"""What the quick filter of the explorer and the file grid accepts, without widgets (spec 16 R3).

A name filter is text: a case-insensitive substring in which ``*`` and ``?`` are wildcards. A
category filter picks folders by the badge detection gave them and files by their state and visual
type. The panels' proxy models compute the facts of a row (from caches only) and ask these.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

BADGES = ("BANDS", "PDOS", "RELAX", "SCF", "CALC")
NO_BADGE = "sem tipo"  # a folder detection found nothing in
STATES = ("OK", "INCOMPLETO", "AVISO", "SEM ERROS", "ERRO")  # file_kinds.status_label
NO_STATE = "sem estado"
VISUALS = ("inputs", "saídas", "dados", "imagens", "outros")


def name_matcher(text: str) -> Callable[[str], bool]:
    """The test of a name filter: any name when ``text`` is empty, else a name containing
    ``text`` ignoring case, with ``*`` for any run of characters and ``?`` for one. Everything
    else is literal, so pasted paths and regex-looking names never raise."""
    if not text:
        return lambda name: True
    if "*" not in text and "?" not in text:
        needle = text.casefold()
        return lambda name: needle in name.casefold()
    parts = (".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in text)
    pattern = re.compile("".join(parts), re.IGNORECASE | re.DOTALL)
    return lambda name: pattern.search(name) is not None


@dataclass(frozen=True)
class CategoryFilter:
    """The ticked categories. Within a group a match on any ticked value is enough; between the
    file groups (state, visual type) both must match.

    Badges are for folders and states / visual types for files. A kind with nothing ticked is
    hidden while the other kind has something: "INCOMPLETO" alone lists only that file, "RELAX"
    alone only the folders detected as relax.
    """

    badges: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    visuals: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        return bool(self.badges or self.states or self.visuals)

    @property
    def files_selected(self) -> bool:
        return bool(self.states or self.visuals)

    def accepts_folder(self, badges: list[str] | None) -> bool:
        """``badges``: those of the folder's cached detection, ``[]`` when detection found none,
        None while it has not run (the folder stays, as "detectando…", until it does)."""
        if not self.active:
            return True
        if not self.badges:
            return False  # only files were asked for
        if badges is None:
            return True
        return bool(self.badges.intersection(badges or [NO_BADGE]))

    def accepts_file(self, state: str | None, visual: str) -> bool:
        """``state``: the ``status_label`` text of the file, None when it has none."""
        if not self.active:
            return True
        if not self.files_selected:
            return False  # only folders were asked for
        if self.states and (state or NO_STATE) not in self.states:
            return False
        return not self.visuals or visual in self.visuals

    def is_pending(self, badges: list[str] | None) -> bool:
        """A folder shown only because its detection is still to come."""
        return badges is None and bool(self.badges)
