"""Chemical formula from the site list a pw.x output prints in its header (no ASE)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# One line of "site n.  atom  positions (alat units)": ``    1   Si   tau(   1) = ( 0.0 … )``.
SITE = re.compile(r"^\s*(?P<index>\d+)\s+(?P<species>[A-Za-z][A-Za-z0-9_-]*)\s+tau\(")
_ALAT = re.compile(
    r"lattice parameter \(alat\)\s*=\s*(?P<alat>\d+\.?\d*(?:[eEdD][+-]?\d+)?)\s*a\.u\."
)
_NUMBER = re.compile(r"[-+]?\d+\.\d*(?:[eEdD][+-]?\d+)?")
BOHR_TO_ANGSTROM = 0.529177210903


@dataclass(frozen=True)
class Site:
    """One atom of the pw.x site list: its 1-based index (the ``N`` of ``pdos_atm#N``), the species
    label and the Cartesian position in Å."""

    index: int
    species: str
    x: float
    y: float
    z: float


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


def read_sites(path: Path) -> list[Site]:
    """The atoms of the first site list of a pw.x output, positions in Å (``alat`` is read from the
    same header). Streams the header only; an unreadable file, a missing ``alat`` or no list give an
    empty list, never an error."""
    alat: float | None = None
    sites: list[Site] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if alat is None and "lattice parameter (alat)" in line:
                    found = _ALAT.search(line)
                    alat = (
                        float(found.group("alat").replace("D", "E").replace("d", "e"))
                        if found
                        else None
                    )
                match = SITE.match(line) if "tau(" in line else None
                if match is None:
                    if sites or "number of k points" in line:
                        break
                    continue
                numbers = _NUMBER.findall(line.partition("=")[2])
                if alat is None or len(numbers) < 3:
                    return []
                x, y, z = (
                    float(n.replace("D", "E").replace("d", "e")) * alat * BOHR_TO_ANGSTROM
                    for n in numbers[:3]
                )
                sites.append(Site(int(match.group("index")), match.group("species"), x, y, z))
    except (OSError, ValueError):
        return []
    return sites
