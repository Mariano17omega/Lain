"""Syntax highlighters of the text viewer (specs 10 R2, 11 R3). Colors are theme tokens, never
literals."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from ...core.qe.input_lexer import LexState, LintIssue, scan_line
from ..theme.manager import ThemeManager


class ThemedHighlighter(QSyntaxHighlighter):
    """Base: formats come from theme tokens and are rebuilt when the theme changes."""

    def __init__(self, document: QTextDocument, theme: ThemeManager):
        super().__init__(document)
        self.theme = theme
        self._formats: dict[tuple[str, bool], QTextCharFormat] = {}
        # A bound method, not a lambda: the connection dies with the highlighter.
        theme.theme_changed.connect(self._on_theme)

    def fmt(self, token: str, bold: bool = False) -> QTextCharFormat:
        key = (token, bold)
        if key not in self._formats:
            fmt = QTextCharFormat()
            fmt.setForeground(self.theme.color(token))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            self._formats[key] = fmt
        return self._formats[key]

    def _on_theme(self, _name: str = "") -> None:
        self._formats.clear()
        self.rehighlight()


class Rule(NamedTuple):
    pattern: re.Pattern[str]
    token: str
    bold: bool = False
    whole_line: bool = False  # color the whole line, not only the matched text


def _rule(pattern: str, token: str, bold: bool = False, whole_line: bool = False) -> Rule:
    return Rule(re.compile(pattern), token, bold, whole_line)


# Later rules win where they overlap.
OUTPUT_RULES = (
    _rule(r"Program \w+ v\.", "hl_header", whole_line=True),
    _rule(
        r"the Fermi energy is|highest occupied|Final enthalpy|total magnetization",
        "hl_info",
        whole_line=True,
    ),
    _rule(r"^!\s+total energy", "hl_energy", bold=True, whole_line=True),
    _rule(r"Message from routine|Warning|WARNING", "hl_warning"),
    _rule(
        r"JOB DONE|convergence has been achieved|bfgs converged|End of BFGS Geometry Optimization",
        "hl_success",
    ),
    _rule(r"convergence NOT achieved", "hl_error"),
    _rule(r"Error in routine|^\s*Error", "hl_error", whole_line=True),
)
# Most lines of a big output match nothing: one search over every rule at once skips them.
ANY_RULE = re.compile("|".join(rule.pattern.pattern for rule in OUTPUT_RULES))
ERROR_BAR = re.compile(r"^\s*%{4,}")  # the %%%% lines that frame a QE error message
INSIDE_ERROR = 1


class OutputHighlighter(ThemedHighlighter):
    """QE outputs and job logs: energies, success, errors, warnings, key results.

    One line at a time, except the ``%%%%`` error block: its lines carry the block state.
    """

    def highlightBlock(self, text: str | None) -> None:
        text = text or ""
        inside = self.previousBlockState() == INSIDE_ERROR
        if ERROR_BAR.match(text):
            # The first bar opens the block, the next one closes it.
            self.setCurrentBlockState(0 if inside else INSIDE_ERROR)
            self.setFormat(0, len(text), self.fmt("hl_error"))
            return
        if inside:
            self.setCurrentBlockState(INSIDE_ERROR)
            self.setFormat(0, len(text), self.fmt("hl_error"))
            return
        self.setCurrentBlockState(0)
        if not ANY_RULE.search(text):
            return
        for rule in OUTPUT_RULES:
            for match in rule.pattern.finditer(text):
                start, end = (0, len(text)) if rule.whole_line else match.span()
                self.setFormat(start, end - start, self.fmt(rule.token, rule.bold))


class InputHighlighter(ThemedHighlighter):
    """QE inputs: namelists, keys, strings, numbers, logicals, comments and cards, plus a wavy
    underline on the span of every write error (``error`` color) or warning (``warning``).

    The coloring is the lexer's (``scan_line``), one line at a time, with the lexer state in the
    block state, so the highlighter and the linter agree on what a token is. The issues come from
    the worker (``lint``) as ``{block: [issue, ...]}``: files too big to lint have none.
    """

    def __init__(
        self,
        document: QTextDocument,
        theme: ThemeManager,
        issues: Mapping[int, Sequence[LintIssue]] | None = None,
    ):
        super().__init__(document, theme)
        # The first pass is queued, so it sees the issues set right after the constructor.
        self._issues: Mapping[int, Sequence[LintIssue]] = issues or {}

    def set_issues(self, issues: Mapping[int, Sequence[LintIssue]]) -> None:
        self._issues = issues
        self.rehighlight()

    def highlightBlock(self, text: str | None) -> None:
        text = text or ""
        block = self.currentBlock().blockNumber()
        scan = scan_line(text, LexState.from_code(self.previousBlockState()), block + 1)
        self.setCurrentBlockState(scan.state.code)
        for token in scan.tokens:
            self.setFormat(token.start, token.end - token.start, self.fmt(token.kind.value))
        for issue in self._issues.get(block, ()):
            color = self.theme.color(issue.severity)
            for column in range(issue.col_start, min(issue.col_end, len(text))):
                fmt = QTextCharFormat(self.format(column))  # keep the syntax color
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(color)
                self.setFormat(column, 1, fmt)


SHELL_KEYWORDS = (
    "if then else elif fi for in do done case esac while until function select export source "
    "local return exit set unset"
)
# Later rules win where they overlap: a variable inside a string keeps its color, anything inside a
# comment is the comment's, and a ``#$`` scheduler directive is not a comment.
SHELL_RULES = (
    _rule(rf"\b(?:{'|'.join(SHELL_KEYWORDS.split())})\b", "syn_namelist"),
    _rule(r"(?:^|(?<=[\s;]))\.(?=\s)", "syn_namelist"),  # ". script": source
    _rule(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', "syn_string"),
    _rule(r"\$\{[^}]*\}|\$[A-Za-z_]\w*|\$[0-9@#?*$!-]", "syn_logical"),
    _rule(r"(?:^|(?<=\s))#.*", "syn_comment"),
    _rule(r"^#\$.*", "syn_card"),
    _rule(r"(?<=^#\$)\s*-\w+", "syn_card_option", bold=True),
)


class ShellHighlighter(ThemedHighlighter):
    """SGE job scripts (``.qsub``, spec 26 R6): ``#$`` directives and their option, comments,
    strings, variables and shell keywords, in the input highlighter's ``syn_*`` colors."""

    def highlightBlock(self, text: str | None) -> None:
        text = text or ""
        for rule in SHELL_RULES:
            for match in rule.pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, self.fmt(rule.token, rule.bold))
