"""Fuzzy matching of the command palette (spec 18 R2): subsequence, case and accent blind.

A query matches a text when its letters appear in the text in order. The score ranks a match: a
prefix beats the start of a word, which beats a plain subsequence. No Qt, no disk.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SCOPES = {">": "Ações", "/": "Pastas", "@": "Abas"}
_BOUNDARIES = " _-./\\"
PREFIX, WORD, SUBSEQUENCE = 3000, 2000, 1000


@dataclass(frozen=True)
class Candidate:
    """One palette row: ``key`` identifies it for recency, ``category`` is the scope's name."""

    key: str
    category: str
    text: str


def fold(text: str) -> str:
    """Lower case without accents (``Gráfico`` → ``grafico``)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def parse_query(text: str) -> tuple[str | None, str]:
    """Split an optional scope prefix: ``">ger"`` → (``"Ações"``, ``"ger"``)."""
    stripped = text.lstrip()
    if stripped and stripped[0] in SCOPES:
        return SCOPES[stripped[0]], stripped[1:].strip()
    return None, text.strip()


def score(query: str, text: str) -> int | None:
    """Rank of ``query`` in ``text``, higher is better; None when it is not a subsequence."""
    phrase, hay = fold(query).strip(), fold(text)
    if not phrase:
        return 0
    if hay.startswith(phrase):
        return PREFIX - len(hay)
    for start in range(1, len(hay)):
        if hay[start - 1] in _BOUNDARIES and hay.startswith(phrase, start):
            return WORD - start - len(hay)
    # Subsequence: each letter takes its first occurrence; gaps and a late start cost points.
    position, first, gaps = -1, -1, 0
    for letter in phrase.replace(" ", ""):
        found = hay.find(letter, position + 1)
        if found < 0:
            return None
        if first < 0:
            first = found
        elif found > position + 1:
            gaps += found - position - 1
        position = found
    return SUBSEQUENCE - gaps - first - len(hay) // 4


def rank(
    query: str,
    candidates: Sequence[Candidate],
    recency: Mapping[str, int] | None = None,
    limit: int = 50,
) -> list[Candidate]:
    """The ``limit`` best candidates for ``query`` (with its optional scope prefix).

    Ties go to the most recently used (``recency``: key → larger is newer), then to the text. An
    empty query keeps the candidates in the order given.
    """
    scope, needle = parse_query(query)
    pool = [c for c in candidates if scope is None or c.category == scope]
    if not needle:
        return pool[:limit]
    recency = recency or {}
    scored: list[tuple[int, int, Candidate]] = []
    for candidate in pool:
        value = score(needle, candidate.text)
        if value is not None:
            scored.append((value, recency.get(candidate.key, 0), candidate))
    scored.sort(key=lambda row: (-row[0], -row[1], row[2].text))
    return [row[2] for row in scored[:limit]]
