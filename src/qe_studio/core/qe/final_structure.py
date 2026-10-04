"""The relaxed structure a relax / vc-relax output prints at the end (spec 24 R3.1).

pw.x prints positions (and, in a vc-relax, the cell) after every BFGS step; the final ones are
those between ``Begin final coordinates`` and ``End final coordinates``::

    Begin final coordinates
         new unit-cell volume =   2253.94778 a.u.^3 (   334.00060 Ang^3 )
         density =      2.56697 g/cm^3

    CELL_PARAMETERS (angstrom)            or (alat= 10.16863713), (bohr); vc-relax only
       5.189525088  -0.000422155   0.002783029
       …
    ATOMIC_POSITIONS (crystal)            the unit of the input's card
    Al            0.2971900999        0.4937797529        0.4786875228
    Si            0.0000000000        0.0000000000        0.0000000000    0   0   0
    End final coordinates

Lines are kept as printed (species, coordinates and the ``if_pos`` flags when the input had them),
so the SCF built from them writes exactly what pw.x converged to. The file is streamed and reading
stops at ``End final coordinates``: relax outputs can be hundreds of MB. Workers only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .relax import NUMBER

BEGIN, END = "Begin final coordinates", "End final coordinates"
_CELL = re.compile(rf"^\s*CELL_PARAMETERS\s*\(\s*(alat|bohr|angstrom)\s*(?:=\s*({NUMBER}))?\s*\)")
_POSITIONS = re.compile(r"^\s*ATOMIC_POSITIONS\s*\(\s*(\w+)\s*\)")


@dataclass(frozen=True)
class FinalPositions:
    unit: str  # alat | bohr | angstrom | crystal
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FinalCell:
    unit: str  # alat | bohr | angstrom
    alat: str | None  # the ``alat= x`` of the header, as printed (8 decimals), in bohr
    rows: tuple[str, ...]


@dataclass(frozen=True)
class FinalStructure:
    positions: FinalPositions
    cell: FinalCell | None  # vc-relax only


def parse_final_structure(lines: Iterable[str]) -> FinalStructure | None:
    """The first final block of ``lines``; None without one (or without its ``End``)."""
    inside = False
    cell: list[str] | None = None
    cell_unit, alat = "", None
    positions: list[str] | None = None
    positions_unit = ""
    for raw in lines:
        if not inside:
            inside = BEGIN in raw
            continue
        line = raw.rstrip()
        if END in line:
            if positions is None:
                return None
            final_cell = FinalCell(cell_unit, alat, tuple(cell)) if cell is not None else None
            return FinalStructure(FinalPositions(positions_unit, tuple(positions)), final_cell)
        if match := _CELL.match(line):
            cell, cell_unit, alat = [], match.group(1), match.group(2)
            positions = None
        elif match := _POSITIONS.match(line):
            positions, positions_unit = [], match.group(1)
        elif not line.strip():
            continue
        elif positions is not None:
            positions.append(line)
        elif cell is not None and len(cell) < 3:
            cell.append(line)
    return None


def read_final_structure(path: Path) -> FinalStructure | None:
    """``parse_final_structure`` of a file, streamed."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_final_structure(handle)
