"""Lexical layer of the pw.x input: split the text into namelists and cards, tolerantly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CARD_NAMES = frozenset(
    {
        "ATOMIC_SPECIES",
        "ATOMIC_POSITIONS",
        "K_POINTS",
        "ADDITIONAL_K_POINTS",
        "CELL_PARAMETERS",
        "REF_CELL_PARAMETERS",
        "CONSTRAINTS",
        "OCCUPATIONS",
        "ATOMIC_FORCES",
        "ATOMIC_VELOCITIES",
        "AUTOPILOT",
        "PLOT_WANNIER",
        "SOLVENTS",
        "HUBBARD",
    }
)


@dataclass
class Card:
    name: str  # upper case
    option: str  # lower case, brackets removed, e.g. "angstrom" or "alat= 10.2"
    lines: list[tuple[int, str]] = field(default_factory=list)  # (line number, text)


@dataclass
class RawInput:
    namelists: dict[str, dict[str, str]] = field(default_factory=dict)  # lower name -> key -> value
    cards: dict[str, Card] = field(default_factory=dict)  # first occurrence of each card


_NAMELIST_HEADER = re.compile(r"&\s*([A-Za-z_]\w*)")
_CARD_HEADER = re.compile(r"([A-Za-z_]+)(.*)$")
_KEY = re.compile(r"([A-Za-z_][\w%]*)\s*(\(\s*[\w\s,+\-]*\))?\s*=")
_STRING_SLOT = re.compile(r"\x00(\d+)\x00")


def _scan(text: str, targets: str) -> int:
    """Index of the first char of ``targets`` that is outside quotes, or -1."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in targets:
            return i
    return -1


def _strip_comment(line: str, markers: str) -> str:
    cut = _scan(line, markers)
    return line if cut < 0 else line[:cut]


def _card_header(text: str) -> tuple[str, str] | None:
    match = _CARD_HEADER.match(text)
    if match is None or match.group(1).upper() not in CARD_NAMES:
        return None
    if match.group(2).lstrip().startswith("="):  # a namelist key such as ``occupations = ...``
        return None
    option = re.sub(r"[(){}]", " ", match.group(2))
    return match.group(1).upper(), re.sub(r"\s+", " ", option).strip().lower()


def _mask_strings(text: str) -> tuple[str, list[str]]:
    strings: list[str] = []
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "'\"":
            j = text.find(ch, i + 1)
            if j < 0:
                j = len(text)
            strings.append(text[i + 1 : j])
            out.append(f"\x00{len(strings) - 1}\x00")
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out), strings


def parse_namelist(content: str) -> dict[str, str]:
    """``key = value`` pairs of one namelist body; keys lower-cased without spaces."""
    masked, strings = _mask_strings(content)
    matches = list(_KEY.finditer(masked))
    values: dict[str, str] = {}
    for n, match in enumerate(matches):
        end = matches[n + 1].start() if n + 1 < len(matches) else len(masked)
        chunk = masked[match.end() : end].strip().strip(",").strip()
        first = re.split(r"[,\s]+", chunk)[0] if chunk else ""
        slot = _STRING_SLOT.fullmatch(first)
        value = strings[int(slot.group(1))] if slot else first
        key = match.group(1).lower() + re.sub(r"\s+", "", match.group(2) or "").lower()
        values[key] = value.strip()
    return values


def split_input(text: str) -> RawInput:
    """Split the input text into namelists and cards. Never raises."""
    raw = RawInput()
    namelist: str | None = None
    body: list[str] = []
    card: Card | None = None

    def close_namelist() -> None:
        nonlocal namelist, body
        if namelist is not None:
            raw.namelists.setdefault(namelist, parse_namelist(" ".join(body)))
        namelist, body = None, []

    for number, original in enumerate(text.splitlines(), start=1):
        rest = _strip_comment(original, "!" if namelist else "!#").strip()
        while rest:
            if namelist is not None:
                if _card_header(rest) is not None:  # namelist never closed with "/"
                    close_namelist()
                    continue
                cut = _scan(rest, "/")
                if cut < 0 and rest.lower() == "&end":
                    cut = 0
                if cut < 0:
                    body.append(rest)
                    rest = ""
                else:
                    body.append(rest[:cut])
                    close_namelist()
                    rest = rest[cut + 1 :].strip()
                continue
            header = _NAMELIST_HEADER.match(rest)
            if header is not None:
                card = None
                namelist = header.group(1).lower()
                rest = rest[header.end() :].strip()
                continue
            card_header = _card_header(rest)
            if card_header is not None:
                card = Card(card_header[0], card_header[1])
                raw.cards.setdefault(card.name, card)
            elif card is not None:
                card.lines.append((number, rest))
            rest = ""
    close_namelist()
    return raw
