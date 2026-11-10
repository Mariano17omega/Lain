"""Write checks of an SGE job script (``.qsub``, spec 38 R2), the counterpart of ``qe/input_lint``.

It reads how a script is *written*: unbalanced quotes, an ``if`` with no ``fi``, a CRLF line end, a
``#$`` option that does not exist. It never runs anything (no ``bash -n``: the result must not depend
on the user's shell) and never raises. A script that passes is not proved correct; the rules are the
ones that are wrong without ambiguity, so a false alarm costs more than a missed error.

The scan follows the nesting bash sees, as a stack of levels: ``$(…)``, backticks, ``<(…)`` and a
subshell are shell with blocks of their own; an array, ``$((…))`` and ``${…}`` hold no commands.

Heredoc bodies (``<< EOF … EOF``) are not shell and are skipped, except that SGE itself reads a ``#$``
line wherever it stands.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ...i18n import _
from .. import cancel
from ..files.job_script import directive_tokens, is_option
from ..qe.input_lexer import LintIssue, Severity

log = logging.getLogger(__name__)

# Options of SGE's qsub(1), as I know them: **not** checked against the user's cluster. An option
# outside the set is only a warning (a site may add its own), so the set errs on the long side.
SGE_OPTION_NAMES = (
    "N pe cwd wd V v S j o e q l m M t hold_jid hold_jid_ad b r P A p R w binding h a "
    "hard soft ckpt c i u sync terse verify ac dc sc js jc jsv masterq now pty clear clearp C dl "
    "ar xd xdv display shell tc notify help"
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
# After these the next word is still a command (``then if x``, ``! cmd``, ``done done``).
KEEPING_WORDS = "if elif then else do while until time ! { fi done esac"
KEEPS_COMMAND = frozenset(KEEPING_WORDS.split())

# A line with none of these is plain words: no quote, escape, expansion, comment or operator.
_SPECIAL = re.compile(r"[\"'\\$#<>;&|()`]")
_HEREDOC = re.compile(r"""<<(-?)[ \t]*((?:\\.|'[^']*'|"[^"]*"|[^\s;|&<>()'"\\])+)""")
_QUOTING = re.compile(r"""\\(.)|'([^']*)'|"([^"]*)\"""")
_REDIRECT = re.compile(r"&>>?|<<<|<<-?|<>|<&|>>|>&|>\||<|>")
_CASE_END = re.compile(r";;&?|;&")
_EMPTY_PARENTHESES = re.compile(r"\([ \t]*\)")
_OPERATORS = frozenset(";&|()<>")
_CHECK_EVERY_CHARS = 100_000  # a single line can be megabytes long

SHELL, LIST, ARITHMETIC, BRACE = "shell", "list", "arithmetic", "brace"

CRLF = _("Fim de linha CRLF: o bash do cluster lê o \\r como parte do comando")
NO_SHEBANG = _("Falta o #! na primeira linha (por exemplo: #!/usr/bin/env bash)")
BROKEN_CONTINUATION = _("\\ no fim da linha seguido de espaço: a continuação de linha não funciona")
PE_NEEDS = _("-pe pede o ambiente paralelo e o número de slots (por exemplo: -pe physica 64)")
N_NEEDS = _("-N pede o nome do job")
UNCLOSED_BRACE = _("${ sem } correspondente")
STRAY = {
    "fi": _("fi sem if correspondente"),
    "done": _("done sem for/while/until correspondente"),
    "esac": _("esac sem case correspondente"),
    "do": _("do fora de um laço for/while/until"),
}
LEFTOVER = {"if": _("if sem fi"), "loop": _("{word} sem done"), "case": _("case sem esac")}


@dataclass(slots=True)
class _Level:
    """One level of nesting and the state that runs from one of its lines to the next. A shell level
    is the script, a ``$(…)``, a backtick pair, a ``<(…)`` or a subshell; a list is any other
    parenthesis (an array, an extglob); the rest are ``$((…))`` and ``${…}``."""

    kind: str = SHELL
    closer: str = ""  # ``)``, a backtick or ``}``; none for the script and an arithmetic expression
    joins_word: bool = True  # what follows it goes on with its word; else a command may follow
    at: tuple[int, int] = (0, 0)  # line and column where it opened
    in_double_quote: bool = False  # a ``${`` inside "…", where a ``'`` is a plain character
    depth: int = 0  # arithmetic: the parentheses still open
    quote: str | None = None  # ", ' or $' (the ANSI-C one, which keeps its escapes)
    quote_at: tuple[int, int] = (0, 0)
    blocks: list[tuple[str, str, int, int, int]] = field(default_factory=list)  # family, word, …
    command: bool = True  # is the next word a command?
    case_words: int = 0  # words still to come up to the ``in`` of a ``case``
    pattern: bool = False  # reading the patterns of a ``case``
    esac_is_pattern: bool = False  # right after ``(`` or ``|``, where ``esac`` is only a pattern


def _delimiter(word: str) -> str:
    """The heredoc delimiter that ``word`` spells: its quoting removed, nothing expanded."""
    return _QUOTING.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or "", word)


class _Scan:
    """The issues found, the heredocs waiting for their body, the levels open, and the word that
    is being read on the current line."""

    def __init__(self) -> None:
        self.issues: list[LintIssue] = []
        self.heredocs: list[tuple[str, bool]] = []  # (delimiter, tabs are stripped)
        self.levels: list[_Level] = [_Level()]
        self.chars: list[str] = []
        self.start = 0
        self.literal = False  # the word holds a quote, an escape or an expansion: never a keyword
        self.text, self.lineno, self.last = "", 0, 0

    def add(self, line: int, start: int, end: int, severity: Severity, message: str) -> None:
        self.issues.append(LintIssue(line, start, max(end, start), severity, message))

    # -- one line ----------------------------------------------------------------------------
    def line(self, line: str, lineno: int) -> None:
        if self.heredocs:
            delimiter, strip = self.heredocs[0]
            if (line.lstrip("\t") if strip else line) == delimiter:
                self.heredocs.pop(0)
            return
        if len(self.levels) == 1 and self.levels[0].quote is None and not _SPECIAL.search(line):
            self._plain(line, lineno)
        else:
            self._scan(line, lineno)

    def _plain(self, line: str, lineno: int) -> None:
        position = 0
        for word in line.split():
            start = line.index(word, position)
            position = start + len(word)
            self._word(word, lineno, start, position, False)
        self.levels[0].command = True

    def _scan(self, line: str, lineno: int) -> None:
        self.text, self.lineno, self.last = line, lineno, len(line.rstrip(" \t"))
        self.literal = self.levels[-1].quote is not None
        n, i, continued, check_at = len(line), 0, False, _CHECK_EVERY_CHARS
        while i < n:
            if i >= check_at:
                cancel.check()
                check_at = i + _CHECK_EVERY_CHARS
            level, c = self.levels[-1], line[i]
            quote = level.quote
            if c == "\\" and quote != "'":
                if i + 1 >= n and quote is None:  # backslash-newline: the same command goes on
                    continued = True
                    break
                self._escape(i)
                i += 2
            elif c == "`" and level.closer == "`":  # the first one closes, even inside a quote
                self._flush(i)
                level.quote = None
                self._close()
                i += 1
            elif quote is not None:
                i = self._in_quote(level, quote, c, i)
            elif c in "$`" and (taken := self._expansion(i)):
                i += taken
            elif c == "#" and level.kind in (SHELL, LIST) and not self.chars and not self.literal:
                end = line.find("`", i) if level.closer == "`" else -1
                if end < 0:
                    break  # a comment: nothing in it is checked
                i = end
            else:
                i = self._unquoted(level, c, i)
        self._flush(min(i, n))
        level = self.levels[-1]
        if not continued and level.quote is None and level.kind == SHELL:
            level.command = True

    def _flush(self, at: int) -> None:
        if self.chars or self.literal:
            self._word("".join(self.chars), self.lineno, self.start, at, self.literal)
        self.chars.clear()
        self.literal = False

    def _escape(self, at: int) -> None:
        """A backslash at ``at``: what it escapes is literal (``\\fi`` is no keyword)."""
        if at + 1 == self.last and at + 1 < len(self.text):
            self.add(self.lineno, at, len(self.text), "warning", BROKEN_CONTINUATION)
        if not self.chars and not self.literal:
            self.start = at
        self.literal = True

    def _in_quote(self, level: _Level, quote: str, c: str, i: int) -> int:
        if c == quote[-1]:
            level.quote = None
        elif quote == '"' and c in "$`":
            return i + (self._expansion(i) or 1)
        return i + 1

    def _unquoted(self, level: _Level, c: str, i: int) -> int:
        """Handle the character at ``i``, outside any quote; the index of the next one."""
        if c == '"' or c == "'":
            return self._open_quote(level, c, i)
        if c in " \t":
            self._flush(i)
            return i + 1
        if level.kind == SHELL:
            if c in _OPERATORS:
                return self._operator(level, c, i)
        elif self._nesting(level, c, i):
            return i + 1
        if not self.chars and not self.literal:
            self.start = i
        self.chars.append(c)
        return i + 1

    def _open_quote(self, level: _Level, c: str, i: int) -> int:
        if c == "'" and level.kind == BRACE and level.in_double_quote:
            return i + 1
        if not self.chars and not self.literal:
            self.start = i
        self.literal = True
        level.quote = "$'" if c == "'" and self.chars and self.chars[-1] == "$" else c
        level.quote_at = (self.lineno, i)
        return i + 1

    # -- levels ------------------------------------------------------------------------------
    def _open(
        self, kind: str, closer: str, at: int, joins_word: bool = True, depth: int = 0
    ) -> None:
        around = self.levels[-1]
        in_double_quote = around.quote == '"' or (around.kind == BRACE and around.in_double_quote)
        self.levels.append(
            _Level(kind, closer, joins_word, (self.lineno, at), in_double_quote, depth)
        )
        self.chars.clear()
        self.literal = False

    def _close(self) -> None:
        level = self.levels.pop()
        self._leftovers(level)
        self.chars.clear()
        self.literal = level.joins_word  # part of the word around it, which is then no keyword
        if not level.joins_word:
            self.levels[-1].command = True

    def _expansion(self, i: int) -> int:
        """Open the expansion that starts at ``i``: how many characters it took (0: none)."""
        line = self.text
        if line[i] == "`":
            self._open(SHELL, "`", i)
            return 1
        if line.startswith("${", i):
            self._open(BRACE, "}", i)
            return 2
        if line.startswith("$((", i):
            self._open(ARITHMETIC, "", i, depth=2)
            return 3
        if line.startswith("$(", i):
            self._open(SHELL, ")", i)
            return 2
        return 0

    def _nesting(self, level: _Level, c: str, i: int) -> bool:
        """The parentheses and braces of a level that is not shell; was ``c`` one of them?"""
        if c == level.closer:
            self._flush(i)
            self._close()
        elif level.kind == LIST and c == "(":
            self._flush(i)
            self._open(LIST, ")", i)
        elif level.kind == ARITHMETIC and c in "()":
            level.depth += 1 if c == "(" else -1
            if not level.depth:
                self._flush(i)
                self._close()
        else:
            return False
        return True

    # -- operators of a shell level ----------------------------------------------------------
    def _operator(self, level: _Level, c: str, i: int) -> int:
        in_word = bool(self.chars) or self.literal
        self._flush(i)
        if c in "<>" or self.text.startswith("&>", i):
            return self._redirect(level, c, i)
        if c == "(":
            return self._open_parenthesis(level, in_word, i)
        if c == ")":
            if level.closer == ")" and not level.pattern:
                self._close()
            else:  # the end of a case pattern, or a stray one
                level.pattern = False
                level.command = True
            return i + 1
        if c == "|" and level.pattern:
            level.esac_is_pattern = True
            return i + 1
        case_end = _CASE_END.match(self.text, i) if c == ";" else None
        if case_end is not None and level.blocks and level.blocks[-1][0] == "case":
            level.pattern, level.esac_is_pattern = True, False
            return case_end.end()
        level.command = True
        return i + 1

    def _redirect(self, level: _Level, c: str, i: int) -> int:
        """A redirection, whose target is no command, a process substitution or a heredoc."""
        line = self.text
        level.command = False
        if c != "&" and line.startswith("(", i + 1):
            self._open(SHELL, ")", i)
            return i + 2
        if line.startswith("<<", i) and not line.startswith("<<<", i):
            heredoc = _HEREDOC.match(line, i)
            if heredoc is not None:
                self.heredocs.append((_delimiter(heredoc.group(2)), heredoc.group(1) == "-"))
                return heredoc.end()
        redirect = _REDIRECT.match(line, i)
        return i + 1 if redirect is None else redirect.end()

    def _open_parenthesis(self, level: _Level, in_word: bool, i: int) -> int:
        if level.pattern:  # the optional ``(`` of a case pattern
            level.esac_is_pattern = True
            return i + 1
        if not in_word and self.text.startswith("((", i):
            self._open(ARITHMETIC, "", i, joins_word=False, depth=2)
            return i + 2
        empty = _EMPTY_PARENTHESES.match(self.text, i)
        if empty is not None:  # ``f()``: its body is a command
            level.command = True
            return empty.end()
        if level.command and not in_word:
            self._open(SHELL, ")", i, joins_word=False)
        else:
            self._open(LIST, ")", i)
        return i + 1

    # -- rules -------------------------------------------------------------------------------
    def _word(self, text: str, lineno: int, start: int, end: int, literal: bool) -> None:
        level = self.levels[-1]
        if level.kind != SHELL:
            return
        if level.pattern:  # only ``esac`` is a keyword here, as in bash's parser
            if text == "esac" and not literal and not level.esac_is_pattern:
                level.pattern = False
                self._keyword(level, text, lineno, start, end)
                level.command = True
            level.esac_is_pattern = False
            return
        if level.case_words:  # the word a ``case`` tests, then its ``in``
            level.case_words -= 1
            if not level.case_words:
                level.pattern = text == "in" and not literal
            return
        if level.command and not literal and text in KEYWORDS:
            self._keyword(level, text, lineno, start, end)
        # Only a word that was itself a command keeps the position: ``echo if`` does not.
        level.command = level.command and not literal and text in KEEPS_COMMAND

    def _keyword(self, level: _Level, word: str, lineno: int, start: int, end: int) -> None:
        top = level.blocks[-1][0] if level.blocks else None
        if word in OPENERS:
            level.blocks.append((OPENERS[word], word, lineno, start, end))
            if word == "case":
                level.case_words = 2
        elif word in CLOSERS:
            if top == CLOSERS[word]:
                level.blocks.pop()
            else:
                self.add(lineno, start, end, "error", STRAY[word])
        elif top != "loop":  # ``do``
            self.add(lineno, start, end, "error", STRAY["do"])

    def directive(self, line: str, lineno: int) -> None:
        """``#$ -N nome -pe ambiente slots …``: the options SGE reads from a script's comments."""
        tokens = directive_tokens(line)
        for k, (col, token) in enumerate(tokens):
            if not is_option(token):
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
            for index in range(k + 1, len(tokens)):
                value = tokens[index][1]
                if is_option(value):
                    break
                values.append(value.strip("\"'"))
            if name == "pe" and sum(1 for v in values if v) < 2:
                self.add(lineno, col, end, "error", PE_NEEDS)
            elif name == "N" and not any(values):
                self.add(lineno, col, end, "error", N_NEEDS)

    def _leftovers(self, level: _Level) -> None:
        for family, word, at_line, start, end in level.blocks:
            self.add(at_line, start, end, "error", LEFTOVER[family].format(word=word))

    def finish(self, lines: list[str]) -> None:
        brace = next((level for level in self.levels if level.kind == BRACE), None)
        if brace is not None:  # the quote that looks unclosed may well be inside it
            at_line, column = brace.at
            self.add(at_line, column, len(lines[at_line - 1]), "error", UNCLOSED_BRACE)
        else:
            for level in self.levels:
                if level.quote is not None:
                    at_line, column = level.quote_at
                    message = _("Aspas {quote} abertas e não fechadas até o fim do arquivo").format(
                        quote=level.quote[-1]
                    )
                    self.add(at_line, column, len(lines[at_line - 1]), "error", message)
        for level in self.levels:
            self._leftovers(level)


def _lint(text: str) -> list[LintIssue]:
    if not text.strip():
        return []
    lines = text.split("\n")
    scan = _Scan()
    if "\r" in text:
        for number, line in enumerate(lines, 1):
            if line.endswith("\r"):  # the editor drops the \r itself: mark the text before it
                scan.add(number, 0, len(line) - 1, "error", CRLF)
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


def lint_script(text: str, name: str = "a script being edited") -> list[LintIssue]:
    """The write problems of ``text``, sorted by line and column; never raises. ``name`` says which
    script it is in the log, if the checker fails."""
    try:
        return _lint(text)
    except cancel.Cancelled:
        raise
    except Exception:  # a checker must not take the viewer down: the text is shown anyway
        log.exception("file: cannot check %s", name)
        return []
