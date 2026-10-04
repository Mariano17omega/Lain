"""Edits of a QE input that keep everything else as written (spec 24 R1).

``InputEditor`` changes values, entries, namelists and cards in the *text* of an input: comments,
blank lines, the case of names, spacing, line ends and whatever no operation touches stay byte for
byte (``parse_input`` goes through ASE and loses all of that). It reads the text with the lexer of
the viewer and the linter (``scan_line``), so the three agree on what an entry or a card is. Like
pw.x, it acts on the first of a repeated namelist.

It never raises: an operation that fails leaves the text as it was and says why in ``issues``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from .input_lexer import CardHeader, Entry, Kind, LexState, LineScan, Mode, scan_line
from .input_lint import Card

__all__ = ["NAMELIST_ORDER", "InputEditor", "normalize_key", "unquote"]

# The order of pw.x's namelists: a new one goes where it belongs among those present.
NAMELIST_ORDER = ("control", "system", "electrons", "ions", "cell")
DEFAULT_INDENT = "  "
_TRAILING = re.compile(r"\s*,?\s*")  # what follows a removed entry: spaces and its comma
_QUOTES = "'\""

T = TypeVar("T")


@dataclass
class _Namelist:
    name: str  # lowercase
    written: str  # as written, without the ``&``
    open_line: int  # line indices are 0-based
    end_line: int  # the closer's line, or the last line with code when unclosed
    close_col: int | None = None  # column of the ``/`` or ``&end``; None when unclosed
    entries: list[Entry] = field(default_factory=list)  # ``Entry.line`` is a line index here


@dataclass
class _CardSpan:
    header: CardHeader
    line: int
    last: int  # last body line (the header's own when the card has no body)
    body: list[str] = field(default_factory=list)


def normalize_key(key: str) -> str:
    """What the lexer makes of a key: lowercase, no blanks (``celldm (1)`` → ``celldm(1)``)."""
    return re.sub(r"\s+", "", key).lower()


def unquote(value_text: str) -> str:
    text = value_text.strip()
    if len(text) >= 2 and text[0] in _QUOTES and text[-1] == text[0]:
        return text[1:-1]
    return text


def _rank(name: str) -> int:
    return NAMELIST_ORDER.index(name) if name in NAMELIST_ORDER else len(NAMELIST_ORDER)


def _has_code(scan: LineScan) -> bool:
    """Does the line hold more than blanks, commas and a comment?"""
    return bool(
        scan.entries
        or scan.issues
        or scan.opens
        or scan.closed
        or any(token.kind is not Kind.COMMENT for token in scan.tokens)
    )


class InputEditor:
    def __init__(self, lines: list[str], crs: list[bool]):
        self._lines = lines  # without the line end
        self._crs = crs  # whether each line ended with ``\r`` (CRLF files)
        self._new_cr = bool(crs) and crs[0]  # new lines end like the first one
        self.issues: list[str] = []
        self._namelists: list[_Namelist] = []
        self._cards: list[_CardSpan] = []
        self._index()

    @classmethod
    def from_text(cls, text: str) -> InputEditor:
        raw = text.split("\n")
        return cls([line.removesuffix("\r") for line in raw], [line.endswith("\r") for line in raw])

    def text(self) -> str:
        return "\n".join(line + "\r" * cr for line, cr in zip(self._lines, self._crs, strict=True))

    # -- reading ------------------------------------------------------------------------------
    def get(self, namelist: str, key: str) -> str | None:
        """The value of ``key`` (the last one, as Fortran reads it) without outer quotes."""
        value = self.raw(namelist, key)
        return None if value is None else unquote(value)

    def raw(self, namelist: str, key: str) -> str | None:
        """The value of ``key`` as written, quotes included."""
        entries = self._entries(namelist, key)
        return entries[-1].value_text if entries else None

    def keys(self, namelist: str) -> list[str]:
        block = self._first(namelist)
        return list(dict.fromkeys(entry.key for entry in block.entries)) if block else []

    def has_namelist(self, name: str) -> bool:
        return self._first(name) is not None

    def card(self, name: str) -> Card | None:
        span = self._card(name)
        if span is None:
            return None
        return Card(span.header.name, span.header.option.lower(), span.line + 1, tuple(span.body))

    # -- editing ------------------------------------------------------------------------------
    def set(self, namelist: str, key: str, value_text: str) -> None:
        """Write ``value_text`` (as it goes in the file: quotes included) as the value of ``key``.

        Every occurrence changes in place; a missing key is a new line at the end of the namelist,
        and a missing namelist is created where pw.x's order puts it."""
        self._guarded(f"{namelist}.{key}", lambda: self._set(namelist, key, value_text), None)

    def remove(self, namelist: str, key: str) -> bool:
        """Remove every ``key = value`` of the namelist: the whole line, or only the entry (and its
        comma) when the line holds something else."""
        return self._guarded(f"{namelist}.{key}", lambda: self._remove(namelist, key), False)

    def remove_namelist(self, name: str) -> bool:
        """Remove the first ``&name`` from its opening to its ``/`` (or ``&end``)."""
        return self._guarded(f"&{name}", lambda: self._remove_namelist(name), False)

    def replace_card(self, name: str, option: str, body: list[str]) -> None:
        """Swap the header option and the body of the card (up to its last body line: the blank
        lines and comments after it stay); a missing card is added at the end."""
        self._guarded(name, lambda: self._replace_card(name, option, body), None)

    # -- internals ----------------------------------------------------------------------------
    def _guarded(self, what: str, action: Callable[[], T], default: T) -> T:
        lines, crs = list(self._lines), list(self._crs)
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - never raise on odd input (R1.3)
            self._lines, self._crs = lines, crs
            self._index()
            self.issues.append(f"Não foi possível editar {what}: {exc}")
            return default

    def _index(self) -> None:
        try:
            self._scan()
        except Exception as exc:  # noqa: BLE001 - an input the lexer cannot read is left alone
            self._namelists, self._cards = [], []
            self.issues.append(f"Input não pôde ser lido: {exc}")

    def _scan(self) -> None:
        self._namelists, self._cards = [], []
        state = LexState()
        current: _Namelist | None = None  # the namelist being read
        card: _CardSpan | None = None
        for i, line in enumerate(self._lines):
            scan = scan_line(line, state, i)
            if scan.opens is not None or scan.card is not None:
                current = card = None  # a new block ends an unclosed namelist and the card
            if scan.opens is not None:
                current = _Namelist(scan.opens.name.lower(), scan.opens.name, i, i)
                self._namelists.append(current)
            if current is not None and _has_code(scan):
                current.end_line = i
                current.entries.extend(scan.entries)
                if scan.closed:
                    closer = [t for t in scan.tokens if t.kind is Kind.NAMELIST][-1]
                    current.close_col = closer.start
                    current = None
            if scan.card is not None:
                card = _CardSpan(scan.card, i, i)
                self._cards.append(card)
            elif scan.body is not None and card is not None:
                card.last = i
                card.body.append(scan.body)
            state = scan.state

    def _first(self, name: str) -> _Namelist | None:
        name = name.lower().lstrip("&")
        return next((block for block in self._namelists if block.name == name), None)

    def _entries(self, namelist: str, key: str) -> list[Entry]:
        block = self._first(namelist)
        key = normalize_key(key)
        return [entry for entry in block.entries if entry.key == key] if block else []

    def _card(self, name: str) -> _CardSpan | None:
        name = name.upper()
        return next((span for span in self._cards if span.header.name == name), None)

    def _replace(self, start: int, end: int, new: list[str]) -> None:
        """Lines ``start..end - 1`` become ``new``; the last line of the file keeps its end."""
        crs = [self._new_cr] * len(new)
        if end == len(self._lines) and end > start:  # the file's last line goes
            if new:
                crs[-1] = self._crs[-1]
            elif start > 0:
                self._crs[start - 1] = self._crs[-1]
        self._lines[start:end] = new
        self._crs[start:end] = crs
        if not self._lines:
            self._lines, self._crs = [""], [False]

    def _append_block(self, new: list[str]) -> None:
        """Add lines at the end of the file, before its final line end if it has one."""
        if self._lines[-1] == "":
            self._replace(len(self._lines) - 1, len(self._lines) - 1, new)
        else:
            self._crs[-1] = self._new_cr
            self._lines.extend(new)
            self._crs.extend([self._new_cr] * (len(new) - 1) + [False])

    def _set(self, namelist: str, key: str, value: str) -> None:
        block = self._first(namelist)
        if block is None:
            self._insert_namelist(namelist, [f"{DEFAULT_INDENT}{key} = {value}"])
        elif entries := self._entries(namelist, key):
            for entry in sorted(entries, key=lambda e: (e.line, e.value_start), reverse=True):
                line = self._lines[entry.line]
                empty = entry.value_start == entry.value_end
                pad = " " if empty and line[: entry.value_start].endswith("=") else ""
                self._lines[entry.line] = (
                    f"{line[: entry.value_start]}{pad}{value}{line[entry.value_end :]}"
                )
        else:
            self._add_entry(block, f"{key} = {value}")
        self._index()

    def _add_entry(self, block: _Namelist, entry: str) -> None:
        if block.close_col is None:  # unclosed: after its last line
            self._replace(block.end_line + 1, block.end_line + 1, [self._indent(block) + entry])
            return
        line = self._lines[block.end_line]
        before = line[: block.close_col]
        if not before.strip():  # the ``/`` alone: a new line above it
            self._replace(block.end_line, block.end_line, [self._indent(block) + entry])
            return
        head = before.rstrip()  # ``&ions /`` or ``x = 1 /``: the entry goes before the ``/``
        if any(e.line == block.end_line for e in block.entries) and not head.endswith(","):
            head += ","
        self._lines[block.end_line] = f"{head} {entry} {line[block.close_col :]}"

    def _indent(self, block: _Namelist) -> str:
        for entry in reversed(block.entries):
            if entry.line != block.open_line:
                line = self._lines[entry.line]
                return line[: len(line) - len(line.lstrip())]
        return DEFAULT_INDENT

    def _insert_namelist(self, name: str, body: list[str]) -> None:
        name = name.lower().lstrip("&")
        firsts = list({block.name: block for block in reversed(self._namelists)}.values())
        upper = not firsts or min(firsts, key=lambda b: b.open_line).written.isupper()
        lines = [f"&{name.upper() if upper else name}", *body, "/"]
        rank = _rank(name)
        before = [b for b in firsts if _rank(b.name) < rank or rank == len(NAMELIST_ORDER)]
        if before:
            at = max(block.end_line for block in before) + 1
        elif self._namelists or self._cards:
            at = min([b.open_line for b in self._namelists] + [c.line for c in self._cards])
        else:
            self._append_block(lines)
            return
        self._replace(at, at, lines)

    def _remove(self, namelist: str, key: str) -> bool:
        removed = False
        for _ in range(len(self._entries(namelist, key))):
            block = self._first(namelist)
            entries = self._entries(namelist, key)
            if block is None or not entries:
                break
            self._remove_entry(block, entries[-1])
            self._index()
            removed = True
        return removed

    def _remove_entry(self, block: _Namelist, entry: Entry) -> None:
        line = self._lines[entry.line]
        rest = line[entry.value_end :]
        trailing = _TRAILING.match(rest)
        new = line[: entry.col] + rest[trailing.end() if trailing else 0 :]
        own_line = entry.line != block.open_line and not (
            block.close_col is not None and entry.line == block.end_line
        )
        if own_line and not _has_code(scan_line(new, LexState(Mode.NAMELIST))):
            self._replace(entry.line, entry.line + 1, [])
        else:
            self._lines[entry.line] = new

    def _remove_namelist(self, name: str) -> bool:
        block = self._first(name)
        if block is None:
            return False
        self._replace(block.open_line, block.end_line + 1, [])
        self._index()
        return True

    def _replace_card(self, name: str, option: str, body: list[str]) -> None:
        span = self._card(name)
        if span is None:
            self._append_block([f"{name.upper()} {option}".rstrip(), *body])
        else:
            self._replace(span.line, span.last + 1, [self._header(span, option), *body])
        self._index()

    def _header(self, span: _CardSpan, option: str) -> str:
        """The header line with ``option`` in place of the old one (brackets kept)."""
        header, line = span.header, self._lines[span.line]
        if not option:
            return line[: header.end]
        if header.option:
            return line[: header.option_start] + option + line[header.option_end :]
        return f"{line[: header.end]} {option}{line[header.end :]}"
