"""Spec 26 R6: the ``.qsub`` highlighter of the "Criar cálculo" preview."""

from PyQt6.QtGui import QTextDocument

from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.highlighters import ShellHighlighter

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
