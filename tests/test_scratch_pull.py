"""The copy of a remote plot (spec 66 R3) through the real rsync: into ``<mirror>/tmp_remote/``,
overwritten without a question, the preview only for a large file. The "cluster" is a local folder
(a host-less ``Endpoint``, as in ``test_sync_integration.py``); the coordinator's ``start_scratch``
gets it from ``remote_helpers.serve_locally``."""

import os
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QWidget

from qe_studio.core.config import parse_config
from qe_studio.core.scratch import scratch_of
from qe_studio.core.sync import planner
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.preview import REPLACED, describe_plan
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.sync_coordinator import WAIT_RUNNING, SyncCoordinator
from qe_studio.ui.theme.manager import ThemeManager

from remote_helpers import REMOTE, serve_locally
from sync_helpers import MB, T0, run_sync, write

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


def config():
    return parse_config({})  # the remote is a local path: no cluster, no ssh


def snapshot(root: Path, skip: str = "tmp_remote") -> dict[str, tuple[bytes, float]]:
    """Every file under ``root`` but those of ``skip/``: content and mtime."""
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).parts[0] != skip
    }


@pytest.fixture
def dirs(tmp_path):
    """(mirror, cluster): ``ilita/Bands`` on both sides; the mirror does not exist yet."""
    cluster = tmp_path / "cluster" / "ilita" / "Bands"
    write(cluster, "scf.out", "scf from the cluster")
    write(cluster, "bands.out", "bands from the cluster")
    write(cluster, "orbitals/pdos_tot", "dos")
    return tmp_path / "local" / "ilita" / "Bands", cluster


def copy(qtbot, mirror: Path, cluster: Path, **kwargs):
    controller = SyncController(config(), scratch=True)
    return run_sync(qtbot, controller, scratch_of(mirror), Endpoint(str(cluster)), **kwargs)


def test_the_first_copy_makes_tmp_remote_without_a_question(qtbot, dirs):
    mirror, cluster = dirs
    plans = []
    report, prompts = copy(qtbot, mirror, cluster, plans=plans)
    assert report.status is SyncStatus.DONE, report.error
    assert plans == [] and prompts == []  # no preview, no conflict prompt
    target = mirror / "tmp_remote"
    assert report.local_dir == target
    assert (target / "scf.out").read_text() == "scf from the cluster"
    assert (target / "orbitals/pdos_tot").read_text() == "dos"  # the whole folder, subfolders too
    assert sorted(p.name for p in mirror.iterdir()) == ["tmp_remote"]


def test_a_second_copy_overwrites_where_a_pull_asks(qtbot, dirs):
    mirror, cluster = dirs
    copy(qtbot, mirror, cluster)
    write(cluster, "scf.out", "scf from the cluster, later", T0 + 3600)
    target = mirror / "tmp_remote"

    _report, prompts = run_sync(qtbot, SyncController(config()), target, Endpoint(str(cluster)))
    assert prompts == ["scf.out"]  # the pull of always asks (and the default answer skips)
    assert (target / "scf.out").read_text() == "scf from the cluster"

    report, prompts = copy(qtbot, mirror, cluster)
    assert report.status is SyncStatus.DONE, report.error
    assert prompts == [] and report.transferred == ["scf.out"]
    assert (target / "scf.out").read_text() == "scf from the cluster, later"


def test_a_copy_edited_by_hand_goes_back_to_the_cluster(qtbot, dirs):
    mirror, cluster = dirs
    copy(qtbot, mirror, cluster)
    write(mirror / "tmp_remote", "scf.out", "edited here, and newer", T0 + 7200)
    report, prompts = copy(qtbot, mirror, cluster)
    assert report.status is SyncStatus.DONE, report.error
    assert prompts == [] and report.transferred == ["scf.out"]
    assert report.local_newer == [] and report.message == "1 arquivo baixado."
    assert (mirror / "tmp_remote/scf.out").read_text() == "scf from the cluster"


def test_the_mirror_own_files_are_never_touched(qtbot, dirs):
    mirror, cluster = dirs
    write(mirror, "scf.out", "mine", T0 - 3600)  # same name as the cluster's, older
    write(mirror, "plots/bands.png", "my figure")
    write(mirror, "notes.txt", "notes")
    before = snapshot(mirror)
    report, prompts = copy(qtbot, mirror, cluster)
    assert report.status is SyncStatus.DONE and prompts == []
    assert snapshot(mirror) == before
    assert (mirror / "tmp_remote/scf.out").read_text() == "scf from the cluster"


def test_a_large_file_shows_the_preview_and_declining_copies_nothing(qtbot, dirs):
    mirror, cluster = dirs
    with open(cluster / "big.dat", "wb") as big:
        big.truncate(101 * MB)  # sparse: nothing is written to the disk
    plans = []
    report, prompts = copy(qtbot, mirror, cluster, confirm=False, plans=plans)
    (plan,) = plans
    assert plan.overwrite and [item.path for item in plan.large] == ["big.dat"]
    assert report.status is SyncStatus.CANCELLED and prompts == []
    assert not (mirror / "tmp_remote").exists()


def test_the_preview_of_a_copy_says_what_it_replaces(qtbot, dirs, monkeypatch):
    mirror, cluster = dirs
    copy(qtbot, mirror, cluster)
    write(cluster, "scf.out", "scf from the cluster, later", T0 + 3600)
    write(cluster, "new.out", "new")
    monkeypatch.setattr(planner, "LARGE_FILE_BYTES", 10)  # every file here is "large"
    plans = []
    report, prompts = copy(qtbot, mirror, cluster, plans=plans)
    assert report.status is SyncStatus.DONE, report.error
    assert prompts == [] and sorted(report.transferred) == ["new.out", "scf.out"]
    preview = describe_plan(plans[0])
    assert preview.summary == "1 arquivo novo (3 B) · 1 a substituir (27 B)"
    assert [section.note for section in preview.sections] == ["", REPLACED]
    assert (mirror / "tmp_remote/scf.out").read_text() == "scf from the cluster, later"


def test_nothing_is_deleted_and_plots_remote_survives(qtbot, dirs):
    mirror, cluster = dirs
    copy(qtbot, mirror, cluster)
    settings = write(mirror / "tmp_remote", "plots_remote/bands.plot", "lain_plot: 1\n")
    (cluster / "bands.out").unlink()
    write(cluster, "scf.out", "scf from the cluster, later", T0 + 3600)
    report, _prompts = copy(qtbot, mirror, cluster)
    assert report.status is SyncStatus.DONE, report.error
    assert settings.read_text() == "lain_plot: 1\n"
    assert (mirror / "tmp_remote/bands.out").read_text() == "bands from the cluster"


def test_nothing_new_is_up_to_date(qtbot, dirs):
    mirror, cluster = dirs
    copy(qtbot, mirror, cluster)
    report, prompts = copy(qtbot, mirror, cluster)
    assert report.status is SyncStatus.UP_TO_DATE and prompts == []


# -- the coordinator (R3.3) -------------------------------------------------------------------
@pytest.fixture
def boxes(monkeypatch):
    shown = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, kind, staticmethod(lambda *a, k=kind, **kw: shown.append((k, a[2])))
        )
    return shown


@pytest.fixture
def coordinator(qtbot, tmp_path, monkeypatch, boxes):
    root = tmp_path / "local"
    root.mkdir(exist_ok=True)
    data = {
        "paths": {"local_root": str(root), "remote_root": REMOTE},
        "cluster": {"host": "hpc.example", "user": "usuario", "jobs_command": ""},
    }
    parent = QWidget()
    qtbot.addWidget(parent)
    serve_locally(monkeypatch, tmp_path / "cluster")
    return SyncCoordinator(parse_config(data), ThemeManager("dark"), parent, parent)


def start(qtbot, coordinator, mirror: Path, ready: list[Path], decline: bool = False):
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        coordinator.start_scratch(mirror, ready.append)
        assert coordinator.dialog is not None
        assert (
            coordinator.dialog.scope_label.text()
            == "Baixando para plotar: ilita/Bands (e subpastas)"
        )
        if decline:
            controller = coordinator.controller
            assert controller is not None
            controller.plan_ready.connect(
                lambda _plan: QTimer.singleShot(0, lambda: controller.confirm_plan(False))
            )
    return blocker.args[0]


def test_start_scratch_hands_the_copy_over(qtbot, coordinator, dirs, boxes):
    mirror, _cluster = dirs
    ready = []
    report = start(qtbot, coordinator, mirror, ready)
    assert report.status is SyncStatus.DONE, report.error
    assert ready == [mirror / "tmp_remote"] and boxes == []
    again = start(qtbot, coordinator, mirror, ready)  # nothing to copy: plots what is there
    assert again.status is SyncStatus.UP_TO_DATE
    assert ready == [mirror / "tmp_remote"] * 2


def test_a_declined_preview_plots_nothing(qtbot, coordinator, dirs, monkeypatch):
    mirror, _cluster = dirs
    monkeypatch.setattr(planner, "LARGE_FILE_BYTES", 10)
    ready = []
    report = start(qtbot, coordinator, mirror, ready, decline=True)
    assert report.status is SyncStatus.CANCELLED and ready == []


def test_a_failed_copy_plots_nothing(qtbot, coordinator, tmp_path, boxes):
    ready = []
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        coordinator.start_scratch(tmp_path / "local" / "ilita" / "nada", ready.append)
    assert blocker.args[0].status is SyncStatus.FAILED and ready == []
    assert [kind for kind, _text in boxes] == ["critical"]


def test_a_copy_waits_for_a_running_sync(coordinator, monkeypatch, tmp_path):
    monkeypatch.setattr(type(coordinator), "running", property(lambda self: True))
    messages, ready = [], []
    coordinator.message.connect(lambda text, level, _ms: messages.append((text, level)))
    coordinator.start_scratch(tmp_path / "local" / "ilita" / "Bands", ready.append)
    assert messages == [(WAIT_RUNNING, "warning")] and coordinator.dialog is None
    assert WAIT_RUNNING == "Aguarde a sincronização em andamento."


def test_root_and_project_are_refused(coordinator, tmp_path, boxes):
    root = tmp_path / "local"
    for folder in (root, root / "ilita"):
        coordinator.start_scratch(folder, lambda _copy: pytest.fail("plotted"))
    assert boxes == [
        ("warning", "Escolha uma pasta de cálculo para plotar; a raiz não é copiada."),
        ("warning", "Escolha uma pasta de cálculo para plotar; o projeto inteiro não é copiado."),
    ]
    assert coordinator.controller is None
    assert not (root / "tmp_remote").exists() and not os.path.exists(root / "ilita")
