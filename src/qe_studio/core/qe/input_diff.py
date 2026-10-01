"""Comparing two QE inputs (spec 11 R6): by parameter, and line by line.

Both work on text or on the tolerant reader's ``InputDoc``, so inputs with write errors compare too.

``compare_params`` says what *means* something different: ``1d-8``, ``1.0e-8`` and ``1.E-8`` are
the same number, ``.t.`` is ``.true.``, strings differ by neither case nor outer blanks (QE
normalizes most of its string parameters). ``text_rows`` aligns the two files line by line for a
side-by-side view; it ignores nothing unless asked to ignore blanks and comments.
"""

from __future__ import annotations

import re
from collections.abc import Hashable
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import zip_longest
from pathlib import Path
from typing import Literal

from ..sniff import INPUT_READ_LIMIT
from .input_extract import clean
from .input_lexer import Kind, LexState, scan_line
from .input_lint import Card, InputDoc, lint
from .pw_input import fortran_float

Status = Literal["only_a", "only_b", "different"]
Tag = Literal["equal", "add", "del", "change", "ignored"]

_ELEMENT = re.compile(r"'[^']*'?|\"[^\"]*\"?|[^\s,]+")
_REPEAT = re.compile(r"(\d+)\*(.+)")
_LOGICALS = {".true.": True, ".t.": True, "t": True, ".false.": False, ".f.": False, "f": False}
MAX_REPEAT = 1000


@dataclass(frozen=True)
class ParamChange:
    namelist: str
    key: str
    a: str | None  # the value as written (quotes removed); None: not in this file
    b: str | None
    status: Status
    line_a: int | None = None
    line_b: int | None = None


@dataclass(frozen=True)
class CardChange:
    name: str
    status: Status
    differing: int  # body lines that differ
    option_a: str | None
    option_b: str | None
    detail: tuple[tuple[str | None, str | None], ...]  # the differing lines, A then B
    line_a: int | None = None
    line_b: int | None = None

    @property
    def summary(self) -> str:
        if self.status == "only_a":
            return f"{self.name}: só em A"
        if self.status == "only_b":
            return f"{self.name}: só em B"
        parts = []
        if self.option_a != self.option_b:
            parts.append(f"opção {self.option_a or '—'} ↔ {self.option_b or '—'}")
        if self.differing:
            noun = "linha difere" if self.differing == 1 else "linhas diferem"
            parts.append(f"{self.differing} {noun}")
        return f"{self.name}: " + ", ".join(parts)


@dataclass(frozen=True)
class ParamDiff:
    params: tuple[ParamChange, ...]
    cards: tuple[CardChange, ...]

    @property
    def identical(self) -> bool:
        return not self.params and not self.cards


@dataclass(frozen=True)
class TextRow:
    """One row of the side-by-side view: ``(line number, text)`` of each side, None for padding."""

    tag: Tag
    a: tuple[int, str] | None
    b: tuple[int, str] | None


# -- by parameter ------------------------------------------------------------------------------
def _element(token: str) -> Hashable:
    if token[0] in "'\"":
        return ("s", token.strip("'\"").strip().casefold())
    if token.lower() in _LOGICALS:
        return ("b", _LOGICALS[token.lower()])
    number = fortran_float(token)
    if number is not None:
        return ("n", number)
    return ("s", token.casefold())


def normalize_value(text: str) -> tuple[Hashable, ...]:
    """What a namelist value means, to compare it: a tuple of numbers, logicals and strings.
    Repeats (``3*1.0``) are expanded."""
    elements: list[Hashable] = []
    for token in _ELEMENT.findall(text):
        repeat = _REPEAT.fullmatch(token)
        if repeat and int(repeat.group(1)) <= MAX_REPEAT:
            elements.extend([_element(repeat.group(2))] * int(repeat.group(1)))
        else:
            elements.append(_element(token))
    return tuple(elements)


def _normalize_line(line: str) -> tuple[Hashable, ...]:
    return tuple(_element(token) for token in line.split())


def _entries(doc: InputDoc, namelist: str):
    """key → (value, line) of a namelist; the last write of a key wins, as in Fortran."""
    return {e.key: (clean(e.value_text), e.line) for e in doc.namelists.get(namelist, ())}


def _ordered_union(first, second) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def _params(a: InputDoc, b: InputDoc) -> list[ParamChange]:
    changes = []
    for namelist in _ordered_union(a.namelists, b.namelists):
        left, right = _entries(a, namelist), _entries(b, namelist)
        for key in _ordered_union(left, right):
            va, vb = left.get(key), right.get(key)
            if va is not None and vb is not None:
                if normalize_value(va[0]) == normalize_value(vb[0]):
                    continue
                status: Status = "different"
            else:
                status = "only_a" if vb is None else "only_b"
            changes.append(
                ParamChange(
                    namelist,
                    key,
                    va[0] if va else None,
                    vb[0] if vb else None,
                    status,
                    va[1] if va else None,
                    vb[1] if vb else None,
                )
            )
    return changes


def _card_change(name: str, a: Card | None, b: Card | None) -> CardChange | None:
    if a is None or b is None:
        return CardChange(
            name,
            "only_a" if b is None else "only_b",
            0,
            a.option if a else None,
            b.option if b else None,
            (),
            a.line if a else None,
            b.line if b else None,
        )
    norm_a = [_normalize_line(line) for line in a.lines]
    norm_b = [_normalize_line(line) for line in b.lines]
    detail: list[tuple[str | None, str | None]] = []
    differing = 0
    matcher = SequenceMatcher(None, norm_a, norm_b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        differing += max(i2 - i1, j2 - j1)
        left, right = a.lines[i1:i2], b.lines[j1:j2]
        detail.extend(zip_longest(left, right))
    if differing == 0 and a.option.casefold() == b.option.casefold():
        return None
    return CardChange(
        name, "different", differing, a.option, b.option, tuple(detail), a.line, b.line
    )


def compare_params(a: InputDoc, b: InputDoc) -> ParamDiff:
    """What differs between two inputs: parameters by namelist, then cards. Equal → ``identical``."""
    cards_a = {card.name: card for card in reversed(a.cards)}  # the first of a repeated card wins
    cards_b = {card.name: card for card in reversed(b.cards)}
    cards = []
    for name in _ordered_union((c.name for c in a.cards), (c.name for c in b.cards)):
        change = _card_change(name, cards_a.get(name), cards_b.get(name))
        if change is not None:
            cards.append(change)
    return ParamDiff(tuple(_params(a, b)), tuple(cards))


# -- line by line ------------------------------------------------------------------------------
def _lines(text: str) -> list[str]:
    lines = [line.removesuffix("\r") for line in text.split("\n")]
    if lines and lines[-1] == "":  # the newline that ends the last line starts no new one
        lines.pop()
    return lines


def _compared(lines: list[str], ignore: bool) -> list[str]:
    """The text each line is compared by. With ``ignore``: no blanks and no comment (a comment is
    whatever the lexer says it is, in namelists and in cards), and an empty result means the line
    is not compared at all."""
    if not ignore:
        return lines
    state, result = LexState(), []
    for number, line in enumerate(lines, 1):
        scan = scan_line(line, state, number)
        state = scan.state
        comment = next((t for t in scan.tokens if t.kind is Kind.COMMENT), None)
        code = line[: comment.start] if comment else line
        result.append("".join(code.split()))
    return result


def text_rows(a_text: str, b_text: str, ignore: bool = False) -> list[TextRow]:
    """Align two texts line by line. ``equal`` rows hold the same line, ``change`` rows a line that
    differs, ``del``/``add`` rows a line only in A/B (padding on the other side). With ``ignore``,
    differences in blanks and comments do not count, and the lines that are only that come out as
    ``ignored`` rows."""
    lines_a, lines_b = _lines(a_text), _lines(b_text)
    keys_a, keys_b = _compared(lines_a, ignore), _compared(lines_b, ignore)
    index_a = [i for i, key in enumerate(keys_a) if key or not ignore]
    index_b = [i for i, key in enumerate(keys_b) if key or not ignore]
    matcher = SequenceMatcher(
        None, [keys_a[i] for i in index_a], [keys_b[i] for i in index_b], autojunk=False
    )
    rows: list[TextRow] = []
    next_a = next_b = 0

    def emit(tag: Tag, x: int | None, y: int | None) -> None:
        nonlocal next_a, next_b
        skipped_a = range(next_a, x) if x is not None else range(0)
        skipped_b = range(next_b, y) if y is not None else range(0)
        if x is not None:
            next_a = x + 1
        if y is not None:
            next_b = y + 1
        for p, q in zip_longest(skipped_a, skipped_b):
            rows.append(TextRow("ignored", _side(lines_a, p), _side(lines_b, q)))
        rows.append(TextRow(tag, _side(lines_a, x), _side(lines_b, y)))

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left, right = index_a[i1:i2], index_b[j1:j2]
        if tag == "equal":
            for x, y in zip(left, right, strict=True):
                emit("equal", x, y)
            continue
        for x, y in zip_longest(left, right):
            emit(
                "change" if x is not None and y is not None else ("del" if y is None else "add"),
                x,
                y,
            )
    for p, q in zip_longest(range(next_a, len(lines_a)), range(next_b, len(lines_b))):
        rows.append(TextRow("ignored", _side(lines_a, p), _side(lines_b, q)))
    return rows


def _side(lines: list[str], index: int | None) -> tuple[int, str] | None:
    return None if index is None else (index + 1, lines[index])


# -- two files ---------------------------------------------------------------------------------
class TooBigError(ValueError):
    """An input above ``INPUT_READ_LIMIT``: the viewer shows those but does not compare them."""


@dataclass(frozen=True)
class Comparison:
    a: Path
    b: Path
    params: ParamDiff
    rows: dict[bool, list[TextRow]]  # side-by-side rows by ``ignore`` (blanks and comments)


def _read(path: Path) -> str:
    if path.stat().st_size > INPUT_READ_LIMIT:
        raise TooBigError(f"{path.name}: arquivo grande demais para comparar")
    return path.read_text(encoding="utf-8", errors="replace")


def compare_files(a: Path, b: Path) -> Comparison:
    """Read both inputs and compare them every way the diff view shows. Raises ``OSError`` for an
    unreadable file and ``TooBigError`` for one over the limit; write errors in the inputs are no
    obstacle."""
    text_a, text_b = _read(a), _read(b)
    return Comparison(
        a,
        b,
        compare_params(lint(text_a), lint(text_b)),
        {False: text_rows(text_a, text_b, False), True: text_rows(text_a, text_b, True)},
    )
