"""The structure a surface type works on (spec 40 R2.1): the SCF's crystal plus its ``if_pos`` flags.

The crystal comes from ``ScfInfo.crystal`` (``qe.lattice``: every ``ibrav``, no ASE); the flags are
words 5–7 of the ``ATOMIC_POSITIONS`` rows as written (``None`` for a row without them).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from ....i18n import _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..scf_info import ScfInfo
from . import SurfaceError

__all__ = ["Flags", "Model", "flags_of", "model_of", "species_rows"]

Flags = tuple[int, int, int]


@dataclass(frozen=True, eq=False)
class Model:
    cell: np.ndarray = field(repr=False)  # (3, 3) in Å, rows a1 a2 a3
    labels: tuple[str, ...]
    frac: np.ndarray = field(repr=False)  # (n, 3) fractional coordinates
    flags: tuple[Flags | None, ...] = ()  # one per atom (empty: none written)

    def __len__(self) -> int:
        return len(self.labels)

    @property
    def cart(self) -> np.ndarray:
        """Cartesian positions in Å."""
        return self.frac @ self.cell

    def flag(self, index: int) -> Flags | None:
        return self.flags[index] if index < len(self.flags) else None

    def replace(self, **changes) -> Model:
        return dataclasses.replace(self, **changes)


def _nat(editor: InputEditor) -> int | None:
    text = editor.get("system", "nat")
    value = fortran_float(text) if text is not None else None
    return int(value) if value is not None and value == int(value) else None


def _flags(words: list[str]) -> Flags | None:
    try:
        values = [int(word) for word in words[4:7]]
    except ValueError:
        return None
    return (values[0], values[1], values[2]) if len(values) == 3 else None


def flags_of(text: str) -> tuple[Flags | None, ...]:
    """The ``if_pos`` of each atom of ``ATOMIC_POSITIONS`` (up to ``nat``), None where none is written."""
    editor = InputEditor.from_text(text)
    card = editor.card("ATOMIC_POSITIONS")
    if card is None:
        return ()
    nat = _nat(editor)
    lines = card.lines if nat is None else card.lines[:nat]
    return tuple(_flags(line.split()) for line in lines)


def model_of(scf: ScfInfo) -> Model:
    """The SCF's structure. Raises ``SurfaceError`` when it cannot be read."""
    crystal = scf.crystal
    if crystal is None:
        raise SurfaceError(
            _("Estrutura de {name} ilegível: {value}").format(
                name=scf.name, value=scf.structure_problem or _("sem estrutura")
            )
        )
    flags = flags_of(scf.text)
    count = len(crystal.labels)
    flags = (flags + (None,) * count)[:count]
    return Model(
        np.array(crystal.cell, float), crystal.labels, np.array(crystal.frac, float), flags
    )


def species_rows(text: str) -> list[str]:
    """The rows of ``ATOMIC_SPECIES`` as written (up to ``ntyp``)."""
    editor = InputEditor.from_text(text)
    rows = editor.card_rows("ATOMIC_SPECIES") or []
    ntyp = editor.get("system", "ntyp")
    value = fortran_float(ntyp) if ntyp is not None else None
    return rows[: int(value)] if value is not None and value == int(value) else rows
