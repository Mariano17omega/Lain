"""Chemical formula from the site list a pw.x output prints in its header (no ASE)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

# One line of "site n.  atom  positions (alat units)": ``    1   Si   tau(   1) = ( 0.0 … )``.
SITE = re.compile(r"^\s*(?P<index>\d+)\s+(?P<species>[A-Za-z][A-Za-z0-9_-]*)\s+tau\(")


def format_formula(species: Mapping[str, int]) -> str | None:
    """``{"Al": 4, "O": 18}`` → ``Al4O18``, in order of appearance; None when empty."""
    return "".join(f"{name}{count if count > 1 else ''}" for name, count in species.items()) or None


def header_formula(path: Path) -> str | None:
    """Formula of the first site list of a pw.x output, reading no further than its end (or the
    ``number of k points`` line that follows it); None if the file has no list or is unreadable."""
    species: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = SITE.match(line) if "tau(" in line else None
                if match is not None:
                    name = match.group("species")
                    species[name] = species.get(name, 0) + 1
                elif species or "number of k points" in line:
                    break
    except OSError:
        return None
    return format_formula(species)
