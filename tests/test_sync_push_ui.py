"""The push from the window (spec 27 R4): the sync window says "Enviando" and "Enviar", its
preview has the two sections, success is a toast, a failure a box over the window; the folder's
context menu and the "Cluster" menu start it. Real rsync, local remote folders, as in
``test_sync_dialog.py``."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu, QMessageBox, QWidget

from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.sync.report import SyncStatus
from qe_studio.core.sync.request import PUSH_ROOT, SYNC_OFF
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.sync_coordinator import SyncCoordinator
from qe_studio.ui.theme.manager import ThemeManager

from sync_helpers import T0, write

rsync = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
PUSH = "Enviar ao cluster"


@pytest.fixture
def boxes(monkeypatch):
    """Message boxes shown: (kind, parent, parent still visible)."""
    shown = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox,
            kind,
            staticmethod(lambda p, *a, k=kind, **kw: shown.append((k, p, p.isVisible()))),
        )
    return shown


@pytest.fixture
def rig(qtbot, tmp_path):
    """(coordinator, local, remote): ``local`` is a calculation folder of the project."""
    project, remote = tmp_path / "proj", tmp_path / "cluster" / "run"
    local = project / "run"
    local.mkdir(parents=True)
    remote.mkdir(parents=True)
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    config = parse_config({"paths": {"local_root": str(project)}})
    coordinator = SyncCoordinator(config, ThemeManager("dark"), parent, parent)
    return coordinator, local, remote


def start(coordinator, local, remote):
    coordinator.run_push(local, Endpoint(str(remote)))
    dialog = coordinator.dialog
    assert dialog is not None
    return dialog


@rsync
def test_the_push_window_previews_then_sends(qtbot, rig, boxes):
    coordinator, local, remote = rig
    write(local, "scf.in", "input")
    write(local, "job/scf.qsub", "qsub")
    write(local, "scf.out", "local copy", T0 + 60)
    write(remote, "scf.out", "cluster copy")
    notices, synced = [], []
    coordinator.notice.connect(lambda *args: notices.append(args))
    coordinator.synced.connect(synced.append)
    dialog = start(coordinator, local, remote)
    assert dialog.windowTitle() == "Enviando para o cluster"
    assert dialog.scope_label.text() == "Enviar para o cluster: run (e subpastas)"
    assert dialog.download_button.text() == "Enviar"
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
    tree = dialog.preview.tree
    header = tree.headerItem()
    assert header is not None and header.text(2) == "Data local"
    sections = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert [s.text(0) for s in sections if s is not None] == [
        "Serão enviados (2 · 9 B)",
        "Já existem no cluster, não serão alterados (1)",
    ]
    send, exists = sections
    assert send is not None and exists is not None
    assert send.isExpanded() and not exists.isExpanded()
    assert exists.foreground(0).color() == dialog.preview.theme.color("text_meta")
    assert not (remote / "scf.in").exists()  # nothing sent before "Enviar"
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        dialog.download_button.click()
    report = blocker.args[0]
    assert report.status is SyncStatus.DONE, report.error
    assert boxes == [] and synced == []  # a toast, and nothing local to refresh
    assert [n[:2] for n in notices] == [("2 arquivo(s) enviado(s).", "success")]
    assert "Já existiam no cluster (não alterados) (1):\n  scf.out" in notices[0][2]
    assert not dialog.isVisible()
    assert (remote / "job/scf.qsub").read_text() == "qsub"
    assert (remote / "scf.out").read_text() == "cluster copy"


@rsync
def test_escape_on_the_push_preview_sends_nothing(qtbot, rig, boxes):
    coordinator, local, remote = rig
    write(local, "scf.in", "input")
    messages = []
    coordinator.message.connect(lambda text, level, _ms: messages.append((text, level)))
    dialog = start(coordinator, local, remote)
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
    with qtbot.waitSignal(coordinator.finished, timeout=10_000) as blocker:
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert blocker.args[0].status is SyncStatus.CANCELLED
    assert not (remote / "scf.in").exists() and not dialog.isVisible()
    assert boxes == [] and messages == [("Envio cancelado.", "warning")]


@rsync
def test_nothing_to_send_is_an_info_toast(qtbot, rig, boxes):
    coordinator, local, remote = rig
    write(local, "scf.in", "local")
    write(remote, "scf.in", "on the cluster")
    notices = []
    coordinator.notice.connect(lambda *args: notices.append(args))
    start(coordinator, local, remote)
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        pass
    assert blocker.args[0].status is SyncStatus.UP_TO_DATE
    assert boxes == [] and [n[:2] for n in notices] == [("Nada a enviar.", "info")]


@rsync
def test_a_failed_push_is_shown_over_the_window(qtbot, rig, boxes):
    coordinator, local, remote = rig
    write(local, "scf.in", "input")
    dialog = start(coordinator, local, remote / "no" / "such" / "parents")
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        dialog.download_button.click()  # a local rsync makes one missing level only
    assert blocker.args[0].status is SyncStatus.FAILED
    assert [(kind, parent, visible) for kind, parent, visible in boxes] == [
        ("critical", dialog, True)
    ]
    assert not dialog.isVisible()


# -- entry points in the main window ---------------------------------------------------------------
@pytest.fixture
def menus(monkeypatch):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


def push_item(menu):
    return next((a for a in menu.actions() if a.text() == PUSH), None)


def cluster_window(window_factory, demo_project):
    """A window with sync on; its monitor probes a closed port (refused at once)."""
    data = {
        "paths": {"local_root": str(demo_project), "remote_root": "/scratch/me"},
        "cluster": {"host": "127.0.0.1", "port": 9, "user": "me"},
    }
    return window_factory(LoadedConfig(parse_config(data), None))


def test_a_folder_menu_offers_the_push_disabled_without_sync(main_window, demo_project, menus):
    main_window._show_item_menu([demo_project / "03_bands"], QPoint())
    item = push_item(menus[-1])
    assert item is not None and not item.isEnabled() and item.toolTip() == SYNC_OFF
    main_window._show_item_menu([demo_project / "03_bands" / "bands.in"], QPoint())
    assert push_item(menus[-1]) is None  # files are never pushed alone


def test_the_folder_menu_pushes_that_folder(window_factory, demo_project, menus):
    window = cluster_window(window_factory, demo_project)
    runs = []
    window.sync.run_push = lambda folder, endpoint, password=None: runs.append((folder, endpoint))
    window._show_item_menu([demo_project / "03_bands"], QPoint())
    item = push_item(menus[-1])
    assert item is not None and item.isEnabled()
    item.trigger()
    assert [(folder, endpoint.path) for folder, endpoint in runs] == [
        (demo_project / "03_bands", "/scratch/me/03_bands")
    ]
    window._show_item_menu([demo_project], QPoint())
    root = push_item(menus[-1])
    assert root is not None and not root.isEnabled() and root.toolTip() == PUSH_ROOT


def test_the_cluster_menu_push_follows_the_folder(window_factory, demo_project):
    window = cluster_window(window_factory, demo_project)
    action = window._actions["sync.push"]
    runs = []
    window.sync.run_push = lambda folder, endpoint, password=None: runs.append(folder)
    window.explorer.select_path(demo_project / "03_bands")
    assert action.text() == "Enviar 03_bands ao cluster…" and action.isEnabled()
    assert action.toolTip() == "Enviar para o cluster: 03_bands (e subpastas)"
    assert "action:sync.push" in [r.key for r in window.command_palette.rows_for(">enviar")]
    action.trigger()
    assert runs == [demo_project / "03_bands"]
    window.explorer.select_path(demo_project)
    assert action.text() == "Enviar pasta ao cluster…" and not action.isEnabled()
    assert action.toolTip() == PUSH_ROOT


def test_the_push_action_is_off_without_sync(main_window):
    main_window.explorer.select_path(main_window.root / "03_bands")
    action = main_window._actions["sync.push"]
    assert not action.isEnabled() and action.toolTip() == SYNC_OFF


def test_a_refused_push_explains_itself(qtbot, tmp_path, boxes):
    parent = QWidget()
    qtbot.addWidget(parent)
    config = parse_config(
        {
            "paths": {"local_root": str(tmp_path), "remote_root": "/scratch/me"},
            "cluster": {"host": "hpc", "user": "me"},
        }
    )
    coordinator = SyncCoordinator(config, ThemeManager("dark"), parent, parent)
    coordinator.push(Path(tmp_path))
    assert [(kind, parent_) for kind, parent_, _ in boxes] == [("warning", parent)]
    assert coordinator.controller is None
