"""Spec 10 (R1-R4): search, output highlighting, line numbers and large files in the text viewer."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QInputDialog

from qe_studio.core import textfile
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.highlighters import OutputHighlighter
from qe_studio.ui.widgets.text_viewer import TOO_BIG, TextViewer, load_for_viewer

from conftest import FIXTURES

AL_SCF = FIXTURES / "al_bands" / "al.scf.out"
ENTER = 0x01000004  # Qt.Key.Key_Return
ESCAPE = 0x01000000
CTRL = 0x04000000  # Qt.KeyboardModifier.ControlModifier
SHIFT = 0x02000000


def open_text(qtbot, window, path: Path) -> TextViewer:
    window.open_file(path)
    viewer = window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    return viewer


def key(qtbot, widget, name: str, modifiers: int = 0) -> None:
    from PyQt6.QtCore import Qt

    qtbot.keyClick(widget, getattr(Qt.Key, f"Key_{name}"), Qt.KeyboardModifier(modifiers))


@pytest.fixture
def small_limits(monkeypatch):
    """Any file above 400 bytes is "large": head 100 B, tail 200 B."""
    monkeypatch.setattr(textfile, "LARGE_FILE", 400)
    monkeypatch.setattr(textfile, "HEAD_BYTES", 100)
    monkeypatch.setattr(textfile, "TAIL_BYTES", 200)


def numbered(path: Path, lines: int = 120) -> list[str]:
    rows = [f"L{i:05d}" for i in range(1, lines + 1)]
    path.write_text("\n".join(rows) + "\n")
    return rows


# -- search (R1) -------------------------------------------------------------------------------
def test_ctrl_f_opens_the_search_and_counts(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF)
    assert viewer.search.isHidden()
    viewer.editor.setFocus()
    key(qtbot, viewer.editor, "F", CTRL)
    assert not viewer.search.isHidden() and viewer.search.field.hasFocus()

    expected = viewer.editor.toPlainText().lower().count("total energy")
    assert expected > 1
    viewer.search.field.setText("total energy")
    viewer.search.search()  # the typing delay would only postpone this
    editor = viewer.editor
    assert editor.match_count == expected
    assert viewer.search.counter.text() == f"1 de {expected}"
    assert len(editor.extraSelections()) == expected

    key(qtbot, viewer.search.field, "Return")
    assert viewer.search.counter.text() == f"2 de {expected}"
    key(qtbot, viewer.search.field, "Return", SHIFT)
    key(qtbot, viewer.search.field, "Return", SHIFT)  # wraps around
    assert viewer.search.counter.text() == f"{expected} de {expected}"
    # The caret follows the current match, and the margin shows its line.
    position = editor.textCursor().position()
    assert editor.toPlainText()[position : position + 12].lower() == "total energy"

    key(qtbot, viewer.search.field, "Escape")
    assert viewer.search.isHidden() and editor.extraSelections() == []


def test_search_options_and_misses(qtbot, main_window, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Alpha alpha ALPHA\nbeta\n")
    viewer = open_text(qtbot, main_window, path)
    viewer.open_search()
    viewer.search.field.setText("alpha")
    viewer.search.search()
    assert viewer.editor.match_count == 3
    viewer.search.case.setChecked(True)  # toggling searches again
    assert viewer.editor.match_count == 1
    viewer.search.field.setText("nothing")
    viewer.search.search()
    assert viewer.search.counter.text() == "Nenhum resultado"
    viewer.search.next_match()  # no match: nothing happens
    viewer.search.field.setText("")
    viewer.search.search()
    assert viewer.search.counter.text() == "" and viewer.editor.extraSelections() == []


def test_search_in_a_truncated_file_says_so(qtbot, main_window, small_limits, tmp_path):
    path = tmp_path / "big.txt"
    numbered(path)
    viewer = open_text(qtbot, main_window, path)
    viewer.open_search()
    viewer.search.field.setText("L00002")
    viewer.search.search()
    assert viewer.search.counter.text() == "1 de 1 (no trecho carregado)"


def test_ctrl_f_in_the_grid_does_not_open_the_text_search(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF)
    main_window.files.view.setFocus()
    key(qtbot, main_window.files.view, "F", CTRL)
    assert viewer.search.isHidden()
    main_window.explorer.tree.setFocus()
    key(qtbot, main_window.explorer.tree, "F", CTRL)
    assert viewer.search.isHidden()


def test_search_is_off_while_loading(qtbot, main_window, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one\n")
    viewer = open_text(qtbot, main_window, path)
    viewer.open_search()
    viewer._start_load(full=False)
    assert viewer.loading and not viewer.search.isEnabled()
    assert viewer.editor.toPlainText() == "" and viewer.editor.placeholderText() == "Carregando…"
    viewer.search.dismiss()
    viewer.open_search()  # refused while loading
    assert viewer.search.isHidden()
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.search.isEnabled()


# -- highlighting (R2) -------------------------------------------------------------------------
def highlighted(qtbot, text: str):
    theme = ThemeManager("dark")
    document = QTextDocument()
    highlighter = OutputHighlighter(document, theme)
    document.setPlainText(text)
    highlighter.rehighlight()

    def colors(line: int) -> list[tuple[int, int, str, bool]]:
        block = document.findBlockByNumber(line)
        return [
            (r.start, r.length, r.format.foreground().color().name(), r.format.fontWeight() > 500)
            for r in block.layout().formats()
        ]

    return theme, colors


def test_output_highlighter_rules(qtbot):
    theme, colors = highlighted(
        qtbot,
        "     Program PWSCF v.7.3.1 starts on 12Jun2024\n"
        "!    total energy              =     -4.18 Ry\n"
        "     the Fermi energy is     6.3 ev\n"
        "     convergence has been achieved in   7 iterations\n"
        "     JOB DONE.\n"
        "     convergence NOT achieved after 100 iterations\n"
        "     Message from routine c_bands:\n"
        "plain line\n",
    )

    def color(token: str) -> str:
        return theme.color(token).name()

    header = "     Program PWSCF v.7.3.1 starts on 12Jun2024"
    assert colors(0) == [(0, len(header), color("hl_header"), False)]
    energy = colors(1)
    assert len(energy) == 1 and energy[0][2:] == (color("hl_energy"), True)
    assert colors(2)[0][2] == color("hl_info")
    assert colors(3) == [(5, 29, color("hl_success"), False)]
    assert colors(4) == [(5, 8, color("hl_success"), False)]
    assert colors(5) == [(5, 24, color("hl_error"), False)]
    assert colors(6) == [(5, 20, color("hl_warning"), False)]
    assert colors(7) == []


def test_percent_block_is_an_error_on_every_line(qtbot):
    bar = " " + "%" * 40
    lines = [
        "before",
        bar,
        "     Error in routine read_input (1):",
        "     no such thing",
        bar,
        "after",
    ]
    theme, colors = highlighted(qtbot, "\n".join(lines) + "\n")
    error = theme.color("hl_error").name()
    assert colors(0) == [] and colors(5) == []
    for number in range(1, 5):
        assert colors(number) == [(0, len(lines[number]), error, False)], number


def test_viewer_highlights_outputs_only(qtbot, main_window, tmp_path):
    out = open_text(qtbot, main_window, AL_SCF)
    assert out._highlighter is not None
    plain = tmp_path / "notes.txt"
    plain.write_text("! total energy was great\n")
    assert open_text(qtbot, main_window, plain)._highlighter is None
    job = tmp_path / "job.o5"
    job.write_text("error\n")
    assert open_text(qtbot, main_window, job)._highlighter is not None


def test_highlight_follows_the_theme(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF)
    block = next(
        b for b in _blocks(viewer.editor.document()) if b.text().startswith("!    total energy")
    )
    qtbot.waitUntil(
        lambda: bool(block.layout().formats()), timeout=5000
    )  # the first pass is queued
    dark = block.layout().formats()[0].format.foreground().color().name()
    main_window.toggle_theme()
    light = block.layout().formats()[0].format.foreground().color().name()
    assert dark != light


def _blocks(document):
    block = document.firstBlock()
    while block.isValid():
        yield block
        block = block.next()


# -- line numbers (R3) -------------------------------------------------------------------------
def test_margin_numbers_every_block(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF)
    editor = viewer.editor
    count = editor.document().blockCount()
    assert [editor.number_at(b) for b in range(count)] == list(range(1, count + 1))
    assert editor.last_number() == count
    assert editor.gutter.width() == editor.gutter_width() > 0
    assert not editor.gutter.grab().isNull()  # painting does not fail


def test_margin_keeps_real_numbers_after_the_marker(qtbot, main_window, small_limits, tmp_path):
    path = tmp_path / "big.txt"
    rows = numbered(path)
    viewer = open_text(qtbot, main_window, path)
    editor = viewer.editor
    line_map = editor.line_map
    assert line_map.truncated and line_map.tail_block is not None
    first = line_map.tail_block + 1  # the tail's first line is cut: take the next, whole one
    text = editor.document().findBlockByNumber(first).text()
    assert text in rows and editor.number_at(first) == rows.index(text) + 1
    assert editor.last_number() == 121  # the empty line after the last newline
    assert editor.number_at(line_map.tail_block - 2) is None  # the marker itself
    assert editor.number_at(0) == 1


def test_navigation_buttons_and_go_to_line(qtbot, main_window, small_limits, tmp_path, monkeypatch):
    path = tmp_path / "big.txt"
    numbered(path)
    viewer = open_text(qtbot, main_window, path)
    editor = viewer.editor
    viewer.end_button.click()
    assert editor.textCursor().atEnd()
    viewer.start_button.click()
    assert editor.textCursor().position() == 0
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (110, True))
    viewer.line_button.click()
    assert editor.number_at(editor.textCursor().blockNumber()) == 110
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (50, True))  # omitted
    viewer.ask_line()
    marker = editor.textCursor().block().text()
    assert "trecho omitido" in marker
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (2, True))
    viewer.ask_line()
    assert editor.number_at(editor.textCursor().blockNumber()) == 2


# -- large files (R4) --------------------------------------------------------------------------
def test_load_all_replaces_the_text(qtbot, main_window, tmp_path):
    path = tmp_path / "five.txt"
    path.write_text("0123456789abcdef\n" * (5 * 1024 * 1024 // 17 + 1))
    viewer = open_text(qtbot, main_window, path)
    assert "trecho omitido" in viewer.editor.toPlainText()
    assert not viewer.load_all_button.isHidden() and viewer.load_all_button.isEnabled()
    assert not viewer.external_button.isHidden()
    with qtbot.waitSignal(viewer.loaded, timeout=20_000):
        viewer.load_all_button.click()
    assert viewer.editor.toPlainText() == path.read_text()
    assert viewer.banner.text().startswith("Arquivo completo (5")
    assert viewer.load_all_button.isHidden() and not viewer.external_button.isHidden()
    assert not viewer.editor.line_map.truncated


def test_load_all_is_refused_over_the_limit(
    qtbot, main_window, small_limits, monkeypatch, tmp_path
):
    monkeypatch.setattr(textfile, "LOAD_ALL_LIMIT", 500)
    path = tmp_path / "huge.txt"
    numbered(path)  # ~840 bytes
    viewer = open_text(qtbot, main_window, path)
    assert not viewer.load_all_button.isHidden()
    assert not viewer.load_all_button.isEnabled()
    assert viewer.load_all_button.toolTip() == TOO_BIG
    viewer.load_all()  # even when called directly
    assert not viewer.loading and "trecho omitido" in viewer.editor.toPlainText()


def test_small_files_have_no_buttons(qtbot, main_window, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one\n")
    viewer = open_text(qtbot, main_window, path)
    assert viewer.banner_bar.isHidden() and viewer.load_all_button.isHidden()
    assert viewer.external_button.isHidden()


def test_open_in_external_editor(qtbot, main_window, small_limits, fake_apps, launched, tmp_path):
    path = tmp_path / "big.in"
    numbered(path)
    viewer = open_text(qtbot, main_window, path)
    viewer.external_button.click()
    assert launched == [("other", ["--open", path.as_uri()], str(path.parent))]


def test_open_in_external_editor_without_a_default_program(
    qtbot, main_window, small_limits, monkeypatch, tmp_path
):
    from PyQt6.QtGui import QDesktopServices

    from qe_studio.core.desktop_apps import AppCatalog
    from qe_studio.ui.widgets import context_menu

    monkeypatch.setattr(context_menu, "catalog", lambda: AppCatalog([], [], []))
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    path = tmp_path / "big.in"
    numbered(path)
    open_text(qtbot, main_window, path).external_button.click()
    assert opened == [str(path)]


def test_loader_marks_outputs(tmp_path):
    assert load_for_viewer(AL_SCF).highlight
    other = tmp_path / "a.txt"
    other.write_text("just text\n")
    assert not load_for_viewer(other).highlight
