""" "Baixar" in the cluster mode (spec 65 R5): the pull of always, of a folder or of one file, through
the real rsync. The "cluster" is a local folder (as in ``test_sync_integration.py``), and once the
test SSH server, from the window's menu to the file on disk."""

import shutil

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.remote.download import only_file_rules
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.planner import Decision
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.widgets.remote_model import RemotePath

from remote_helpers import menu_spy
from sync_helpers import T0, run_sync, write

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


def config():
    return parse_config({})  # the remote is a local path: no cluster, no ssh


def test_a_folder_missing_here_is_made_and_filled(qtbot, tmp_path):
    remote, local = tmp_path / "cluster" / "Analise 1", tmp_path / "local" / "Analise 1"
    write(remote, "scf.out", "scf")
    write(remote, "bands/bands.out", "bands")
    plans = []
    report, prompts = run_sync(
        qtbot, SyncController(config()), local, Endpoint(str(remote)), plans=plans
    )
    assert report.status is SyncStatus.DONE, report.error
    assert len(plans) == 1 and prompts == []  # the preview was confirmed first
    assert (local / "scf.out").read_text() == "scf"
    assert (local / "bands" / "bands.out").read_text() == "bands"


def test_a_different_local_file_is_asked_and_never_overwritten_alone(qtbot, tmp_path):
    remote, local = tmp_path / "cluster", tmp_path / "local"
    write(remote, "scf.out", "cluster", T0 + 100)
    write(local, "scf.out", "mine", T0)
    rules = only_file_rules("scf.out")
    report, prompts = run_sync(
        qtbot, SyncController(config(), extra_args=rules), local, Endpoint(str(remote))
    )
    assert prompts == ["scf.out"]  # asked; the default answer skips
    assert (local / "scf.out").read_text() == "mine"
    assert report.status is SyncStatus.DONE

    again, prompts = run_sync(
        qtbot,
        SyncController(config(), extra_args=rules),
        local,
        Endpoint(str(remote)),
        decisions={"scf.out": Decision.OVERWRITE},
    )
    assert prompts == ["scf.out"] and (local / "scf.out").read_text() == "cluster"


@pytest.mark.parametrize("name", ["a[1].in", "x*y.out", "com espaço.out", "plain\\name"])
def test_one_file_and_not_its_namesake_below(qtbot, tmp_path, name):
    remote, local = tmp_path / "cluster", tmp_path / "local"
    write(remote, name, "top")
    write(remote, f"sub/{name}", "below")
    write(remote, "other.out", "other")
    controller = SyncController(config(), extra_args=only_file_rules(name))
    report, _prompts = run_sync(qtbot, controller, local, Endpoint(str(remote)))
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == [name]
    assert (local / name).read_text() == "top"
    assert not (local / "sub").exists() and not (local / "other.out").exists()


def test_download_from_the_cluster_menu(qtbot, ssh_server, window_factory, tmp_path, monkeypatch):
    server, remote = ssh_server
    write(remote, "proj/run/scf.out", "scf from the cluster")
    write(remote, "proj/run/big.wfc1", "never")
    root = tmp_path / "local"
    (root / "proj").mkdir(parents=True)
    data = server.config_data(jobs_command="")
    data["paths"]["local_root"] = str(root)
    window = window_factory(loaded=LoadedConfig(parse_config(data), None))
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(lambda *a, **k: None))

    with qtbot.waitSignal(window.remote.listed, timeout=20_000):
        window.activity.remote.click()  # the real listing, through ssh
    assert window.remote.current == str(remote)
    menu_spy(monkeypatch, choose="Baixar")
    window.remote.show_menu([RemotePath(f"{remote}/proj/run/scf.out", False)], QPoint())
    dialog = window.sync.dialog
    assert dialog is not None
    assert dialog.scope_label.text() == "Baixar do cluster: proj/run/scf.out"
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=20_000)
    with qtbot.waitSignal(window.sync_finished, timeout=30_000) as blocker:
        dialog.download_button.click()
    report = blocker.args[0]
    assert report.status is SyncStatus.DONE, report.error
    assert (root / "proj/run/scf.out").read_text() == "scf from the cluster"
    assert not (root / "proj/run/big.wfc1").exists()
    assert window.remote.active  # the mode goes on after a "Baixar"
