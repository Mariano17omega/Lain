"""End-to-end pulls through the real rsync binary.

Remote side: a temp folder reached either as a local path or through ``fake_ssh.py``
(exercises the ``-e`` remote-shell path and argument quoting without an ssh server).
"""

import os
import shutil
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer

from qe_studio.config import parse_config
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.planner import Decision
from qe_studio.core.sync.rsync import Endpoint

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")

FAKE_SSH = Path(__file__).parent / "fake_ssh.py"
T0 = 1_700_000_000


def make_config(exclude=None):
    return parse_config(
        {
            "cluster": {"host": "cluster.test", "user": "me", "auth": "key"},
            "sync": {
                "ssh_binary": f"{sys.executable} {FAKE_SSH}",
                **({"exclude": exclude} if exclude is not None else {}),
            },
        }
    )


def write(root: Path, rel: str, content: str, mtime: float = T0) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def dirs(tmp_path):
    remote = tmp_path / "cluster" / "Simulações" / "4 DOS - PDOS"
    local = tmp_path / "local" / "Simulações" / "4 DOS - PDOS"
    remote.mkdir(parents=True)
    return remote, local


def run_sync(qtbot, controller, local, endpoint, decisions=None, on_stage=None):
    prompts = []

    def answer(item):
        prompts.append(item.path)
        decision = (decisions or {}).get(item.path, Decision.SKIP)
        QTimer.singleShot(0, lambda: controller.resolve(decision))

    controller.conflict_needed.connect(answer)
    if on_stage:
        controller.stage_changed.connect(on_stage)
    with qtbot.waitSignal(controller.finished, timeout=30_000) as blocker:
        controller.start(local, endpoint)
    report = blocker.args[0]
    return report, prompts


def test_pull_through_fake_ssh_with_excludes(qtbot, dirs, tmp_path, monkeypatch):
    remote, local = dirs
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    write(remote, "scf.out", "scf")
    write(remote, "orbitals/pdos.dat.pdos_atm#1(Al)_wfc#1(s)", "pdos")
    write(remote, "ação.out", "unicode")
    write(remote, "tmp/al.save/data-file.xml", "heavy")
    write(remote, "al.wfc1", "heavy")
    controller = SyncController(make_config())
    report, prompts = run_sync(
        qtbot, controller, local, Endpoint(str(remote), "cluster.test", "me")
    )

    assert report.status is SyncStatus.DONE, report.error
    assert sorted(report.transferred) == [
        "ação.out",
        "orbitals/pdos.dat.pdos_atm#1(Al)_wfc#1(s)",
        "scf.out",
    ]
    assert prompts == []
    assert (local / "ação.out").read_text(encoding="utf-8") == "unicode"
    assert not (local / "tmp").exists() and not (local / "al.wfc1").exists()
    assert abs((local / "scf.out").stat().st_mtime - T0) < 1  # mtimes preserved
    assert "cluster.test" in log.read_text(encoding="utf-8")
    assert "baixado" in report.message

    again, _ = run_sync(
        qtbot, SyncController(make_config()), local, Endpoint(str(remote), "cluster.test", "me")
    )
    assert again.status is SyncStatus.UP_TO_DATE


def test_conflicts_overwrite_folder_and_skip(qtbot, dirs):
    remote, local = dirs
    for rel in ("a.out", "sub/x.out", "sub/y.out", "z.out"):
        write(remote, rel, f"remote {rel}", T0 + 100)
        write(local, rel, f"local {rel}", T0)
    write(remote, "new.out", "new", T0 + 100)
    decisions = {
        "a.out": Decision.OVERWRITE,
        "sub/x.out": Decision.OVERWRITE_FOLDER,
        "z.out": Decision.SKIP,
    }
    report, prompts = run_sync(
        qtbot, SyncController(make_config()), local, Endpoint(str(remote)), decisions
    )
    assert report.status is SyncStatus.DONE
    assert prompts == ["a.out", "z.out", "sub/x.out"]  # rsync order: root files first
    assert (local / "a.out").read_text() == "remote a.out"
    assert (local / "sub/y.out").read_text() == "remote sub/y.out"
    assert (local / "z.out").read_text() == "local z.out"
    assert (local / "new.out").read_text() == "new"
    assert report.skipped == ["z.out"]


def test_cancel_at_conflict_transfers_nothing(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "remote", T0 + 100)
    write(local, "a.out", "local", T0)
    write(remote, "new.out", "new", T0 + 100)
    report, _ = run_sync(
        qtbot,
        SyncController(make_config()),
        local,
        Endpoint(str(remote)),
        {"a.out": Decision.CANCEL},
    )
    assert report.status is SyncStatus.CANCELLED
    assert not (local / "new.out").exists()
    assert (local / "a.out").read_text() == "local"


def test_local_newer_folder_blocks_transfer(qtbot, dirs):
    remote, local = dirs
    write(remote, "scf.out", "cluster", T0)
    write(local, "scf.out", "edited locally", T0 + 500)
    report, prompts = run_sync(qtbot, SyncController(make_config()), local, Endpoint(str(remote)))
    assert report.status is SyncStatus.LOCAL_NEWER
    assert report.local_newer == ["scf.out"] and report.local_newer_folders == ["."]
    assert prompts == []
    assert (local / "scf.out").read_text() == "edited locally"
    assert "mais recente" in report.message


def test_generated_plots_do_not_block_pull(qtbot, dirs):
    remote, local = dirs
    write(remote, "bands.dat.gnu", "data", T0)
    write(local, "plots/bands.png", "figure", T0 + 10_000)
    report, _ = run_sync(qtbot, SyncController(make_config()), local, Endpoint(str(remote)))
    assert report.status is SyncStatus.DONE
    assert report.transferred == ["bands.dat.gnu"]


def test_cancel_during_transfer_leaves_no_partial(qtbot, dirs):
    remote, local = dirs
    (remote / "big.out").write_bytes(os.urandom(8 * 1024 * 1024))
    controller = SyncController(make_config(), extra_args=["--bwlimit=256"])

    def on_stage(text):
        if text.startswith("Transferindo"):
            QTimer.singleShot(300, controller.cancel)

    report, _ = run_sync(qtbot, controller, local, Endpoint(str(remote)), on_stage=on_stage)
    assert report.status is SyncStatus.CANCELLED
    assert not (local / "big.out").exists()
    assert [p.name for p in local.iterdir()] == []


def test_missing_remote_folder_fails(qtbot, dirs):
    remote, local = dirs
    report, _ = run_sync(
        qtbot, SyncController(make_config()), local, Endpoint(str(remote / "nope"))
    )
    assert report.status is SyncStatus.FAILED
    assert "não encontrada" in report.error


def test_missing_rsync_binary_fails(qtbot, dirs):
    remote, local = dirs
    config = parse_config({"sync": {"rsync_binary": "/nonexistent/rsync"}})
    report, _ = run_sync(qtbot, SyncController(config), local, Endpoint(str(remote)))
    assert report.status is SyncStatus.FAILED and "rsync não encontrado" in report.error
