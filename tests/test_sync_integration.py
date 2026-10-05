"""End-to-end pulls through the real rsync binary.

Remote side: a temp folder reached either as a local path or through the ``ssh_server`` fixture,
a real ssh connection to a local paramiko server (see ``ssh_server.py``). Authentication and
connection-failure cases are in ``test_sync_ssh.py``.
"""

import os
import shutil
import threading

import pytest
from PyQt6.QtCore import QTimer

from qe_studio.core.config import parse_config
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.planner import Decision, recheck_local
from qe_studio.core.sync.rsync import Endpoint

from ssh_server import HOST_ALIAS, USER
from sync_helpers import T0, run_sync, write

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


def make_config():
    return parse_config({})  # the remote is a local path in these tests: no cluster, no ssh


@pytest.fixture
def dirs(tmp_path):
    remote = tmp_path / "cluster" / "Simulações" / "4 DOS - PDOS"
    local = tmp_path / "local" / "Simulações" / "4 DOS - PDOS"
    remote.mkdir(parents=True)
    return remote, local


def test_pull_through_ssh_with_excludes(qtbot, tmp_path, ssh_server):
    server, remote = ssh_server
    local = tmp_path / "local"
    write(remote, "scf.out", "scf")
    write(remote, "orbitals/pdos.dat.pdos_atm#1(Al)_wfc#1(s)", "pdos")
    write(remote, "ação.out", "unicode")
    write(remote, "tmp/al.save/data-file.xml", "heavy")
    write(remote, "al.wfc1", "heavy")
    config = parse_config(server.config_data())
    endpoint = Endpoint(str(remote), HOST_ALIAS, USER)
    report, prompts = run_sync(qtbot, SyncController(config), local, endpoint)

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
    assert "baixado" in report.message
    assert {r.method for r in server.log} == {"publickey"}
    assert all(r.user == USER and r.command.startswith("rsync --server") for r in server.log)
    assert len(server.log) == 2  # the dry run and the transfer

    again, _ = run_sync(qtbot, SyncController(config), local, endpoint)
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


def test_the_plan_waits_for_confirmation(qtbot, dirs):
    """Spec 17 R2: the preview comes before anything is written, then "Baixar" pulls it all."""
    remote, local = dirs
    write(remote, "a.out", "a")
    write(remote, "sub/b.out", "b")
    controller = SyncController(make_config())
    controller.confirm_plan(True)  # not running: ignored
    with qtbot.waitSignal(controller.plan_ready, timeout=30_000) as ready:
        controller.start(local, Endpoint(str(remote)))
    plan = ready.args[0]
    assert len(plan.new) == 2 and controller.running
    qtbot.wait(200)
    assert not local.exists()  # nothing moves until the answer
    with qtbot.waitSignal(controller.finished, timeout=30_000) as done:
        controller.confirm_plan(True)
    report = done.args[0]
    assert report.status is SyncStatus.DONE
    assert sorted(report.transferred) == ["a.out", "sub/b.out"]
    assert (local / "sub" / "b.out").read_text() == "b"


def test_a_declined_plan_transfers_nothing(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    write(remote, "b.out", "b")
    plans = []
    controller = SyncController(make_config())
    report, prompts = run_sync(
        qtbot, controller, local, Endpoint(str(remote)), confirm=False, plans=plans
    )
    assert report.status is SyncStatus.CANCELLED and report.transferred == []
    assert [len(plan.new) for plan in plans] == [2] and prompts == []
    assert not local.exists()


def test_cancel_while_the_preview_waits(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    controller = SyncController(make_config())
    controller.plan_ready.connect(lambda _plan: controller.cancel())
    report, _ = run_sync(qtbot, controller, local, Endpoint(str(remote)), confirm=None)
    assert report.status is SyncStatus.CANCELLED and not local.exists()


def test_confirm_plan_off_transfers_directly(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "remote", T0 + 100)
    write(local, "a.out", "local", T0)
    write(remote, "new.out", "new")
    plans = []
    config = parse_config({"sync": {"confirm_plan": False}})
    report, prompts = run_sync(
        qtbot,
        SyncController(config),
        local,
        Endpoint(str(remote)),
        {"a.out": Decision.OVERWRITE},
        confirm=None,  # an unanswered preview would hang the test
        plans=plans,
    )
    assert report.status is SyncStatus.DONE and plans == []
    assert prompts == ["a.out"]  # updates still ask file by file
    assert sorted(report.transferred) == ["a.out", "new.out"]


def test_nothing_to_transfer_has_no_preview(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "same", T0)
    write(local, "a.out", "same", T0)
    plans = []
    report, _ = run_sync(
        qtbot, SyncController(make_config()), local, Endpoint(str(remote)), plans=plans
    )
    assert report.status is SyncStatus.UP_TO_DATE and plans == []


def test_local_newer_folder_blocks_transfer(qtbot, dirs):
    remote, local = dirs
    write(remote, "scf.out", "cluster", T0)
    write(local, "scf.out", "edited locally", T0 + 500)
    plans = []
    report, prompts = run_sync(
        qtbot, SyncController(make_config()), local, Endpoint(str(remote)), plans=plans
    )
    assert report.status is SyncStatus.LOCAL_NEWER and plans == []  # no preview either
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


def test_unexpected_stage_error_fails_the_sync(qtbot, dirs, monkeypatch):
    """An exception inside a stage (e.g. mkdir of the local folder) must still end the sync."""
    remote, local = dirs
    write(remote, "a.out", "x")

    def broken(*args, **kwargs):
        raise NotADirectoryError(20, "Not a directory", str(local))

    monkeypatch.setattr("qe_studio.core.sync.controller.transfer_command", broken)
    controller = SyncController(make_config())
    report, _ = run_sync(qtbot, controller, local, Endpoint(str(remote)))
    assert report.status is SyncStatus.FAILED and "Not a directory" in report.error
    assert not controller.running


def test_temp_cleanup_lists_each_folder_once(tmp_path, monkeypatch):
    controller = SyncController(make_config())
    controller._local_dir = tmp_path
    controller._transfer = [f"run/f{i}.out" for i in range(50)] + ["other/x.dat"]
    for name in ("run/.f1.out.Ab12Cd", "run/.f49.out.zzzzzz", "run/.keep.out.Ab12Cd", "run/f1.out"):
        write(tmp_path, name, "")
    write(tmp_path, "other/.x.dat.123456", "")
    scanned = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda path: scanned.append(path) or real(path))
    controller._remove_temp_files()
    assert sorted(p.name for p in (tmp_path / "run").iterdir()) == [".keep.out.Ab12Cd", "f1.out"]
    assert list((tmp_path / "other").iterdir()) == []
    assert len(scanned) == 2


# -- files that change while the preview is open (spec 27-3 R3.1) ---------------------------------
def test_a_file_edited_during_the_preview_is_not_overwritten(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "remote a", T0 + 100)
    write(local, "a.out", "local a", T0)

    def edit(_plan):
        write(local, "a.out", "edited while the preview was open", T0 + 50)

    report, _ = run_sync(
        qtbot,
        SyncController(make_config()),
        local,
        Endpoint(str(remote)),
        {"a.out": Decision.OVERWRITE},
        before_confirm=edit,
    )
    assert report.status is SyncStatus.DONE
    assert report.transferred == [] and report.changed_locally == ("a.out",)
    assert (local / "a.out").read_text() == "edited while the preview was open"
    assert (
        "1 arquivo(s) mudaram localmente durante a prévia e não foram baixados." in report.message
    )
    assert "Mudaram localmente (não baixados) (1):\n  a.out" in report.details
    assert report.headline.endswith("não foram baixados.")


def test_a_file_created_during_the_preview_is_not_overwritten(qtbot, dirs):
    remote, local = dirs
    write(remote, "new.out", "remote")
    write(remote, "other.out", "other")

    report, _ = run_sync(
        qtbot,
        SyncController(make_config()),
        local,
        Endpoint(str(remote)),
        before_confirm=lambda _plan: write(local, "new.out", "mine", T0 + 7),
    )
    assert report.status is SyncStatus.DONE
    assert report.transferred == ["other.out"]  # the file nobody touched still comes
    assert report.changed_locally == ("new.out",)
    assert (local / "new.out").read_text() == "mine"
    assert (local / "other.out").read_text() == "other"


def test_a_file_removed_during_the_preview_is_not_brought_back(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "remote a", T0 + 100)
    write(local, "a.out", "local a", T0)
    report, _ = run_sync(
        qtbot,
        SyncController(make_config()),
        local,
        Endpoint(str(remote)),
        {"a.out": Decision.OVERWRITE},
        before_confirm=lambda _plan: (local / "a.out").unlink(),
    )
    assert report.transferred == [] and report.changed_locally == ("a.out",)
    assert not (local / "a.out").exists()


def test_nothing_changed_nothing_is_reported(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "remote a", T0 + 100)
    write(local, "a.out", "local a", T0)
    report, _ = run_sync(
        qtbot,
        SyncController(make_config()),
        local,
        Endpoint(str(remote)),
        {"a.out": Decision.OVERWRITE},
    )
    assert report.transferred == ["a.out"] and report.changed_locally == ()
    assert "mudaram" not in report.message and "Mudaram" not in report.details
    assert report.headline == report.message.splitlines()[0]


def test_cancel_while_the_local_files_are_rechecked(qtbot, dirs, monkeypatch):
    remote, local = dirs
    write(remote, "a.out", "a")
    gate = threading.Event()

    def slow(items, local_dir):
        gate.wait(10)
        return recheck_local(items, local_dir)

    monkeypatch.setattr("qe_studio.core.sync.controller.recheck_local", slow)
    controller = SyncController(make_config())

    def on_stage(text):
        if text == SyncController.CHECKING:
            QTimer.singleShot(0, controller.cancel)
            QTimer.singleShot(50, gate.set)

    report, _ = run_sync(qtbot, controller, local, Endpoint(str(remote)), on_stage=on_stage)
    assert report.status is SyncStatus.CANCELLED and not local.exists()


def test_a_failing_recheck_ends_the_sync_as_failed(qtbot, dirs, monkeypatch):
    remote, local = dirs
    write(remote, "a.out", "a")

    def broken(items, local_dir):
        raise RuntimeError("stat exploded")

    monkeypatch.setattr("qe_studio.core.sync.controller.recheck_local", broken)
    report, _ = run_sync(qtbot, SyncController(make_config()), local, Endpoint(str(remote)))
    assert report.status is SyncStatus.FAILED and "stat exploded" in report.error
