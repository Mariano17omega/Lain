"""Spec 12 R3: the "Resumo" menu item and the summary tab."""

import threading
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QMenu

from qe_studio.core.qe.summary import summarize
from qe_studio.ui.widgets import summary_view
from qe_studio.ui.widgets.summary_view import CONTENT, MESSAGE, SummaryView, summary_key
from qe_studio.ui.widgets.text_viewer import TextViewer

from conftest import FIXTURES, copy_fixture
from viewer_helpers import open_text


def open_summary(qtbot, window, path: Path) -> SummaryView:
    view = window.workspace.open_summary(path)
    assert isinstance(view, SummaryView)
    with qtbot.waitSignal(view.loaded, timeout=10_000):
        pass
    return view


def row_of(view: SummaryView, label: str):
    return next(row for section in view.sections for row in section.rows if row.row.label == label)


def trigger_resumo(window, path: Path, monkeypatch) -> None:
    def pick(menu, pos):
        next(a for a in menu.actions() if a.text() == "Resumo").trigger()

    monkeypatch.setattr(QMenu, "exec", pick)
    window.service.detect_now(path.parent)  # the menu reads the sniff cache only
    window._show_item_menu([path], QPoint())


def test_resumo_item_opens_the_tab_once_and_shows_the_workspace(
    qtbot, main_window, demo_project, monkeypatch
):
    window = main_window
    window.set_panel_visible("workspace", False)
    folder = demo_project / "02_scf"
    path = folder / "scf.out"
    before = sorted(p.name for p in folder.iterdir())
    trigger_resumo(window, path, monkeypatch)
    view = window.workspace.widget_for(summary_key(path))
    assert isinstance(view, SummaryView) and window.workspace.isVisible()
    tabs = window.workspace.tabs
    assert summary_key(path) == f"summary:{path}"
    assert tabs.tabText(tabs.indexOf(view)) == "Resumo · scf.out"
    assert tabs.tabToolTip(tabs.indexOf(view)) == str(path)  # the plain path: tab menu reads it
    assert tabs.currentWidget() is view
    with qtbot.waitSignal(view.loaded, timeout=10_000):
        pass
    window.open_file(path)  # another tab on top, then the same action again
    trigger_resumo(window, path, monkeypatch)
    assert tabs.currentWidget() is view
    assert [k for k, _ in window.workspace.items() if k.startswith("summary:")] == [
        summary_key(path)
    ]
    assert sorted(p.name for p in folder.iterdir()) == before  # nothing written (R3.5)


def test_view_shows_loading_then_the_sections(qtbot, main_window, demo_project):
    path = demo_project / "02_scf" / "scf.out"
    view = main_window.workspace.open_summary(path)
    assert view.stack.currentIndex() == MESSAGE and view.message.text() == "Lendo scf.out…"
    assert not view.copy_button.isEnabled()
    with qtbot.waitSignal(view.loaded, timeout=10_000):
        pass
    assert view.stack.currentIndex() == CONTENT and view.copy_button.isEnabled()
    assert [s.title.text() for s in view.sections] == [
        "GERAL",
        "SISTEMA",
        "RESULTADOS",
        "AVISOS E ERROS",
    ]
    state = row_of(view, "Estado")
    assert state.value.text() == "Concluído" and state.value.property("level") == "success"
    assert row_of(view, "Tempo (WALL)").value.text() == "1.90 s"


def test_unreadable_file_shows_the_error(qtbot, main_window, tmp_path):
    view = open_summary(qtbot, main_window, tmp_path / "missing.out")
    assert view.stack.currentIndex() == MESSAGE
    assert view.message.text().startswith("Não foi possível ler o arquivo: ")
    assert view.refresh_button.isEnabled() and not view.copy_button.isEnabled()


def test_a_parser_bug_is_shown_not_left_loading(qtbot, main_window, demo_project, monkeypatch):
    from qe_studio.ui.widgets import summary_view

    def boom(path):
        raise RuntimeError("boom")

    monkeypatch.setattr(summary_view, "summarize", boom)
    view = open_summary(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    assert view.message.text() == "Não foi possível ler o arquivo: boom"


def test_copiar_puts_the_text_on_the_clipboard(qtbot, main_window, demo_project):
    view = open_summary(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    QApplication.clipboard().clear()
    view.copy_button.click()
    text = QApplication.clipboard().text()
    assert "WALL" in text and "Concluído" in text and "GERAL" in text


def test_atualizar_reads_the_file_again(qtbot, main_window, tmp_path):
    out = copy_fixture("al_bands", tmp_path) / "al.scf.out"
    full = out.read_text()
    out.write_text("".join(full.splitlines(keepends=True)[:300]))  # a job still running
    view = open_summary(qtbot, main_window, out)
    assert row_of(view, "Estado").value.text() == "Incompleto"
    out.write_text(full)
    with qtbot.waitSignal(view.loaded, timeout=10_000):
        view.refresh_button.click()
    assert view.stack.currentIndex() == CONTENT
    assert row_of(view, "Estado").value.text() == "Concluído"


def test_the_result_of_a_superseded_read_is_dropped(qtbot, main_window, demo_project, monkeypatch):
    view = open_summary(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    shown = view.summary
    gate, slow = threading.Event(), demo_project / "01_relax" / "si.rel.out"
    calls = []

    def gated(path):
        calls.append(path)
        if len(calls) == 1:  # the first read is slow and gets superseded by "Atualizar"
            gate.wait(5)
            return summarize(slow)
        return summarize(path)

    monkeypatch.setattr(summary_view, "summarize", gated)
    view.refresh()
    first = view._task
    qtbot.waitUntil(lambda: first.started, timeout=5000)
    with qtbot.waitSignal(view.loaded, timeout=10_000):
        view.refresh()
    assert view.summary == shown and first.cancelled
    gate.set()
    assert first.wait(5)
    qtbot.wait(50)
    assert view.summary == shown and view.stack.currentIndex() == CONTENT


def test_expandable_rows_start_collapsed(qtbot, main_window, demo_project):
    view = open_summary(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    pseudos = row_of(view, "Pseudopotenciais")
    assert pseudos.toggle is not None and pseudos.details.isHidden()
    pseudos.toggle.click()
    assert not pseudos.details.isHidden()
    assert [c.row.label for c in pseudos.children_widgets] == ["Al"]
    pseudos.toggle.click()
    assert pseudos.details.isHidden()
    assert row_of(view, "Estado").toggle is None


def test_double_click_opens_the_output_at_that_line(qtbot, main_window, demo_project):
    window = main_window
    path = demo_project / "02_scf" / "scf.out"
    view = open_summary(qtbot, window, path)
    energy = row_of(view, "Energia total")
    line = energy.row.line
    assert line is not None and energy.head.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.workspace.widget_for(str(path)) is None
    qtbot.mouseDClick(energy.head, Qt.MouseButton.LeftButton)  # the viewer is still loading
    viewer = window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    assert window.workspace.tabs.currentWidget() is viewer
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.editor.textCursor().blockNumber() + 1 == line
    # A row without a line does nothing.
    assert row_of(view, "Cálculo").row.line is None
    count = len(window.workspace.keys())
    qtbot.mouseDClick(row_of(view, "Cálculo").head, Qt.MouseButton.LeftButton)
    assert len(window.workspace.keys()) == count


def test_abrir_saida_opens_the_text_tab(qtbot, main_window, demo_project):
    window = main_window
    path = demo_project / "02_scf" / "scf.out"
    view = open_summary(qtbot, window, path)
    view.open_button.click()
    assert isinstance(window.workspace.widget_for(str(path)), TextViewer)
    assert window.workspace.widget_for(summary_key(path)) is view  # the summary tab stays


def test_text_viewer_go_to_line_when_loaded(qtbot, main_window, demo_project):
    viewer = open_text(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    viewer.go_to_line(40)
    assert viewer.editor.textCursor().blockNumber() == 39


def test_renaming_the_output_closes_its_summary(qtbot, main_window, demo_project, monkeypatch):
    from qe_studio.ui import main_window as main_window_module

    path = demo_project / "02_scf" / "scf.out"
    open_summary(qtbot, main_window, path)
    monkeypatch.setattr(main_window_module, "ask_rename", lambda parent, p: "renamed.out")
    main_window.rename_path(path)
    assert main_window.workspace.widget_for(summary_key(path)) is None


def test_summary_of_every_fixture_output_opens(qtbot, main_window):
    for out in (
        FIXTURES / "kao_vc_relax" / "vc-relax.out",
        FIXTURES / "al_bands" / "bands.out",
    ):
        view = open_summary(qtbot, main_window, out)
        assert view.stack.currentIndex() == CONTENT and view.sections


def test_summary_survives_a_theme_change(qtbot, main_window, demo_project):
    view = open_summary(qtbot, main_window, demo_project / "02_scf" / "scf.out")
    main_window.toggle_theme()
    pseudos = row_of(view, "Pseudopotenciais")
    assert pseudos.toggle is not None and not pseudos.toggle.icon().isNull()
