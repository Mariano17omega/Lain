import os
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.planner import Action, Decision, PlanItem, SyncPlan
from qe_studio.core.sync.request import SYNC_OFF, SyncScope
from qe_studio.ui.dialogs.sync_dialog import ConflictDialog, SyncDialog
from qe_studio.ui.main_window import MainWindow
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.spinner import CircularProgress

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
T0 = 1_700_000_000


def touch(path: Path, text: str, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (mtime, mtime))


@pytest.fixture
def messages(monkeypatch):
    shown = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, kind, staticmethod(lambda *a, k=kind, **kw: shown.append((k, a[2])))
        )
    return shown


def make_window(qtbot, tmp_path, demo_project, ssh_server, **cluster):
    server, remote = ssh_server
    data = server.config_data(**cluster)
    data["paths"]["local_root"] = str(demo_project)
    theme = ThemeManager("dark")
    theme.apply()
    window = MainWindow(
        LoadedConfig(parse_config(data), None),
        theme,
        QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        FolderMemory(tmp_path / "memory.json"),
    )
    qtbot.addWidget(window)
    window.show()
    return window, remote


def test_sync_with_conflict_prompt(qtbot, tmp_path, demo_project, ssh_server, messages):
    window, remote = make_window(qtbot, tmp_path, demo_project, ssh_server)
    local = demo_project / "03_bands"
    os.utime(local / "scf.out", (T0, T0))
    touch(remote / "03_bands" / "scf.out", "cluster version", T0 + 3600)
    touch(remote / "03_bands" / "new.out", "new", T0 + 3600)
    touch(remote / "03_bands" / "tmp" / "al.save" / "big.dat", "heavy", T0)
    window.explorer.select_path(local)

    with qtbot.waitSignal(window.sync_finished, timeout=30_000) as blocker:
        window.start_sync()
        assert window.monitor.state.value == "syncing"
        dialog = window.sync.dialog
        assert dialog.scope_label.text() == "Baixar do cluster: 03_bands (e subpastas)"
        qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
        assert not (local / "new.out").exists()  # nothing moves before "Baixar"
        dialog.download_button.click()
        qtbot.waitUntil(lambda: window.sync.conflict_dialog is not None, timeout=15_000)
        assert dialog.current_page() is dialog.transfer
        assert dialog.transfer.stage.text() == "Aguardando sua decisão…"
        assert window.sync.conflict_dialog.item.path == "scf.out"
        window.sync.conflict_dialog.decide(Decision.OVERWRITE)
    report = blocker.args[0]
    assert report.status is SyncStatus.DONE
    assert sorted(report.transferred) == ["new.out", "scf.out"]
    assert (local / "scf.out").read_text() == "cluster version"
    assert not (local / "tmp" / "al.save").exists()
    assert messages == []  # success is a toast, not a message box (spec 17 R3)
    assert window.toast.isVisible() and window.toast.text.text() == "2 arquivo(s) baixado(s)."
    assert window.status.message.text() == "2 arquivo(s) baixado(s)."
    assert window.monitor.state.value != "syncing"
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window.sync.controller is None and window.sync.conflict_dialog is None
    for kind in (SyncController, SyncDialog, ConflictDialog):  # nothing piles up per sync
        assert not window.findChildren(kind)


def test_sync_local_newer_warns(qtbot, tmp_path, demo_project, ssh_server, messages):
    window, remote = make_window(qtbot, tmp_path, demo_project, ssh_server)
    local = demo_project / "02_scf"
    os.utime(local / "scf.out", (T0 + 7200, T0 + 7200))
    touch(remote / "02_scf" / "scf.out", "older on cluster", T0)
    window.explorer.select_path(local)
    with qtbot.waitSignal(window.sync_finished, timeout=30_000) as blocker:
        window.start_sync()
    assert blocker.args[0].status is SyncStatus.LOCAL_NEWER
    assert messages[-1][0] == "warning" and "mais recente" in messages[-1][1]


def test_sync_disabled_explains(qtbot, main_window, messages):
    main_window.start_sync()
    assert messages and "config.yaml" in messages[0][1]
    assert main_window.sync.controller is None


def test_password_prompt_is_used_once(
    qtbot, tmp_path, demo_project, ssh_server, monkeypatch, messages
):
    window, _remote = make_window(
        qtbot, tmp_path, demo_project, ssh_server, auth="password", password_env="NOPE_X"
    )
    asked, runs = [], []
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: asked.append(1) or ("s3cret", True))
    )
    monkeypatch.setattr(
        window.sync, "run", lambda folder, endpoint, password=None: runs.append(password)
    )
    window.start_sync()
    window.start_sync()
    assert runs == ["s3cret", "s3cret"] and len(asked) == 1


class FakeController(QObject):
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, str)
    plan_ready = pyqtSignal(object)
    conflict_needed = pyqtSignal(object)
    transfer_started = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.running = True
        self.cancelled = False
        self.confirmed: list[bool] = []

    def cancel(self):
        self.cancelled = True

    def confirm_plan(self, accepted):
        self.confirmed.append(accepted)


def fake_dialog(qtbot):
    controller = FakeController()
    dialog = SyncDialog(ThemeManager("dark"), controller, SyncScope("a/b", "me@h:/r/a/b/"))
    qtbot.addWidget(dialog)
    dialog.open()
    return dialog, controller


def test_sync_dialog_escape_cancels_then_closes(qtbot):
    dialog, controller = fake_dialog(qtbot)
    controller.progress_changed.emit(40, "4/10 arquivos")
    assert dialog.spinner.percent == 40 and dialog.search.detail.text() == "4/10 arquivos"
    dialog.reject()  # Esc while running
    assert controller.cancelled and dialog.isVisible()
    controller.running = False
    dialog.finish()  # the coordinator closes it once the report is out
    assert not dialog.isVisible()


def test_sync_dialog_pages_follow_the_controller(qtbot):
    """One window from the listing to the progress: the pages switch, nothing reopens."""
    dialog, controller = fake_dialog(qtbot)
    assert "a/b (e subpastas)" in dialog.scope_label.text()
    assert dialog.current_page() is dialog.search and not dialog.download_button.isVisible()
    small = dialog.size()
    assert small.height() < dialog.preview.tree.minimumHeight()  # the preview's room is not kept
    controller.plan_ready.emit(SyncPlan([PlanItem("x.out", Action.NEW, 10, T0)]))
    assert dialog.current_page() is dialog.preview and dialog.download_button.isVisible()
    big = dialog.size()
    assert big.height() > small.height() and big.width() >= small.width()
    dialog.download_button.click()
    assert controller.confirmed == [True] and dialog.current_page() is dialog.transfer
    assert dialog.size() == big  # the same window, same size, from the preview to the end
    controller.transfer_started.emit(1)
    controller.progress_changed.emit(55, "0/1 arquivos")
    assert dialog.transfer.bar.value() == 55 and dialog.transfer.detail.text() == "0/1 arquivos"
    controller.progress_changed.emit(-1, "")
    assert dialog.transfer.bar.maximum() == 0  # busy
    assert dialog.isVisible() and dialog.pages.count() == 3


def test_escape_on_the_preview_declines_the_plan(qtbot):
    dialog, controller = fake_dialog(qtbot)
    controller.plan_ready.emit(SyncPlan([PlanItem("x.out", Action.NEW, 10, T0)]))
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert controller.confirmed == [False] and not controller.cancelled


def cluster_window(window_factory, demo_project):
    """A window with sync on; its monitor probes a closed port (refused at once)."""
    data = {
        "paths": {"local_root": str(demo_project), "remote_root": "/scratch/me"},
        "cluster": {"host": "127.0.0.1", "port": 9, "user": "me"},
    }
    return window_factory(LoadedConfig(parse_config(data), None))


def test_rsync_tooltip_and_menu_follow_the_folder(qtbot, window_factory, demo_project):
    window = cluster_window(window_factory, demo_project)
    action, project = window._actions["sync.start"], window._actions["sync.project"]
    (demo_project / "03_bands" / "sub").mkdir()
    window.explorer.select_path(demo_project / "03_bands" / "sub")
    assert "03_bands/sub (e subpastas)" in window.activity.rsync.toolTip()
    assert action.text() == "Sincronizar 03_bands/sub" and action.isEnabled()
    assert "03_bands/sub (e subpastas)" in action.toolTip()
    window.explorer.select_path(demo_project)
    assert window.activity.rsync.toolTip() == "Baixar do cluster: projeto inteiro"
    assert action.text() == "Sincronizar projeto inteiro" and project.isEnabled()


def test_rsync_tooltip_when_sync_is_off(qtbot, main_window):
    main_window.explorer.select_path(main_window.root / "03_bands")
    assert main_window.activity.rsync.toolTip() == SYNC_OFF
    assert not main_window._actions["sync.start"].isEnabled()
    assert not main_window._actions["sync.project"].isEnabled()


def test_sync_whole_project_ignores_the_selection(qtbot, window_factory, demo_project):
    window = cluster_window(window_factory, demo_project)
    runs = []
    window.sync.run = lambda folder, endpoint, password=None: runs.append((folder, endpoint))
    window.explorer.select_path(demo_project / "03_bands")
    window._actions["sync.project"].trigger()
    window._actions["sync.start"].trigger()
    assert [(folder, endpoint.path) for folder, endpoint in runs] == [
        (demo_project, "/scratch/me"),
        (demo_project / "03_bands", "/scratch/me/03_bands"),
    ]


@pytest.mark.parametrize("percent", [-1, 0, 55, 100])
def test_spinner_paints(qtbot, percent):
    spinner = CircularProgress(ThemeManager("light"))
    qtbot.addWidget(spinner)
    spinner.set_percent(percent)
    assert not spinner.grab().isNull()
    spinner.stop()
