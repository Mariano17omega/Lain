"""Line lexer of Quantum ESPRESSO inputs, tolerant and stateful (spec 11 R1).

``scan_line`` reads one line given the state the previous line left, so the linter
(``input_lint``) and the editor's syntax highlighter walk a file with the same rules, and the
highlighter only has to keep ``LexState.code`` in the block state. It never raises: a line it
cannot make sense of yields no tokens, and the local write errors it can see (R2 rows 1, 3–7, 12)
come back as ``LintIssue``s. Rules that need the whole file (unclosed namelist, repeated or
unknown namelist/card, card options) belong to ``input_lint``.

Conventions: ``LintIssue.line`` is 1-based (``LineMap`` numbering) and columns are 0-based,
half-open (what ``QSyntaxHighlighter.setFormat`` takes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Literal

from .pw_input import NUMBER

Severity = Literal["error", "warning"]

KNOWN_CARDS = (
    "ATOMIC_SPECIES", "ATOMIC_POSITIONS", "K_POINTS", "ADDITIONAL_K_POINTS", "CELL_PARAMETERS",
    "CONSTRAINTS", "OCCUPATIONS", "ATOMIC_VELOCITIES", "ATOMIC_FORCES", "SOLVENTS", "HUBBARD",
)  # fmt: skip
# Cards whose option is a closed set (pw.x 7.1+). Writing no option is allowed (QE's default).
CARD_OPTIONS = {
    "ATOMIC_POSITIONS": frozenset({"alat", "bohr", "angstrom", "crystal", "crystal_sg"}),
    "K_POINTS": frozenset(
        {"tpiba", "automatic", "crystal", "gamma", "tpiba_b", "crystal_b", "tpiba_c", "crystal_c"}
    ),
    "CELL_PARAMETERS": frozenset({"alat", "bohr", "angstrom"}),
}


class Kind(StrEnum):
    """Token classes. The values are the theme tokens the highlighter paints them with."""

    NAMELIST = "syn_namelist"
    KEY = "syn_key"
    STRING = "syn_string"
    NUMBER = "syn_number"
    LOGICAL = "syn_logical"
    COMMENT = "syn_comment"
    CARD = "syn_card"
    CARD_OPTION = "syn_card_option"


class Mode(IntEnum):
    OUTSIDE = 0
    NAMELIST = 1
    CARD = 2


@dataclass(frozen=True)
class LexState:
    """What a line leaves for the next one: where we are, and whether the last significant line of
    the namelist ended with a comma (so a line of bare values continues it, R1.2)."""

    mode: Mode = Mode.OUTSIDE
    comma: bool = False

    @property
    def code(self) -> int:
        """Fits ``QSyntaxHighlighter.setCurrentBlockState``."""
        return int(self.mode) | int(self.comma) << 2

    @classmethod
    def from_code(cls, code: int) -> LexState:
        """Inverse of ``code``; anything else (Qt's -1 for the first block) is the start state."""
        try:
            return cls(Mode(code & 3), bool(code >> 2 & 1)) if code >= 0 else cls()
        except ValueError:
            return cls()


@dataclass(frozen=True)
class LintIssue:
    line: int
    col_start: int
    col_end: int
    severity: Severity
    message: str


@dataclass(frozen=True)
class Entry:
    """One ``key = value`` of a namelist. ``key`` is lowercase, indices included (``celldm(1)``)."""

    key: str
    value_text: str
    line: int
    col: int


@dataclass(frozen=True)
class Token:
    kind: Kind
    start: int
    end: int


@dataclass(frozen=True)
class NamelistOpen:
    name: str  # as written, without the ``&``
    start: int
    end: int


@dataclass(frozen=True)
class CardHeader:
    name: str  # uppercase
    known: bool
    start: int
    end: int
    option: str = ""
    option_start: int = 0
    option_end: int = 0


@dataclass
class LineScan:
    state: LexState
    tokens: list[Token] = field(default_factory=list)
    opens: NamelistOpen | None = None
    closed: bool = False  # a ``/`` or ``&end`` ended the open namelist on this line
    entries: list[Entry] = field(default_factory=list)
    card: CardHeader | None = None
    body: str | None = None  # a non-blank card body line, comment stripped
    issues: list[LintIssue] = field(default_factory=list)


_AMP = re.compile(r"&(\w*)")
_WORD = re.compile(r"[A-Za-z][A-Za-z_]*")
_UNKNOWN_CARD = re.compile(r"[A-Z][A-Z_]{3,}")
_OPTION_REST = re.compile(r"\s*(?:\{[^}]*\}|\([^)]*\)|[\w-]+)?\s*")
_OPTION = re.compile(r"[^\s{}()]+")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_REPEAT = re.compile(r"\d+\*")
_LOGICAL_OK = {".true.", ".false.", ".t.", ".f.", "t", "f"}
_LOGICAL_LIKE = re.compile(r"\.[A-Za-z]+\.?|[A-Za-z]+\.")
_NUMBERISH = re.compile(r"[-+]?\.?\d")
_BODY_NUMBER = re.compile(r"(?<![\w.])" + NUMBER.pattern + r"(?![\w.])")
_STOPS = "=,/'\""


def _quote_spans(text: str, hash_comments: bool) -> tuple[int, list[tuple[int, int]], int | None]:
    """(where the comment starts, closed-or-not string spans, start of an unclosed quote).

    Quote state is per line, as in QE: a quote never reaches the next line. ``!`` starts a
    comment outside quotes; ``#`` too, except inside a namelist.
    """
    spans: list[tuple[int, int]] = []
    quote, start = "", 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                spans.append((start, i + 1))
                quote = ""
        elif ch in "'\"":
            quote, start = ch, i
        elif ch == "!" or (hash_comments and ch == "#"):
            return i, spans, None
    if quote:
        spans.append((start, len(text)))
        return len(text), spans, start
    return len(text), spans, None


def _paren_pairs(code: str, strings: dict[int, int]) -> tuple[dict[int, int], list[int], list[int]]:
    """Matching ``(``→``)`` outside strings, then the unmatched ``(`` and the stray ``)``."""
    pairs: dict[int, int] = {}
    opened: list[int] = []
    stray: list[int] = []
    i = 0
    while i < len(code):
        if i in strings:
            i = max(strings[i], i + 1)
            continue
        if code[i] == "(":
            opened.append(i)
        elif code[i] == ")":
            if opened:
                pairs[opened.pop()] = i
            else:
                stray.append(i)
        i += 1
    return pairs, opened, stray


def _classify(word: str) -> tuple[Kind | None, str]:
    """(token kind, error message) of an unquoted value. Only wrongly written logicals and
    numbers are errors; anything else is left alone (names of parameters are not checked)."""
    rest = _REPEAT.sub("", word, count=1)
    if rest.lower() in _LOGICAL_OK:
        return Kind.LOGICAL, ""
    if NUMBER.fullmatch(rest):
        return Kind.NUMBER, ""
    if _LOGICAL_LIKE.fullmatch(rest):
        return Kind.LOGICAL, "Valor lógico inválido: use .true. ou .false."
    if _NUMBERISH.match(rest):
        return Kind.NUMBER, "Número inválido"
    return None, ""


@dataclass
class _Atom:
    kind: str  # word, string, eq, comma
    start: int
    end: int


def _atoms(
    code: str, start: int, strings: dict[int, int], pairs: dict[int, int]
) -> tuple[list[_Atom], tuple[int, int] | None]:
    """Top-level pieces of namelist text from ``start`` and the span of the ``/`` (or ``&end``)
    that ended it, or None."""
    atoms: list[_Atom] = []
    i, n = start, len(code)
    while i < n:
        ch = code[i]
        if ch.isspace():
            i += 1
        elif i in strings:
            end = max(strings[i], i + 1)
            atoms.append(_Atom("string", i, end))
            i = end
        elif ch == "=":
            atoms.append(_Atom("eq", i, i + 1))
            i += 1
        elif ch == ",":
            atoms.append(_Atom("comma", i, i + 1))
            i += 1
        elif ch == "/":
            return atoms, (i, i + 1)
        else:
            j = i
            while j < n and not code[j].isspace() and code[j] not in _STOPS:
                j = pairs[j] + 1 if code[j] == "(" and j in pairs else j + 1
            if code[i:j].lower() == "&end":
                return atoms, (i, j)
            if _IDENT.fullmatch(code[i:j]):  # ``celldm (1) = 5``
                k = j
                while k < n and code[k].isspace():
                    k += 1
                if k < n and k in pairs:
                    j = pairs[k] + 1
            atoms.append(_Atom("word", i, max(j, i + 1)))
            i = max(j, i + 1)
    return atoms, None


def _namelist_content(
    scan: LineScan, code: str, start: int, strings: dict[int, int], lineno: int
) -> None:
    """Pairs, comments and the closing ``/`` of namelist text; sets the state it leaves."""
    pairs, opened, stray = _paren_pairs(code, strings)

    def issue(a: int, b: int, message: str) -> None:
        scan.issues.append(LintIssue(lineno, a, b, "error", message))

    for p in opened:
        if p >= start:
            q = p + 1
            while q < len(code) and not code[q].isspace() and code[q] not in "=,/":
                q += 1
            issue(p, q, "Parêntese não fechado")
    for p in stray:
        if p >= start:
            issue(p, p + 1, "Parêntese sem abertura")

    atoms, closer = _atoms(code, start, strings, pairs)
    tokens = scan.tokens
    key: _Atom | None = None
    eq: _Atom | None = None
    values: list[_Atom] = []
    bad: list[int] = []  # [start, end] of the bare values that belong to no pair

    def mark_bad(a: int, b: int) -> None:
        if bad:
            bad[1] = b
        else:
            bad.extend((a, b))

    def finish() -> None:
        if key is None or eq is None:
            return
        name = re.sub(r"\s+", "", code[key.start : key.end]).lower()
        if not values:
            issue(key.start, eq.end, f"Valor ausente para {name}")
            text = ""
        else:
            text = code[values[0].start : values[-1].end]
        scan.entries.append(Entry(name, text, lineno, key.start))

    i = 0
    while i < len(atoms):
        atom = atoms[i]
        nxt = atoms[i + 1] if i + 1 < len(atoms) else None
        if atom.kind in ("word", "string") and nxt is not None and nxt.kind == "eq":
            finish()
            key, eq, values = atom, nxt, []
            tokens.append(Token(Kind.KEY, atom.start, atom.end))
            i += 2
            continue
        i += 1
        if atom.kind == "eq":
            mark_bad(atom.start, atom.end)
        elif atom.kind in ("word", "string"):
            if atom.kind == "string":
                tokens.append(Token(Kind.STRING, atom.start, atom.end))
            else:
                kind, message = _classify(code[atom.start : atom.end])
                if kind is not None:
                    tokens.append(Token(kind, atom.start, atom.end))
                if message:
                    issue(atom.start, atom.end, message)
            if key is not None:
                values.append(atom)
            elif not scan.state.comma:  # first values of the line, not a continuation
                mark_bad(atom.start, atom.end)
    finish()
    if bad:
        issue(bad[0], bad[1], "Esperado 'chave = valor'")

    if closer is not None:
        tokens.append(Token(Kind.NAMELIST, *closer))
        scan.closed = True
        scan.state = LexState()
    else:
        scan.state = LexState(Mode.NAMELIST, bool(atoms) and atoms[-1].kind == "comma")


def _card_header(code: str, first: int, in_namelist: bool, continuing: bool) -> CardHeader | None:
    match = _WORD.match(code, first)
    if match is None:
        return None
    rest = code[match.end() :]
    name = match.group().upper()
    if "=" in code and in_namelist:
        return None
    known = name in KNOWN_CARDS
    if not known and (
        continuing or not _UNKNOWN_CARD.fullmatch(match.group()) or not _OPTION_REST.fullmatch(rest)
    ):
        return None
    option = _OPTION.search(rest)
    if option is None:
        return CardHeader(name, known, first, match.end())
    shift = match.end()
    return CardHeader(
        name,
        known,
        first,
        match.end(),
        option.group(),
        shift + option.start(),
        shift + option.end(),
    )


def scan_line(text: str, state: LexState | None = None, lineno: int = 0) -> LineScan:
    """Tokens, entries, local issues and the next state of one line (no trailing newline)."""
    state = state or LexState()
    scan = LineScan(state)
    mode = state.mode
    code_end, spans, unclosed = _quote_spans(text, mode is not Mode.NAMELIST)
    strings = dict(spans)
    code = text[:code_end]
    if code_end < len(text):
        scan.tokens.append(Token(Kind.COMMENT, code_end, len(text)))
    stripped = code.strip()
    if not stripped:
        return scan  # blank or comment only: the state carries on
    first = len(code) - len(code.lstrip())

    def issue(a: int, b: int, message: str, severity: Severity = "error") -> None:
        scan.issues.append(LintIssue(lineno, a, b, severity, message))

    if stripped.startswith("&"):
        amp = _AMP.match(code, first)
        name = amp.group(1) if amp else ""
        end = amp.end() if amp else first + 1
        if not name:
            issue(first, end, "'&' sem nome de namelist", "warning")
        elif name.lower() == "end":
            scan.tokens.append(Token(Kind.NAMELIST, first, end))
            if mode is Mode.NAMELIST:
                scan.closed = True
                scan.state = LexState()
            else:
                issue(first, end, "'&end' sem namelist aberta", "warning")
        else:
            scan.opens = NamelistOpen(name, first, end)
            scan.tokens.append(Token(Kind.NAMELIST, first, end))
            scan.state = LexState(Mode.NAMELIST)
            if unclosed is not None:
                issue(unclosed, len(text), "Aspas não fechadas")
            _namelist_content(scan, code, end, strings, lineno)
        return scan
    if mode is not Mode.NAMELIST and stripped == "/":
        issue(first, first + 1, "'/' sem namelist aberta", "warning")
        return scan

    header = _card_header(code, first, mode is Mode.NAMELIST, state.comma)
    if header is not None:
        scan.card = header
        scan.state = LexState(Mode.CARD)
        scan.tokens.append(Token(Kind.CARD, header.start, header.end))
        if header.option:
            scan.tokens.append(Token(Kind.CARD_OPTION, header.option_start, header.option_end))
        return scan

    if mode is Mode.NAMELIST:
        if unclosed is not None:
            issue(unclosed, len(text), "Aspas não fechadas")
        _namelist_content(scan, code, first, strings, lineno)
    elif mode is Mode.CARD:
        scan.body = stripped
        if unclosed is not None:
            issue(unclosed, len(text), "Aspas não fechadas")
        for found in _BODY_NUMBER.finditer(code):
            scan.tokens.append(Token(Kind.NUMBER, found.start(), found.end()))
    return scan
