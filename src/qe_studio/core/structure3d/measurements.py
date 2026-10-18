"""The measures of one 3D window (spec 44 R1.2): a mode ("distancia" or "angulo"), the atoms clicked so far
and the measure each complete pair or trio makes.

Each pair (or trio) is independent: when it is complete the measure is made and the pending atoms start
over, so clicks 3 and 4 make a second pair. The vertex of an angle is the second atom clicked. An atom
already pending is ignored (no zero distance, no angle with a repeated atom).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ...i18n import _
from .measure import angle, distance
from .model import AtomRef, Structure, atom_name

__all__ = [
    "KIND_LABEL",
    "NEEDED",
    "MeasureMode",
    "Measurement",
    "Measurer",
    "number_text",
    "row_text",
    "to_tsv",
]

MeasureMode = Literal["distancia", "angulo"]
NEEDED: dict[str, int] = {"distancia": 2, "angulo": 3}
KIND_LABEL: dict[str, str] = {"distancia": _("Distância"), "angulo": _("Ângulo")}
DECIMALS: dict[str, int] = {"distancia": 3, "angulo": 2}
UNIT: dict[str, str] = {"distancia": " Å", "angulo": "°"}
DASH = "—"


@dataclass(frozen=True)
class Measurement:
    kind: MeasureMode
    refs: tuple[AtomRef, ...]
    value: float  # Å or degrees; NaN for an angle with a zero arm


class Measurer:
    def __init__(self, structure: Structure):
        self.structure = structure
        self.mode: MeasureMode | None = None
        self.pending: tuple[AtomRef, ...] = ()

    def set_mode(self, mode: MeasureMode | None) -> None:
        """Change the mode (None: nothing is measured); the pending atoms are dropped."""
        self.mode = mode
        self.pending = ()

    def clear_pending(self) -> None:
        self.pending = ()

    def click(self, ref: AtomRef) -> Measurement | None:
        """Take a clicked atom; the measure when it completes a pair or trio, else None."""
        if self.mode is None or ref in self.pending:
            return None
        self.pending = (*self.pending, ref)
        if len(self.pending) < NEEDED[self.mode]:
            return None
        refs, self.pending = self.pending, ()
        if self.mode == "distancia":
            value = distance(self.structure, refs[0], refs[1])
        else:
            value = angle(self.structure, refs[0], refs[1], refs[2])
        return Measurement(self.mode, refs, value)


def number_text(m: Measurement) -> str:
    """The value without unit (3 decimals for a distance, 2 for an angle); "" when undefined."""
    return "" if math.isnan(m.value) else f"{m.value:.{DECIMALS[m.kind]}f}"


def row_text(structure: Structure, m: Measurement) -> tuple[str, str]:
    """``("O1 - O2", "1.500 Å")`` / ``("O1 - O2 - O3", "120.00°")``; an undefined angle is "—"."""
    atoms = " - ".join(atom_name(structure, ref) for ref in m.refs)
    number = number_text(m)
    return atoms, (number + UNIT[m.kind]) if number else DASH


def to_tsv(structure: Structure, measurements: Sequence[Measurement]) -> str:
    """Every measure as tab-separated text (pastes into a spreadsheet), in the order made."""
    lines = [_("Medida\tÁtomos\tValor")]
    for m in measurements:
        atoms, _value = row_text(structure, m)
        lines.append(f"{KIND_LABEL[m.kind]}\t{atoms}\t{number_text(m)}")
    return "\n".join(lines) + "\n"
