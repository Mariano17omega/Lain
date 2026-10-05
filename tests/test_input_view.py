"""Spec 11 (R3, R4): the text viewer for QE inputs: highlight, write-error marks, banner, F8."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QPoint
from PyQt6.QtGui import QHelpEvent, QTextCharFormat, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QToolTip

from qe_studio.core import text_preview
from qe_studio.core.file_kinds import viewer_kind
from qe_studio.core.sniff import FileKind, SniffCache
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.highlighters import InputHighlighter, OutputHighlighter
from qe_studio.ui.widgets.text_viewer import TextViewer

from conftest import FIXTURES
from viewer_helpers import SHIFT, key, open_text

SI_SCF = FIXTURES / "si_bands" / "si.scf.in"
WAVE = QTextCharFormat.UnderlineStyle.WaveUnderline
BROKEN = """&control
    calculation = 'scf',
    prefix = 'si
/
&system
    ecutwfc = 25
    conv_thr = 1.0e
/
&electrons
/
ATOMIC_SPECIES
 Si  28.086  Si.pz-rrkj.UPF
"""


def write(tmp_path: Path, text: str, name: str = "run.in") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def painted(document: QTextDocument, line: int) -> list[tuple[str, str, bool]]:
    """(text, color, wavy) of each formatted stretch of 1-based ``line``, once highlighted."""
    block = document.findBlockByNumber(line - 1)
    text = block.text()
    return [
        (
            text[r.start : r.start + r.length],
            r.format.foreground().color().name(),
            r.format.underlineStyle() == WAVE,
        )
        for r in block.layout().formats()
    ]


def highlighted(text: str, theme: ThemeManager | None = None):
    """A bare document with the input highlighter run synchronously."""
    theme = theme or ThemeManager("dark")
    document = QTextDocument()
    document.setPlainText(text)
    highlighter = InputHighlighter(document, theme)
    highlighter.rehighlight()
    return document, highlighter, theme


# -- highlight (R3.1) --------------------------------------------------------------------------
def test_si_scf_gets_the_syntax_colors():
    document, _, theme = highlighted(SI_SCF.read_text())

    def color(token):
        return theme.color(token).name()

    assert painted(document, 1) == [("&control", color("syn_namelist"), False)]
    assert ("calculation", color("syn_key"), False) in painted(document, 2)
    assert ("'scf'", color("syn_string"), False) in painted(document, 2)
    assert ("celldm(1)", color("syn_key"), False) in painted(document, 9)
    assert ("10.16863713", color("syn_number"), False) in painted(document, 9)
    assert ("1.0d-12", color("syn_number"), False) in painted(document, 17)  # d exponent
    assert painted(document, 6) == [("/", color("syn_namelist"), False)]
    assert painted(document, 19) == [("ATOMIC_SPECIES", color("syn_card"), False)]
    assert ("K_POINTS", color("syn_card"), False) in painted(document, 24)
    assert ("automatic", color("syn_card_option"), False) in painted(document, 24)
    assert ("0.25", color("syn_number"), False) in painted(document, 23)  # card body number


def test_logicals_and_comments():
    document, _, theme = highlighted("&control\n  lflag = .true. ! why\n/\n")
    colors = {text: color for text, color, _ in painted(document, 2)}
    assert colors[".true."] == theme.color("syn_logical").name()
    assert colors["! why"] == theme.color("syn_comment").name()


def test_state_runs_across_blocks():
    # The card's body line is a card line only because the block before it left that state.
    document, _, theme = highlighted("K_POINTS gamma\n 0.5 0.5 0.5\n")
    assert ("0.5", theme.color("syn_number").name(), False) in painted(document, 2)
    document, _, _ = highlighted(" 0.5 0.5 0.5\n")  # outside any card: plain text
    assert painted(document, 1) == []


def test_errors_are_underlined_in_the_error_color():
    text = BROKEN
    document = QTextDocument()
    document.setPlainText(text)
    theme = ThemeManager("dark")
    from qe_studio.core.qe.input_lint import lint

    issues = lint(text).issues
    by_block: dict[int, list] = {}
    for issue in issues:
        by_block.setdefault(issue.line - 1, []).append(issue)
    highlighter = InputHighlighter(document, theme, by_block)
    highlighter.rehighlight()
    block = document.findBlockByNumber(2)  # prefix = 'si
    wavy = [r for r in block.layout().formats() if r.format.underlineStyle() == WAVE]
    assert [block.text()[r.start : r.start + r.length] for r in wavy] == ["'si"]
    assert wavy[0].format.underlineColor().name() == theme.color("error").name()
    # The syntax color survives under the wave.
    assert wavy[0].format.foreground().color().name() == theme.color("syn_string").name()


def test_highlight_follows_the_theme(qtbot):
    theme = ThemeManager("dark")
    document, highlighter, _ = highlighted("&control\n/\n", theme)
    dark = painted(document, 1)[0][1]
    theme.toggle()
    qtbot.waitUntil(lambda: painted(document, 1)[0][1] != dark, timeout=5000)
    assert highlighter.theme is theme


# -- which viewer (R4.1) -----------------------------------------------------------------------
def test_input_files_get_the_input_highlighter_and_outputs_do_not(qtbot, main_window):
    viewer = open_text(qtbot, main_window, SI_SCF)
    assert isinstance(viewer._highlighter, InputHighlighter)
    out = open_text(qtbot, main_window, FIXTURES / "si_bands" / "si.scf.out")
    assert isinstance(out._highlighter, OutputHighlighter)
    assert out.input_view.isHidden()


def test_a_plain_text_file_is_not_an_input(qtbot, main_window, tmp_path):
    notes = write(tmp_path, "just words\nK_POINTS gamma ! total energy\n", "notes.txt")
    viewer = open_text(qtbot, main_window, notes)
    assert viewer._highlighter is None
    assert viewer.input_view.isHidden()


def test_a_broken_input_ase_cannot_read_still_opens_as_an_input(qtbot, main_window, tmp_path):
    path = write(tmp_path, "&control\n  pre'fix = 'x'\n/\n&system\n/\n")
    assert SniffCache().sniff(path).kind is FileKind.UNKNOWN  # ASE raised
    viewer = open_text(qtbot, main_window, path)
    assert isinstance(viewer._highlighter, InputHighlighter)
    assert viewer.input_view.issues  # the error is marked
    assert not viewer.input_view.isHidden()


def test_unknown_suffix_with_a_namelist_head_opens_in_the_viewer(tmp_path):
    assert viewer_kind(write(tmp_path, "&control\n/\n", "si.pw")) == "text"
    assert viewer_kind(write(tmp_path, "nothing here\n", "si.xyz")) == "external"


# -- diagnostics (R3.2-R3.3) -------------------------------------------------------------------
def test_clean_input_has_no_banner_and_no_marks(qtbot, main_window):
    viewer = open_text(qtbot, main_window, SI_SCF)
    assert viewer.input_view.issues_bar.isHidden()
    assert viewer.editor.diagnostics == {}
    assert viewer.banner_bar.isHidden()


def test_banner_counts_the_problems(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    view = viewer.input_view
    assert not view.isHidden()
    assert view.issues_label.text() == "2 problemas de escrita no input"
    assert view.issues_bar.property("level") == "error"
    assert viewer.banner_bar.isHidden()  # the notice about the file itself stays apart


def test_one_problem_in_the_singular_and_warnings_are_not_errors(qtbot, main_window, tmp_path):
    only_warning = "&control\n/\n&control\n/\n&system\n/\n&electrons\n/\n"
    viewer = open_text(qtbot, main_window, write(tmp_path, only_warning))
    assert viewer.input_view.issues_label.text() == "1 problema de escrita no input"
    assert viewer.input_view.issues_bar.property("level") == "warning"


def test_margin_marks_the_lines_and_makes_room(qtbot, main_window, tmp_path):
    clean = open_text(qtbot, main_window, SI_SCF)
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    assert sorted(viewer.editor.diagnostics) == [2, 6]  # blocks of lines 3 and 7
    assert viewer.editor.gutter_width() > clean.editor.gutter_width()
    # Reloading drops the marks of the old text.
    viewer.editor.setPlainText("&control\n/\n")
    assert viewer.editor.diagnostics == {}


def tip_at(qtbot, editor, block: int, column: int, margin: bool = False) -> str:
    """The tooltip text a hover over ``column`` of ``block`` (or its margin marker) would show."""
    QToolTip.hideText()  # Qt hides it after a short delay
    qtbot.waitUntil(lambda: not QToolTip.isVisible(), timeout=2000)
    cursor = QTextCursor(editor.document().findBlockByNumber(block))
    cursor.setPosition(cursor.position() + column)
    rect = editor.cursorRect(cursor)
    # Half a character to the right of the caret is over character ``column``.
    point = QPoint(rect.x() + 2, rect.center().y())
    if margin:
        point = QPoint(6, rect.center().y())
        event = QHelpEvent(QEvent.Type.ToolTip, point, editor.gutter.mapToGlobal(point))
        editor.gutter.event(event)
    else:
        event = QHelpEvent(QEvent.Type.ToolTip, point, editor.viewport().mapToGlobal(point))
        editor.viewportEvent(event)
    return QToolTip.text() if QToolTip.isVisible() else ""


def test_tooltips_over_the_marker_and_the_marked_text(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    editor = viewer.editor
    line = editor.document().findBlockByNumber(2).text()
    column = line.index("'si")
    assert tip_at(qtbot, editor, 2, column + 1) == "Aspas não fechadas"
    assert tip_at(qtbot, editor, 2, column + 1, margin=True) == "Aspas não fechadas"
    assert tip_at(qtbot, editor, 2, 1) == ""  # indentation: nothing to say
    assert tip_at(qtbot, editor, 3, 0, margin=True) == ""  # a clean line


# -- navigation (R3.4) -------------------------------------------------------------------------
def test_go_to_first_and_f8_walk_the_problems(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    editor = viewer.editor
    view = viewer.input_view

    def line() -> int:
        return editor.number_at(editor.textCursor().blockNumber())

    viewer.show()
    view.first_button.click()
    assert line() == 3
    editor.setFocus()
    key(qtbot, editor, "F8")
    assert line() == 7
    key(qtbot, editor, "F8")
    assert line() == 3  # wraps
    key(qtbot, editor, "F8", SHIFT)
    assert line() == 7


def test_f8_without_problems_does_nothing(qtbot, main_window):
    viewer = open_text(qtbot, main_window, SI_SCF)
    viewer.editor.setFocus()
    before = viewer.editor.textCursor().position()
    key(qtbot, viewer.editor, "F8")
    assert viewer.editor.textCursor().position() == before


# -- big inputs (R4.2) -------------------------------------------------------------------------
def test_input_over_the_limit_is_colored_but_not_checked(qtbot, main_window, tmp_path, monkeypatch):
    monkeypatch.setattr(text_preview, "INPUT_READ_LIMIT", 50)
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    assert isinstance(viewer._highlighter, InputHighlighter)
    assert viewer.input_view.issues == [] and viewer.editor.diagnostics == {}
    assert not viewer.banner_bar.isHidden()
    assert "escrita não foi verificada" in viewer.banner.text()


def test_reload_with_load_all_keeps_the_input_marks(qtbot, main_window, tmp_path, monkeypatch):
    # "Carregar tudo" runs the worker again: the same highlighter takes the new issues.
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    highlighter = viewer._highlighter
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        viewer._start_load(full=True)
    assert viewer._highlighter is highlighter
    assert len(viewer.input_view.issues) == 2
    assert isinstance(viewer, TextViewer)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_syntax_token_exists_in_both_themes(theme):
    manager = ThemeManager(theme)
    for name in (
        "syn_namelist", "syn_key", "syn_string", "syn_number", "syn_logical", "syn_comment",
        "syn_card", "syn_card_option", "diff_add_bg", "diff_del_bg", "diff_change_bg",
    ):  # fmt: skip
        assert manager.has_color(name)


# -- extract strip (R5) ------------------------------------------------------------------------
AL_SCF_IN = FIXTURES / "al_bands" / "al.scf.in"


def chip_texts(viewer: TextViewer) -> list[str]:
    return [button.text() for button in viewer.input_view.chip_buttons]


def test_extract_strip_matches_the_file(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF_IN)
    texts = chip_texts(viewer)
    assert "calculation: scf" in texts
    assert "ecutwfc: 100" in texts
    assert "nat: 1" in texts
    assert "K_POINTS: automatic 10×10×10 (0 0 0)" in texts
    assert not viewer.input_view.extract_bar.isHidden()


def test_clicking_a_chip_goes_to_its_line(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF_IN)
    chip = next(b for b in viewer.input_view.chip_buttons if b.text() == "ecutwfc: 100")
    chip.click()
    assert viewer.editor.textCursor().blockNumber() == 11  # line 12
    next(b for b in viewer.input_view.chip_buttons if b.text().startswith("K_POINTS")).click()
    assert viewer.editor.textCursor().blockNumber() == 28  # line 29


def test_defaults_are_dimmed_chips(qtbot, main_window, tmp_path):
    viewer = open_text(
        qtbot, main_window, write(tmp_path, "&control\n prefix='x'\n/\n&system\n/\n&electrons\n/\n")
    )
    chip = next(b for b in viewer.input_view.chip_buttons if b.text().startswith("calculation"))
    assert chip.text() == "calculation: scf (padrão)"
    assert chip.property("dim") is True
    chip.click()
    assert viewer.editor.textCursor().blockNumber() == 0  # the &control line
    prefix = next(b for b in viewer.input_view.chip_buttons if b.text().startswith("prefix"))
    assert prefix.property("dim") is False


def test_the_strip_collapses(qtbot, main_window):
    viewer = open_text(qtbot, main_window, AL_SCF_IN)
    view = viewer.input_view
    assert not view.chips_host.isHidden()
    view.toggle.click()
    assert view.chips_host.isHidden() and not view.extract_bar.isHidden()
    view.toggle.click()
    assert not view.chips_host.isHidden()


def test_extract_survives_errors(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    assert "ecutwfc: 25" in chip_texts(viewer)
    assert viewer.input_view.issues  # and the errors are there too


def test_programs_without_a_strip_keep_the_header(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, "title\n&inputph\n tr2_ph=1d-14\n/\n"))
    assert chip_texts(viewer) == []
    assert not viewer.input_view.extract_bar.isHidden() and viewer.input_view.toggle.isHidden()
    assert not viewer.input_view.compare_button.isHidden()


def test_outputs_and_big_inputs_have_no_strip(qtbot, main_window, tmp_path, monkeypatch):
    out = open_text(qtbot, main_window, FIXTURES / "si_bands" / "si.scf.out")
    assert out.input_view.isHidden()
    monkeypatch.setattr(text_preview, "INPUT_READ_LIMIT", 50)
    big = open_text(qtbot, main_window, write(tmp_path, BROKEN, "big.in"))
    assert big.input_view.isHidden() and chip_texts(big) == []


def test_flow_layout_wraps_onto_more_rows_when_narrow(qtbot):
    from PyQt6.QtWidgets import QPushButton, QWidget

    from qe_studio.ui.widgets.flow_layout import FlowLayout

    host = QWidget()
    layout = FlowLayout(host)
    for i in range(8):
        layout.addWidget(QPushButton(f"parameter_{i}: value"))
    qtbot.addWidget(host)
    wide, narrow = layout.heightForWidth(2000), layout.heightForWidth(200)
    assert narrow > wide
    host.resize(2000, wide)
    host.show()
    tops = {layout.itemAt(i).geometry().top() for i in range(layout.count())}
    assert len(tops) == 1  # one row when there is room


# -- comparing two inputs (R6) -----------------------------------------------------------------
from PyQt6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from qe_studio.ui.widgets.diff_view import MESSAGE, PARAMS, TEXT, DiffView, diff_key  # noqa: E402


def open_diff(qtbot, window, a: Path, b: Path) -> DiffView:
    widget = window.workspace.open_diff(a, b)
    assert isinstance(widget, DiffView)
    with qtbot.waitSignal(widget.loaded, timeout=5000):
        pass
    return widget


def changed_copy(tmp_path: Path) -> Path:
    other = tmp_path / "si.changed.in"
    other.write_text(
        SI_SCF.read_text().replace("ecutwfc = 25", "ecutwfc = 30").replace("1.0d-12", "1.0e-12")
    )
    return other


def tree_rows(view: DiffView) -> list[list[str]]:
    return [
        [item.text(c) for c in range(5)]
        for item in (view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount()))
        if item is not None
    ]


def test_compare_button_asks_for_a_file_and_opens_the_diff_tab(
    qtbot, main_window, tmp_path, monkeypatch
):
    other = changed_copy(tmp_path)
    viewer = open_text(qtbot, main_window, SI_SCF)
    asked = []

    def choose(parent, title, folder, filters):
        asked.append((title, folder, filters))
        return str(other), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose)
    viewer.input_view.compare_button.click()
    key = diff_key(SI_SCF, other)
    diff = main_window.workspace.widget_for(key)
    assert isinstance(diff, DiffView)
    assert asked == [
        (
            "Comparar com…",
            str(SI_SCF.parent),
            "Inputs do QE (*.in *.inp *.pw*);;Todos os arquivos (*)",
        )
    ]
    tabs = main_window.workspace.tabs
    assert tabs.tabText(tabs.indexOf(diff)) == "Diff · si.scf.in ↔ si.changed.in"
    assert tabs.currentWidget() is diff
    # The same pair again shows the same tab.
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(other), ""))
    viewer.input_view.compare_button.click()
    assert [k for k, _ in main_window.workspace.items() if k.startswith("diff:")] == [key]


def test_cancelling_the_dialog_or_choosing_a_non_input_opens_nothing(
    qtbot, main_window, tmp_path, monkeypatch
):
    viewer = open_text(qtbot, main_window, SI_SCF)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: ("", ""))
    viewer.input_view.compare_button.click()
    notes = write(tmp_path, "just words\n", "notes.txt")
    warned = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(notes), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warned.append(text))
    viewer.input_view.compare_button.click()
    assert warned == ["notes.txt não parece um input do Quantum ESPRESSO."]
    assert not any(k.startswith("diff:") for k, _ in main_window.workspace.items())


def test_parameters_mode_lists_only_what_differs(qtbot, main_window, tmp_path):
    diff = open_diff(qtbot, main_window, SI_SCF, changed_copy(tmp_path))
    assert diff.mode == PARAMS and diff.stack.currentIndex() == PARAMS
    # Only ecutwfc: `1.0d-12` and `1.0e-12` are the same number.
    assert tree_rows(diff) == [["system", "ecutwfc", "25", "30", "diferente"]]
    assert diff.text_button.isEnabled() and diff.ignore_box.isHidden()


def test_parameters_in_one_file_and_cards_are_rows(qtbot, main_window, tmp_path):
    a = write(
        tmp_path,
        "&control\n prefix='x'\n/\nATOMIC_POSITIONS crystal\n Si 0 0 0\n Si 0.25 0.25 0.25\n",
        "a.in",
    )
    b = write(
        tmp_path,
        "&control\n outdir='o'\n/\nATOMIC_POSITIONS crystal\n Si 0 0 0\n Si 0.3 0.3 0.3\n",
        "b.in",
    )
    diff = open_diff(qtbot, main_window, a, b)
    assert tree_rows(diff) == [
        ["control", "prefix", "x", "—", "só em A"],
        ["control", "outdir", "—", "o", "só em B"],
        ["card", "ATOMIC_POSITIONS: 1 linha difere", "", "", "diferente"],
    ]
    card = diff.tree.topLevelItem(2)
    assert card.childCount() == 1 and not card.isExpanded()
    diff.tree.itemClicked.emit(card, 0)  # a click opens the excerpt
    assert card.isExpanded()
    assert [card.child(0).text(c) for c in (2, 3)] == ["Si 0.25 0.25 0.25", "Si 0.3 0.3 0.3"]
    diff.tree.itemClicked.emit(card, 0)
    assert not card.isExpanded()


def test_equivalent_inputs_say_so(qtbot, main_window, tmp_path):
    same = write(
        tmp_path, SI_SCF.read_text().replace("ecutwfc = 25      ", "ECUTWFC = 25.0"), "same.in"
    )
    diff = open_diff(qtbot, main_window, SI_SCF, same)
    assert diff.stack.currentIndex() == MESSAGE
    assert diff.message.text().startswith("Os inputs são equivalentes")


def test_text_mode_puts_the_files_side_by_side(qtbot, main_window, tmp_path):
    diff = open_diff(qtbot, main_window, SI_SCF, changed_copy(tmp_path))
    diff.text_button.click()
    assert diff.mode == TEXT and diff.stack.currentIndex() == TEXT
    assert not diff.ignore_box.isHidden()
    a, b = diff.pane_a, diff.pane_b
    assert a.blockCount() == b.blockCount()
    changed = [
        i
        for i in range(a.blockCount())
        if a.document().findBlockByNumber(i).text() != b.document().findBlockByNumber(i).text()
    ]
    assert len(changed) == 2  # ecutwfc and conv_thr, as written
    assert sorted(a._row_tokens) == changed and set(a._row_tokens.values()) == {"diff_change_bg"}
    assert len(a.extraSelections()) == 2
    assert [a.number_at(i) for i in changed] == [12, 17]  # the real line numbers


def test_text_mode_pads_added_and_removed_lines(qtbot, main_window, tmp_path):
    a = write(tmp_path, "&control\n a = 1\n b = 2\n/\n", "a.in")
    b = write(tmp_path, "&control\n a = 1\n/\n&system\n/\n", "b.in")
    diff = open_diff(qtbot, main_window, a, b)
    diff.text_button.click()
    assert diff.pane_a.toPlainText().split("\n") == ["&control", " a = 1", " b = 2", "/", "", ""]
    assert diff.pane_b.toPlainText().split("\n") == ["&control", " a = 1", "", "/", "&system", "/"]
    assert set(diff.pane_a._row_tokens.values()) == {"diff_del_bg"}
    assert set(diff.pane_b._row_tokens.values()) == {"diff_add_bg"}
    assert [diff.pane_a.number_at(i) for i in range(6)] == [
        1,
        2,
        3,
        4,
        None,
        None,
    ]  # padding: no number


def test_ignoring_comments_clears_the_comment_only_differences(qtbot, main_window, tmp_path):
    a = write(tmp_path, "&control\n calculation = 'scf' ! the usual\n/\n", "a.in")
    b = write(tmp_path, "&control\n calculation = 'scf'\n/\n", "b.in")
    diff = open_diff(qtbot, main_window, a, b)
    diff.text_button.click()
    assert len(diff.pane_a._row_tokens) == 1  # the comment makes the line differ
    diff.ignore_box.setChecked(True)
    assert diff.pane_a._row_tokens == {} and diff.pane_b._row_tokens == {}
    diff.ignore_box.setChecked(False)
    assert len(diff.pane_a._row_tokens) == 1


def test_the_panes_scroll_together(qtbot, main_window, tmp_path):
    rows = "".join(f" k{i} = {i}\n" for i in range(200))
    a = write(tmp_path, f"&control\n{rows}/\n", "a.in")
    b = write(tmp_path, f"&control\n{rows}/\n", "b.in")
    diff = open_diff(qtbot, main_window, a, b)
    diff.text_button.click()
    diff.resize(600, 300)
    diff.show()
    diff.pane_a.verticalScrollBar().setValue(40)
    assert diff.pane_b.verticalScrollBar().value() == 40
    diff.pane_b.verticalScrollBar().setValue(10)
    assert diff.pane_a.verticalScrollBar().value() == 10


def test_inputs_with_write_errors_can_be_compared(qtbot, main_window, tmp_path):
    broken = write(tmp_path, BROKEN, "broken.in")
    diff = open_diff(qtbot, main_window, broken, SI_SCF)
    assert diff.comparison is not None and not diff.comparison.params.identical


def test_big_or_missing_files_are_reported_not_raised(qtbot, main_window, tmp_path, monkeypatch):
    from qe_studio.core.qe import input_diff

    monkeypatch.setattr(input_diff, "INPUT_READ_LIMIT", 50)
    diff = open_diff(qtbot, main_window, SI_SCF, changed_copy(tmp_path))
    assert diff.comparison is None and diff.stack.currentIndex() == MESSAGE
    assert "grande demais para comparar" in diff.message.text()
    monkeypatch.undo()
    gone = open_diff(qtbot, main_window, SI_SCF, tmp_path / "missing.in")
    assert gone.message.text().startswith("Não foi possível comparar")


def test_the_diff_follows_the_theme(qtbot, main_window, tmp_path):
    diff = open_diff(qtbot, main_window, SI_SCF, changed_copy(tmp_path))
    item = diff.tree.topLevelItem(0)
    dark = item.background(0).color().name()
    main_window.toggle_theme()
    assert item.background(0).color().name() != dark


def test_renaming_either_file_closes_the_comparison(qtbot, main_window, tmp_path, monkeypatch):
    a = write(tmp_path, "&control\n/\n", "a.in")
    b = write(tmp_path, "&control\n prefix='x'\n/\n", "b.in")
    open_diff(qtbot, main_window, a, b)
    key = diff_key(a, b)
    assert main_window.workspace.widget_for(key) is not None
    monkeypatch.setattr(
        "qe_studio.ui.rename_controller.ask_rename", lambda parent, path: "renamed.in"
    )
    main_window.rename_path(b)
    assert main_window.workspace.widget_for(key) is None
