"""Spec 18 R3 (tooltips of badges and state labels, from caches only) and R4 (elided footer)."""

import pytest
from PyQt6.QtCore import QEvent, QPoint
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import QToolTip

from grid_helpers import index_of, show_folder
from qe_studio.core.sniff import FileKind, FileSniff


def hover(qtbot, view, pos: QPoint) -> str:
    """The tooltip a hover over ``pos`` (viewport coordinates) of ``view`` would show."""
    QToolTip.hideText()
    qtbot.waitUntil(lambda: not QToolTip.isVisible(), timeout=2000)
    event = QHelpEvent(QEvent.Type.ToolTip, pos, view.viewport().mapToGlobal(pos))
    view.viewportEvent(event)
    return QToolTip.text() if QToolTip.isVisible() else ""


def tree_row(qtbot, window, folder):
    explorer = window.explorer
    qtbot.waitUntil(lambda: explorer.proxy.index_for(folder).isValid(), timeout=5000)
    index = explorer.proxy.index_for(folder)
    qtbot.waitUntil(lambda: explorer.tree.visualRect(index).isValid(), timeout=5000)
    return explorer.tree.visualRect(index)


# -- R3: folder badges --------------------------------------------------------------------------
def test_relax_badge_tooltip_names_the_module(qtbot, main_window, demo_project):
    window = main_window
    folder = demo_project / "01_relax"
    window.service.detect_now(folder)
    rect = tree_row(qtbot, window, folder)
    tip = hover(qtbot, window.explorer.tree, QPoint(rect.right() - 10, rect.center().y()))
    assert "Otimização estrutural" in tip


def test_badge_tooltip_only_over_the_badge(qtbot, main_window, demo_project):
    window = main_window
    folder = demo_project / "01_relax"
    window.service.detect_now(folder)
    rect = tree_row(qtbot, window, folder)
    # Over the name, far from the badge on the right: not the badge's text.
    tip = hover(qtbot, window.explorer.tree, QPoint(rect.left() + 40, rect.center().y()))
    assert "Otimização estrutural" not in tip


def test_a_tooltip_never_triggers_detection(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    folder = demo_project / "04_pdos"
    asked = []
    monkeypatch.setattr(window.service, "request", lambda *a, **k: asked.append(a))
    assert window.service.peek_results(folder) is None
    rect = tree_row(qtbot, window, folder)
    assert hover(qtbot, window.explorer.tree, QPoint(rect.right() - 10, rect.center().y())) == ""
    assert asked == []


def test_each_module_tooltip_has_its_sentence(qtbot, main_window, demo_project):
    window = main_window
    for name, phrase in [
        ("03_bands", "bands.x/.gnu detectados"),
        ("02_scf", "Cálculo SCF (pw.x)"),
    ]:
        folder = demo_project / name
        results = window.service.detect_now(folder)
        assert any(phrase in r.module.badge_tooltip() for r in results), name


def test_grid_folder_card_explains_its_badges(qtbot, main_window, demo_project):
    window = main_window
    window.service.detect_now(demo_project / "01_relax")
    show_folder(qtbot, window, demo_project, up=False)  # the project root has no ".."
    index = index_of(window.files, "01_relax")
    rect = window.files.view.visualRect(index)
    tip = hover(qtbot, window.files.view, rect.center())
    assert "Otimização estrutural" in tip


# -- R3: file state labels ----------------------------------------------------------------------
def test_incomplete_label_tooltip_mentions_job_done(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    folder = demo_project / "03_bands"
    output = folder / "scf.out"
    cut = FileSniff(output, FileKind.PW_OUT, job_done=False)
    monkeypatch.setattr(window.service, "file_sniff", lambda p: cut if p == output else None)
    show_folder(qtbot, window, folder)
    rect = window.files.view.visualRect(index_of(window.files, "scf.out"))
    tip = hover(qtbot, window.files.view, QPoint(rect.center().x(), rect.bottom() - 6))
    assert "JOB DONE" in tip
    # The top of the card (the icon and the name) has no state tooltip.
    assert "JOB DONE" not in hover(
        qtbot, window.files.view, QPoint(rect.center().x(), rect.top() + 12)
    )


def test_warning_label_lists_the_warnings(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    folder = demo_project / "03_bands"
    output = folder / "scf.out"
    warned = FileSniff(
        output, FileKind.PW_OUT, job_done=True, warnings=("SCF não convergiu", "outro aviso")
    )
    monkeypatch.setattr(window.service, "file_sniff", lambda p: warned if p == output else None)
    show_folder(qtbot, window, folder)
    rect = window.files.view.visualRect(index_of(window.files, "scf.out"))
    tip = hover(qtbot, window.files.view, QPoint(rect.center().x(), rect.bottom() - 6))
    assert tip == "SCF não convergiu\noutro aviso"


# -- R4: the footer ---------------------------------------------------------------------------
READOUT = "Estrutura de bandas · E_F = 8.0584 eV · gap direto 1.234 eV em Γ · 1200×900 px (300 DPI)"


@pytest.fixture
def narrow(main_window):
    main_window.resize(600, 700)
    return main_window


def test_long_readout_is_elided_in_a_narrow_window(qtbot, narrow):
    status = narrow.status
    status.set_readout(READOUT)
    status.set_path("03_bands/subpasta/bands.in")
    qtbot.waitUntil(lambda: status.readout.text() != READOUT, timeout=3000)
    assert "…" in status.readout.text() and len(status.readout.text()) < len(READOUT)
    assert status.readout.toolTip() == READOUT
    assert status.readout.full_text() == READOUT
    assert (
        status.message.width() >= status.MESSAGE_MIN_WIDTH
    )  # the readout gave way, not the message


def test_the_path_is_elided_by_the_same_rule(qtbot, narrow):
    status = narrow.status
    status.set_readout(READOUT)
    status.set_path("03_bands/uma/pasta/muito/funda/que/nao/cabe/bands.in")
    qtbot.waitUntil(lambda: "…" in status.path.text(), timeout=3000)
    assert (
        status.path.toolTip().endswith("bands.in") and status.path.toolTip() != status.path.text()
    )


def test_a_wide_window_shows_everything(qtbot, main_window):
    status = main_window.status
    main_window.resize(1440, 700)
    status.set_readout(READOUT)
    status.set_path("03_bands")
    qtbot.waitUntil(lambda: status.readout.text() == READOUT, timeout=3000)
    assert status.readout.toolTip() == "" and status.path.text() == "03_bands"


def test_widening_the_window_restores_the_text(qtbot, narrow):
    status = narrow.status
    status.set_readout(READOUT)
    status.set_path("03_bands/subpasta/bands.in")  # the top bar keeps the window ~900 px wide
    qtbot.waitUntil(lambda: status.readout.text() != READOUT, timeout=3000)
    narrow.resize(1440, 700)
    qtbot.waitUntil(lambda: status.readout.text() == READOUT, timeout=3000)
