"""The sync window of spec 17 (R2.3): one dialog from the listing to the progress, the plan
preview and how a pull ends (toast, or a message box over the window when it needs attention).
Real rsync, local remote folders: ``SyncCoordinator.run`` with a host-less ``Endpoint``."""

import shutil

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QMessageBox, QWidget

from qe_studio.core.config import parse_config
from qe_studio.core.sync.controller import SyncStatus
from qe_studio.core.sync.planner import LARGE_FILE_BYTES, Action, PlanItem, SyncPlan
from qe_studio.core.sync.preview import LARGE_TIP
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.dialogs.sync_pages import PreviewPage
from qe_studio.ui.sync_coordinator import SyncCoordinator
from qe_studio.ui.theme.manager import ThemeManager

from sync_helpers import T0, write

MB = 1024**2
rsync = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


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
    """(coordinator, remote, project): the project is ``tmp_path/proj``, the remote a folder."""
    project, remote = tmp_path / "proj", tmp_path / "cluster"
    project.mkdir()
    remote.mkdir()
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    config = parse_config({"paths": {"local_root": str(project)}})
    coordinator = SyncCoordinator(config, ThemeManager("dark"), parent, parent)
    return coordinator, remote, project


def start(qtbot, coordinator, folder, remote):
    coordinator.run(folder, Endpoint(str(remote)))
    dialog = coordinator.dialog
    assert dialog is not None
    return dialog


@rsync
def test_one_window_from_listing_to_progress(qtbot, rig, boxes):
    coordinator, remote, project = rig
    write(remote, "a.out", "a")
    write(remote, "sub/b.out", "b")
    notices = []
    coordinator.notice.connect(lambda *args: notices.append(args))
    dialog = start(qtbot, coordinator, project / "run", remote)
    assert dialog.current_page() is dialog.search
    assert dialog.scope_label.text() == "Baixar do cluster: run (e subpastas)"
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
    assert coordinator.dialog is dialog
    assert dialog.parent().findChildren(QDialog) == [dialog]  # nothing opened beside it
    assert dialog.preview.summary.text() == "2 arquivos novos (2 B)"
    assert dialog.preview.large.isHidden()
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        dialog.download_button.click()
        assert dialog.current_page() is dialog.transfer
    assert blocker.args[0].status is SyncStatus.DONE
    assert boxes == []  # success is not modal
    assert not dialog.isVisible()
    assert [n[:2] for n in notices] == [("2 arquivo(s) baixado(s).", "success")]
    assert (project / "run" / "sub" / "b.out").read_text() == "b"


@rsync
def test_escape_on_the_preview_cancels(qtbot, rig, boxes):
    coordinator, remote, project = rig
    write(remote, "a.out", "a")
    messages = []
    coordinator.message.connect(lambda text, level, _ms: messages.append((text, level)))
    dialog = start(qtbot, coordinator, project / "run", remote)
    qtbot.waitUntil(lambda: dialog.current_page() is dialog.preview, timeout=15_000)
    with qtbot.waitSignal(coordinator.finished, timeout=10_000) as blocker:
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert blocker.args[0].status is SyncStatus.CANCELLED
    assert not (project / "run").exists() and not dialog.isVisible()
    assert boxes == [] and messages == [("Sincronização cancelada.", "warning")]


@rsync
def test_a_failure_is_shown_over_the_sync_window(qtbot, rig, boxes):
    coordinator, remote, project = rig
    dialog = start(qtbot, coordinator, project, remote / "nope")
    with qtbot.waitSignal(coordinator.finished, timeout=30_000) as blocker:
        pass
    assert blocker.args[0].status is SyncStatus.FAILED
    assert [(kind, parent, visible) for kind, parent, visible in boxes] == [
        ("critical", dialog, True)
    ]
    assert not dialog.isVisible()  # closed after the box


def tree_preview(qtbot, plan):
    page = PreviewPage(ThemeManager("dark"))
    qtbot.addWidget(page)
    page.set_plan(plan)
    return page


def test_large_files_stand_out(qtbot):
    big = 150 * MB
    plan = SyncPlan(
        [
            PlanItem("a/small.out", Action.NEW, 1024, T0),
            PlanItem("a/charge.dat", Action.NEW, big, T0),
            PlanItem("b/x.out", Action.NEW, 10, T0),
            PlanItem("scf.out", Action.UPDATE, 2048, T0, T0 - 60),
        ]
    )
    page = tree_preview(qtbot, plan)
    rows = {row.text(0): row for row in page.file_rows()}
    assert [row.text(0) for row in page.file_rows()] == [
        "charge.dat",
        "small.out",
        "x.out",
        "scf.out",
    ]  # largest first in each group
    large, small = rows["charge.dat"], rows["small.out"]
    assert not large.icon(0).isNull() and LARGE_TIP in large.toolTip(0)
    assert large.font(1).bold() and large.text(1) == "150.0 MB"
    assert small.icon(0).isNull() and LARGE_TIP not in small.toolTip(0)
    assert not small.font(1).bold()
    assert rows["scf.out"].text(3) == "pedirá confirmação"
    assert large.parent().isExpanded() and not rows["x.out"].parent().isExpanded()
    assert page.large.isVisibleTo(page) and page.large.text() == "1 arquivo grande soma 150.0 MB"
    assert page.summary.text().startswith("3 arquivos novos (150.0 MB)")


def test_no_large_line_without_large_files(qtbot):
    plan = SyncPlan([PlanItem("a.out", Action.NEW, LARGE_FILE_BYTES, T0)])
    page = tree_preview(qtbot, plan)
    assert not page.large.isVisibleTo(page) and page.file_rows()[0].icon(0).isNull()
