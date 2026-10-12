"""Spec 38 R2.1, R2.3, R2.4: a ``.qsub`` opens highlighted, with its write problems marked."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QTextCharFormat, QTextDocument

from qe_studio.core.qsub_lint import lint_script
from qe_studio.core.sniff import INPUT_READ_LIMIT
from qe_studio.core.text_preview import read_preview
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.highlighters import InputHighlighter, ShellHighlighter

from viewer_helpers import key, open_text

WAVE = QTextCharFormat.UnderlineStyle.WaveUnderline
REFERENCE = Path(__file__).parents[1] / "Documentation" / "Referencia_de_scripts_QSUB"
BROKEN = """#!/bin/bash
#$ -N "teste"
#$ -pe physica
PWCOMMAND="/opt/pw.x -nk 4"
if [ -f scf.in ]; then
  echo "rodando
fi
exit 0
"""
# Three problems: line 3 (-pe without slots), line 6 (the quote never closes) and, because that quote
# swallows the `fi` of line 7, line 5 (an `if` with no `fi`).
CLEAN = "#!/usr/bin/env bash\n#$ -N teste\n#$ -cwd\necho ok\nexit 0\n"


def write(tmp_path: Path, text: str, name: str = "job.qsub") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def wavy_columns(document: QTextDocument, line: int) -> list[int]:
    """The columns of 1-based ``line`` that are underlined with a wave."""
    block = document.findBlockByNumber(line - 1)
    columns: list[int] = []
    for r in block.layout().formats():
        if r.format.underlineStyle() == WAVE:
            columns.extend(range(r.start, r.start + r.length))
    return sorted(columns)


def activate(qtbot, window, widget) -> None:
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=3000)
    widget.setFocus()


# -- preview -----------------------------------------------------------------------------------
def test_a_script_is_judged_by_its_name_not_by_what_its_heredoc_holds(tmp_path):
    pdos = write(tmp_path, (REFERENCE / "PDOS.qsub").read_text(), "PDOS.qsub")
    loaded = read_preview(pdos)
    assert loaded.is_script and not loaded.is_input and loaded.input_doc is None
    assert loaded.issues == [] and not loaded.highlight and not loaded.is_markdown


def test_only_qsub_is_a_script(tmp_path):
    for name in ("run.sh", "job.pbs", "job.slurm", "job.o123", "notas.txt"):
        loaded = read_preview(write(tmp_path, BROKEN, name))
        assert not loaded.is_script and loaded.issues == [], name


def test_the_preview_carries_the_issues(tmp_path):
    loaded = read_preview(write(tmp_path, BROKEN))
    assert [(i.line, i.severity) for i in loaded.issues] == [
        (3, "error"),
        (5, "error"),
        (6, "error"),
    ]
    assert loaded.issues == lint_script(BROKEN)


# -- the viewer --------------------------------------------------------------------------------
def test_a_qsub_opens_with_the_shell_highlighter_and_the_problems_row(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    assert isinstance(viewer._highlighter, ShellHighlighter)
    view = viewer.input_view
    assert view.isVisibleTo(viewer) and view.issues_bar.isVisibleTo(viewer)
    assert view.issues_label.text() == "3 problemas de escrita no script"
    assert view.issues_label.property("level") == "error"
    # a script has no extract and nothing to compare with
    assert not view.extract_bar.isVisibleTo(viewer)
    assert not view.compare_button.isVisibleTo(viewer) and view.chip_buttons == []
    assert sorted(viewer.editor.diagnostics) == [2, 4, 5]  # blocks, 0-based
    assert viewer.editor.gutter_width() > 0


def test_one_problem_is_singular_and_a_warning_has_its_own_level(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, "echo hi\n"))  # no #!
    assert viewer.input_view.issues_label.text() == "1 problema de escrita no script"
    assert viewer.input_view.issues_label.property("level") == "warning"


def test_a_clean_script_shows_no_row(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, CLEAN))
    assert isinstance(viewer._highlighter, ShellHighlighter)
    assert not viewer.input_view.isVisibleTo(viewer) and viewer.editor.diagnostics == {}


def test_the_reference_scripts_open_clean(qtbot, main_window):
    for path in sorted(REFERENCE.glob("*.qsub")):
        viewer = open_text(qtbot, main_window, path)
        assert not viewer.input_view.isVisibleTo(viewer), path.name


def test_f8_moves_between_the_problems(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    editor = viewer.editor
    activate(qtbot, main_window, editor)
    editor.go_to_line(1)
    key(qtbot, editor, "F8")
    assert editor.textCursor().blockNumber() + 1 == 3
    key(qtbot, editor, "F8")
    assert editor.textCursor().blockNumber() + 1 == 5
    key(qtbot, editor, "F8")
    assert editor.textCursor().blockNumber() + 1 == 6
    key(qtbot, editor, "F8")  # wraps
    assert editor.textCursor().blockNumber() + 1 == 3
    viewer.input_view.first_button.click()
    assert editor.textCursor().blockNumber() + 1 == 3


def test_the_underline_covers_the_span_of_the_problem(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN))
    viewer._highlighter.rehighlight()
    document = viewer.editor.text_document()
    assert wavy_columns(document, 3) == [3, 4, 5]  # "-pe"
    assert wavy_columns(document, 5) == [0, 1]  # "if"
    assert wavy_columns(document, 6) == list(range(7, 15))  # the open quote to the end of the line
    assert wavy_columns(document, 4) == []


def test_the_highlighter_underlines_with_the_color_of_the_severity():
    theme = ThemeManager("dark")
    text = "#!/bin/bash\n#$ -zz\necho ${A\n"
    document = QTextDocument()
    document.setPlainText(text)
    issues = {i.line - 1: [i] for i in lint_script(text)}
    highlighter = ShellHighlighter(document, theme, issues)
    highlighter.rehighlight()
    warning = document.findBlockByNumber(1).layout().formats()
    error = document.findBlockByNumber(2).layout().formats()
    colors = {
        r.format.underlineColor().name()
        for r in [*warning, *error]
        if r.format.underlineStyle() == WAVE
    }
    assert colors == {theme.color("warning").name(), theme.color("error").name()}
    highlighter.set_issues({})
    assert wavy_columns(document, 2) == [] and wavy_columns(document, 3) == []


def test_input_and_shell_highlighters_share_the_underline():
    assert InputHighlighter.set_issues is ShellHighlighter.set_issues
    assert InputHighlighter.underline_issues is ShellHighlighter.underline_issues


def test_a_big_script_keeps_the_color_and_says_it_was_not_checked(qtbot, main_window, tmp_path):
    line = 'echo "linha de um script grande" # comentario de enchimento\n'
    text = "#!/bin/bash\n" + 'echo "aberta\n' + line * (INPUT_READ_LIMIT // len(line) + 10)
    viewer = open_text(qtbot, main_window, write(tmp_path, text))
    assert isinstance(viewer._highlighter, ShellHighlighter)
    assert "Script grande" in viewer.banner.text() and "não foi verificada" in viewer.banner.text()
    assert not viewer.input_view.isVisibleTo(viewer) and viewer.editor.diagnostics == {}


@pytest.mark.parametrize("name", ["run.sh", "job.pbs", "job.slurm"])
def test_other_script_suffixes_stay_plain_text(qtbot, main_window, tmp_path, name):
    viewer = open_text(qtbot, main_window, write(tmp_path, BROKEN, name))
    assert viewer._highlighter is None
    assert not viewer.input_view.isVisibleTo(viewer) and viewer.editor.diagnostics == {}
    assert viewer.editor.toPlainText() == BROKEN


def test_a_script_with_a_heredoc_of_an_input_is_no_input(qtbot, main_window, tmp_path):
    path = write(tmp_path, (REFERENCE / "PDOS.qsub").read_text(), "PDOS.qsub")
    viewer = open_text(qtbot, main_window, path)
    assert isinstance(viewer._highlighter, ShellHighlighter)
    assert viewer.input_view.chip_buttons == []
    assert not viewer.input_view.compare_button.isVisibleTo(viewer)
