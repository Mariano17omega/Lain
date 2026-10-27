"""Write checks of an SGE job script (``.qsub``, spec 38 R2), the counterpart of ``qe/input_lint``.

It reads how a script is *written*: unbalanced quotes, an ``if`` with no ``fi``, a CRLF line end, a
``#$`` option that does not exist. It never runs anything (no ``bash -n``: the result must not depend
on the user's shell) and never raises. A script that passes is not proved correct; the rules are the
ones that are wrong without ambiguity, so a false alarm costs more than a missed error.

Heredoc bodies (``<< EOF … EOF``) are not shell and are skipped, except that SGE itself reads a ``#$``
line wherever it stands.
"""

from __future__ import annotations

import logging
import re

from ..i18n import _
from . import cancel
from .qe.input_lexer import LintIssue, Severity

log = logging.getLogger(__name__)

# Options of SGE's qsub(1), as I know them: **not** checked against the user's cluster. An option
# outside the set is only a warning (a site may add its own), so the set errs on the long side.
SGE_OPTION_NAMES = (
    "N pe cwd wd V v S j o e q l m M t hold_jid hold_jid_ad b r P A p R w binding h a "
    "hard soft ckpt c i u sync terse verify ac dc sc js jc masterq now pty clear C dl ar xdv "
    "shell tc notify help"
)
SGE_OPTIONS = frozenset(SGE_OPTION_NAMES.split())
OPENERS = {
    "if": "if",
    "for": "loop",
    "while": "loop",
    "until": "loop",
    "select": "loop",
    "case": "case",
}
CLOSERS = {"fi": "if", "done": "loop", "esac": "case"}
KEYWORDS = frozenset(OPENERS) | frozenset(CLOSERS) | {"do"}
# After these the next word is still a command (``then if x``, ``! cmd``, ``while cmd``).
KEEPING_WORDS = "if elif then else do while until time ! {"
KEEPS_COMMAND = frozenset(KEEPING_WORDS.split())

# A line with none of these is plain words: no quote, escape, expansion, comment or operator.
_SPECIAL = re.compile(r"[\"'\\$#<>;&|()`]")
_HEREDOC = re.compile(r"<<(-?)[ \t]*(?:\\?([A-Za-z_][^\s;|&<>()'\"]*)|'([^']+)'|\"([^\"]+)\")")
_OPTION = re.compile(r"-[A-Za-z_]+$")
_TOKEN = re.compile(r"(?:\"[^\"]*\"|'[^']*'|[^\s\"'])+")

CRLF = _("Fim de linha CRLF: o bash do cluster lê o \\r como parte do comando")
NO_SHEBANG = _("Falta o #! na primeira linha (por exemplo: #!/usr/bin/env bash)")
BROKEN_CONTINUATION = _("\\ no fim da linha seguido de espaço: a continuação de linha não funciona")
PE_NEEDS = _("-pe pede o ambiente paralelo e o número de slots (por exemplo: -pe physica 64)")
N_NEEDS = _("-N pede o nome do job")
STRAY = {
    "fi": _("fi sem if correspondente"),
    "done": _("done sem for/while/until correspondente"),
    "esac": _("esac sem case correspondente"),
    "do": _("do fora de um laço for/while/until"),
}
LEFTOVER = {"if": _("if sem fi"), "loop": _("{word} sem done"), "case": _("case sem esac")}


class _Scan:
    """The state that runs from one line to the next: an open quote, the heredocs waiting for their
    body, the open blocks, and whether the next word is a command."""

    def __init__(self) -> None:
        self.issues: list[LintIssue] = []
        self.quote: str | None = None  # ", ' or $' (the ANSI-C one, which keeps its escapes)
        self.quote_at = (0, 0)
        self.heredocs: list[tuple[str, bool]] = []  # (delimiter, tabs are stripped)
        self.stack: list[tuple[str, str, int, int, int]] = []  # family, word, line, start, end
        self.command = True

    def add(self, line: int, start: int, end: int, severity: Severity, message: str) -> None:
        self.issues.append(LintIssue(line, start, max(end, start), severity, message))

    # -- one line ----------------------------------------------------------------------------
    def line(self, line: str, lineno: int) -> None:
        if self.heredocs:
            delimiter, strip = self.heredocs[0]
            if (line.lstrip("\t") if strip else line) == delimiter:
                self.heredocs.pop(0)
            return
        if self.quote is None and not _SPECIAL.search(line):
            self._plain(line, lineno)
        else:
            self._scan(line, lineno)

    def _plain(self, line: str, lineno: int) -> None:
        position = 0
        for word in line.split():
            start = line.index(word, position)
            position = start + len(word)
            self._word(word, lineno, start, position, "", False)
        self.command = True

    def _scan(self, line: str, lineno: int) -> None:
        n = len(line)
        i, start, quoted, continued = 0, 0, self.quote is not None, False
        chars: list[str] = []

        def flush(at: int) -> None:
            nonlocal quoted
            if chars or quoted:
                self._word("".join(chars), lineno, start, at, line[at:], quoted)
            chars.clear()
            quoted = False

        while i < n:
            c = line[i]
            quote = self.quote
            if quote is not None:
                if c == "\\" and quote != "'":
                    self._blanks_after_backslash(line, lineno, i)
                    i += 2
                    continue
                if c == quote[-1]:
                    self.quote = None
                elif c == "$" and quote == '"' and line.startswith("${", i):
                    self._brace(line, lineno, i)
                i += 1
                continue
            if c == "\\":
                if i + 1 >= n:  # backslash-newline: the line goes on, still in the same command
                    flush(i)
                    continued = True
                    break
                self._blanks_after_backslash(line, lineno, i)
                if not chars and not quoted:
                    start = i
                quoted = True  # an escaped character is literal: ``\fi`` is no keyword
                i += 2
                continue
            if c == '"' or c == "'":
                if not chars and not quoted:
                    start = i
                quoted = True
                self.quote = "$'" if c == "'" and chars and chars[-1] == "$" else c
                self.quote_at = (lineno, i)
                i += 1
                continue
            if c == "#" and not chars and not quoted:
                break  # a comment: nothing in it is checked
            if c in " \t":
                flush(i)
            elif c in ";&|()":
                flush(i)
                self.command = True
            elif c in "<>":
                flush(i)
                if line.startswith("<<<", i):
                    i += 3
                    continue
                match = _HEREDOC.match(line, i) if line.startswith("<<", i) else None
                if match is not None:
                    name = match.group(2) or match.group(3) or match.group(4)
                    self.heredocs.append((name, match.group(1) == "-"))
                    i = match.end()
                    continue
            else:
                if c == "$" and line.startswith("${", i):
                    self._brace(line, lineno, i)
                if not chars and not quoted:
                    start = i
                chars.append(c)
            i += 1
        flush(min(i, n))
        if not continued and self.quote is None:
            self.command = True

    # -- rules -------------------------------------------------------------------------------
    def _word(self, text: str, lineno: int, start: int, end: int, rest: str, quoted: bool) -> None:
        if self.command and not quoted and text in KEYWORDS:
            self._keyword(text, lineno, start, end, rest)
        # Only a word that was itself a command keeps the position: ``echo if`` does not.
        self.command = self.command and not quoted and text in KEEPS_COMMAND

    def _keyword(self, word: str, lineno: int, start: int, end: int, rest: str) -> None:
        top = self.stack[-1][0] if self.stack else None
        if top == "case" and rest.lstrip().startswith(")"):
            return  # ``fi) …;;``: a pattern of the case, not a keyword
        if word in OPENERS:
            self.stack.append((OPENERS[word], word, lineno, start, end))
        elif word in CLOSERS:
            if top == CLOSERS[word]:
                self.stack.pop()
            else:
                self.add(lineno, start, end, "error", STRAY[word])
        elif top != "loop":  # ``do``
            self.add(lineno, start, end, "error", STRAY["do"])

    def _brace(self, line: str, lineno: int, at: int) -> None:
        if "}" not in line[at + 2 :]:
            self.add(lineno, at, len(line), "error", _("${ sem } na linha"))

    def _blanks_after_backslash(self, line: str, lineno: int, at: int) -> None:
        rest = line[at + 1 :]
        if rest and not rest.strip(" \t"):
            self.add(lineno, at, len(line), "warning", BROKEN_CONTINUATION)

    def directive(self, line: str, lineno: int) -> None:
        """``#$ -N nome -pe ambiente slots …``: the options SGE reads from a script's comments."""
        tokens = [(m.start() + 2, m.group()) for m in _TOKEN.finditer(line[2:])]
        for k, (col, token) in enumerate(tokens):
            if token.startswith("#"):
                break
            if not _OPTION.match(token):
                continue
            end = col + len(token)
            name = token[1:]
            if name not in SGE_OPTIONS:
                self.add(
                    lineno,
                    col,
                    end,
                    "warning",
                    _("Opção desconhecida do qsub: {token}").format(token=token),
                )
                continue
            values = []
            for _col, value in tokens[k + 1 :]:
                if value.startswith("#") or _OPTION.match(value):
                    break
                values.append(value.strip("\"'"))
            if name == "pe" and sum(1 for v in values if v) < 2:
                self.add(lineno, col, end, "error", PE_NEEDS)
            elif name == "N" and not any(values):
                self.add(lineno, col, end, "error", N_NEEDS)

    def finish(self, lines: list[str]) -> None:
        if self.quote is not None:
            at_line, column = self.quote_at
            quote = self.quote[-1]
            message = _("Aspas {quote} abertas e não fechadas até o fim do arquivo").format(
                quote=quote
            )
            self.add(at_line, column, len(lines[at_line - 1]), "error", message)
        for family, word, at_line, start, end in self.stack:
            self.add(at_line, start, end, "error", LEFTOVER[family].format(word=word))


def _lint(text: str) -> list[LintIssue]:
    if not text.strip():
        return []
    lines = text.split("\n")
    scan = _Scan()
    if "\r" in text:
        for number, line in enumerate(lines, 1):
            if line.endswith("\r"):
                scan.add(number, len(line) - 1, len(line), "error", CRLF)
                break
        lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    if not lines[0].startswith("#!"):
        scan.add(1, 0, len(lines[0]), "warning", NO_SHEBANG)
    for number, line in enumerate(cancel.checked(lines), 1):
        if line.startswith("#$"):
            scan.directive(line, number)
        scan.line(line, number)
    scan.finish(lines)
    return sorted(scan.issues, key=lambda issue: (issue.line, issue.col_start))


def lint_script(text: str) -> list[LintIssue]:
    """The write problems of ``text``, sorted by line and column; never raises."""
    try:
        return _lint(text)
    except cancel.Cancelled:
        raise
    except Exception:  # a checker must not take the viewer down: the text is shown anyway
        log.exception("cannot check the script")
        return []


def job_name(text: str, script: str) -> str:
    """The name SGE gives the job of the script ``text``: the value of the last ``-N`` of its ``#$``
    lines, quotes stripped, else the script's file name ``script``, as ``qsub`` does (spec 71 R3)."""
    name = ""
    for line in text.splitlines():
        if not line.startswith("#$"):
            continue
        tokens = [match.group() for match in _TOKEN.finditer(line[2:])]
        for k, token in enumerate(tokens):
            if token.startswith("#"):
                break
            value = tokens[k + 1] if k + 1 < len(tokens) else ""
            if token == "-N" and not value.startswith("#") and not _OPTION.match(value):
                name = value.strip("\"'") or name
    return name or script.rsplit("/", 1)[-1]
