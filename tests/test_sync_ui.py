import os
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.planner import Decision
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
        qtbot.waitUntil(lambda: window.sync.conflict_dialog is not None, timeout=15_000)
        assert window.sync.conflict_dialog.item.path == "scf.out"
        window.sync.conflict_dialog.decide(Decision.OVERWRITE)
    report = blocker.args[0]
    assert report.status is SyncStatus.DONE
    assert sorted(report.transferred) == ["new.out", "scf.out"]
    assert (local / "scf.out").read_text() == "cluster version"
    assert not (local / "tmp" / "al.save").exists()
    assert messages and messages[-1][0] == "information"
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
    finished = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.running = True
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_sync_dialog_escape_cancels_then_closes(qtbot):
    theme = ThemeManager("dark")
    controller = FakeController()
    dialog = SyncDialog(theme, controller, "me@h:/r/", "/l")
    qtbot.addWidget(dialog)
    dialog.open()
    controller.progress_changed.emit(40, "4/10 arquivos")
    assert dialog.spinner.percent == 40 and dialog.detail.text() == "4/10 arquivos"
    dialog.reject()  # Esc while running
    assert controller.cancelled and dialog.isVisible()
    controller.running = False
    controller.finished.emit(None)
    assert not dialog.isVisible()


@pytest.mark.parametrize("percent", [-1, 0, 55, 100])
def test_spinner_paints(qtbot, percent):
    spinner = CircularProgress(ThemeManager("light"))
    qtbot.addWidget(spinner)
    spinner.set_percent(percent)
    assert not spinner.grab().isNull()
    spinner.stop()
