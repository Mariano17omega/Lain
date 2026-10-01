"""Tolerant reader and write-only checker of QE inputs (spec 11 R1, R2).

``lint`` never raises and keeps tokenizing after an error, so a broken input still gives the viewer,
the extract strip and the diff something to work with. It checks how things are *written* (quotes,
``/``, ``=``, parentheses, logicals, numbers, namelist and card names), not what the parameters
mean: an unknown parameter name is advanced validation, left for later.

The line-level rules live in ``input_lexer``; this module adds the ones that need the whole file.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .input_lexer import (
    CARD_OPTIONS,
    KNOWN_CARDS,
    CardHeader,
    Entry,
    LexState,
    LintIssue,
    NamelistOpen,
    Severity,
    scan_line,
)
from .pw_input import PROGRAM_NAMELISTS, deduce_program

__all__ = ["Card", "Entry", "InputDoc", "LintIssue", "lint", "neighbour_issue"]

_ALL_NAMELISTS = frozenset().union(*PROGRAM_NAMELISTS.values())


@dataclass(frozen=True)
class Card:
    name: str  # uppercase
    option: str  # lowercase, no braces or parentheses; "" when absent
    line: int  # 1-based line of the card name
    lines: tuple[str, ...]  # body: comments and blank lines dropped


@dataclass
class InputDoc:
    program: str | None = None
    # Entries of the first occurrence of each namelist (pw.x ignores a repeated one), by lowercase name.
    namelists: dict[str, list[Entry]] = field(default_factory=dict)
    namelist_lines: dict[str, int] = field(default_factory=dict)  # line of each ``&name``
    cards: list[Card] = field(default_factory=list)
    issues: list[LintIssue] = field(default_factory=list)

    def get(self, namelist: str, key: str) -> Entry | None:
        for entry in self.namelists.get(namelist, ()):
            if entry.key == key.lower():
                return entry
        return None

    def card(self, name: str) -> Card | None:
        return next((card for card in self.cards if card.name == name), None)


def _distance(a: str, b: str) -> int:
    """Levenshtein distance (names here are a dozen characters, so the plain version will do)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]


def _closest(name: str, candidates: Iterable[str]) -> str | None:
    """The candidate within 2 edits of ``name`` (1 for names of up to 3 letters, or nearly any
    short word would match ``dos`` and ``fcp``). An exact match is not a suggestion."""
    best, best_distance = None, 99
    for candidate in sorted(candidates):
        distance = _distance(name, candidate)
        limit = 1 if len(candidate) <= 3 else 2
        if 0 < distance <= limit and distance < best_distance:
            best, best_distance = candidate, distance
    return best


@dataclass
class _CardBuild:
    header: CardHeader
    line: int
    body: list[str] = field(default_factory=list)

    def build(self) -> Card:
        option = self.header.option.lower()
        return Card(self.header.name, option, self.line, tuple(self.body))


def _lint(text: str) -> InputDoc:
    doc = InputDoc()
    state = LexState()
    opened: list[tuple[str, NamelistOpen, int]] = []  # every ``&name``: lowercase, token, line
    unclosed: tuple[str, NamelistOpen, int] | None = None
    reading: str | None = None  # namelist whose entries are kept (None: a repeated one)
    building: _CardBuild | None = None
    headers: list[tuple[CardHeader, int]] = []

    def rule(line: int, start: int, end: int, message: str, severity: Severity = "error") -> None:
        doc.issues.append(LintIssue(line, start, end, severity, message))

    def unclosed_issue(item: tuple[str, NamelistOpen, int]) -> None:
        _, token, line = item
        name = token.name.upper()
        rule(line, token.start, token.end, f"&{name} não foi fechada com '/'")

    for number, raw in enumerate(text.split("\n"), 1):
        line = raw[:-1] if raw.endswith("\r") else raw
        scan = scan_line(line, state, number)
        doc.issues.extend(scan.issues)

        if scan.opens is not None or scan.card is not None:
            if unclosed is not None:  # the next namelist or a card ends it without a ``/``
                unclosed_issue(unclosed)
                unclosed = None
            if building is not None:
                doc.cards.append(building.build())
                building = None

        if scan.opens is not None:
            name = scan.opens.name.lower()
            item = (name, scan.opens, number)
            repeated = name in doc.namelists
            opened.append(item)
            if repeated:
                reading = None
                rule(
                    number,
                    scan.opens.start,
                    scan.opens.end,
                    f"&{name.upper()} repetida: o pw.x lê só a primeira",
                    "warning",
                )
            else:
                reading = name
                doc.namelists[name] = []
                doc.namelist_lines[name] = number
            unclosed = item
        if scan.entries and reading is not None:
            doc.namelists[reading].extend(scan.entries)
        if scan.closed:
            unclosed = None
            reading = None

        if scan.card is not None:
            building = _CardBuild(scan.card, number)
            headers.append((scan.card, number))
        elif scan.body is not None and building is not None:
            building.body.append(scan.body)
        state = scan.state

    if unclosed is not None:
        unclosed_issue(unclosed)
    if building is not None:
        doc.cards.append(building.build())

    doc.program = deduce_program(name for name, _, _ in opened)
    _check_names(doc, opened, headers, rule)
    doc.issues.sort(key=lambda issue: (issue.line, issue.col_start, issue.col_end))
    return doc


def _check_names(doc: InputDoc, opened, headers, rule) -> None:
    """Rules 8–10: unknown namelists and cards, invalid card options. They need the program, so
    they stay off for ph.x, pp.x, neb.x… (``program is None``), except for a namelist that is
    nearly a known one."""
    program = doc.program
    known = PROGRAM_NAMELISTS[program] if program else frozenset()
    seen: set[str] = set()
    for name, token, line in opened:
        if name in seen or name in known:
            seen.add(name)
            continue
        seen.add(name)
        suggestion = _closest(name, known or _ALL_NAMELISTS)
        if program is None and suggestion is None:
            continue
        message = f"Namelist desconhecida &{name.upper()}"
        if suggestion:
            message += f" (quis dizer &{suggestion.upper()}?)"
        rule(line, token.start, token.end, message)
    if program is None:
        return
    for header, line in headers:
        if not header.known:
            suggestion = _closest(header.name, KNOWN_CARDS)
            message = f"Card desconhecido {header.name}"
            if suggestion:
                message += f" (quis dizer {suggestion}?)"
            rule(line, header.start, header.end, message)
            continue
        options = CARD_OPTIONS.get(header.name)
        if options and header.option and header.option.lower() not in options:
            message = f"Opção inválida para {header.name}: {header.option}"
            rule(line, header.option_start, header.option_end, message)


def lint(text: str) -> InputDoc:
    """Read ``text`` as a QE input. Never raises: whatever it cannot read is simply not there."""
    try:
        return _lint(text)
    except Exception:  # noqa: BLE001 - the viewer must open any file; tests call ``_lint`` bare
        return InputDoc()


def neighbour_issue(issues: list[LintIssue], line: int, forward: bool = True) -> LintIssue | None:
    """The next (or previous) issue on another line than ``line``, wrapping around the file.
    ``issues`` must be sorted, as ``lint`` leaves them."""
    if not issues:
        return None
    if forward:
        return next((i for i in issues if i.line > line), issues[0])
    return next((i for i in reversed(issues) if i.line < line), issues[-1])
