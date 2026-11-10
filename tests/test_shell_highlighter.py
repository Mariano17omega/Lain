"""Spec 26 R6: the ``.qsub`` highlighter of the "Criar cálculo" preview."""

from PyQt6.QtGui import QTextDocument

from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.viewer.highlighters import ShellHighlighter

SCRIPT = """#!/bin/bash
#$ -N bandas_al
# a comment with $HOME
export OMP_NUM_THREADS=1
echo "run ${PREFIX} in $DIR"
if [ -f x ]; then . ./env.sh; fi
"""


def colors(qapp, line: int) -> tuple[dict[str, str], ThemeManager]:
    """Text → color of each formatted stretch of 0-based ``line``."""
    theme = ThemeManager("dark")
    document = QTextDocument()
    document.setPlainText(SCRIPT)
    highlighter = ShellHighlighter(document, theme)
    highlighter.rehighlight()
    block = document.findBlockByNumber(line)
    text = block.text()
    painted = {
        text[r.start : r.start + r.length]: r.format.foreground().color().name()
        for r in block.layout().formats()
    }
    return {k: v for k, v in painted.items() if k.strip()}, theme


def token(theme: ThemeManager, name: str) -> str:
    return theme.color(name).name()


def test_directive_and_its_option(qapp):
    painted, theme = colors(qapp, 1)
    assert painted["#$"] == token(theme, "syn_card")
    assert painted[" -N"] == token(theme, "syn_card_option")
    assert painted[" bandas_al"] == token(theme, "syn_card")


def test_comment_wins_over_what_is_inside(qapp):
    painted, theme = colors(qapp, 2)
    assert painted == {"# a comment with $HOME": token(theme, "syn_comment")}
    shebang, _theme = colors(qapp, 0)
    assert shebang == {"#!/bin/bash": token(theme, "syn_comment")}


def test_keywords_strings_and_variables(qapp):
    painted, theme = colors(qapp, 3)
    assert painted["export"] == token(theme, "syn_namelist")
    painted, _theme = colors(qapp, 4)
    assert painted['"run '] == token(theme, "syn_string")
    assert painted["${PREFIX}"] == token(theme, "syn_logical")
    assert painted["$DIR"] == token(theme, "syn_logical")
    painted, _theme = colors(qapp, 5)
    for keyword in ("if", "then", "fi"):
        assert painted[keyword] == token(theme, "syn_namelist")
    assert painted["."] == token(theme, "syn_namelist")


def painted_line(qapp, line: str) -> tuple[dict[str, str], ThemeManager]:
    """Text → color of each formatted stretch of one line of script."""
    theme = ThemeManager("dark")
    document = QTextDocument()
    document.setPlainText(line)
    ShellHighlighter(document, theme).rehighlight()
    block = document.firstBlock()
    painted = {
        line[r.start : r.start + r.length]: r.format.foreground().color().name()
        for r in block.layout().formats()
    }
    return {k: v for k, v in painted.items() if k.strip()}, theme


def test_in_is_a_keyword_only_as_a_word_of_its_own(qapp):
    painted, theme = painted_line(qapp, "mpirun pw.x -in scf.in > scf.out")
    assert painted == {}  # no ``in`` of ``-in`` or ``scf.in`` coloured as a keyword
    painted, theme = painted_line(qapp, "for f in *.in; do echo $f; done")
    for keyword in ("for", "in", "do", "done"):
        assert painted[keyword] == token(theme, "syn_namelist")
    assert painted["$f"] == token(theme, "syn_logical")


def test_a_hash_inside_a_string_is_not_a_comment(qapp):
    painted, theme = painted_line(qapp, 'echo "Job #1 done" # a real one')
    assert painted['"Job #1 done"'] == token(theme, "syn_string")
    assert painted["# a real one"] == token(theme, "syn_comment")
    painted, theme = painted_line(qapp, "echo 'a #b' \\# c")  # the backslash escapes the #
    assert painted["'a #b'"] == token(theme, "syn_string")
    assert "\\# c" not in painted and not any(
        v == token(theme, "syn_comment") for v in painted.values()
    )


def test_the_hash_of_a_word_in_the_middle_is_not_a_comment(qapp):
    painted, theme = painted_line(qapp, "echo a#b $#")
    assert not any(color == token(theme, "syn_comment") for color in painted.values())
    assert painted["$#"] == token(theme, "syn_logical")
