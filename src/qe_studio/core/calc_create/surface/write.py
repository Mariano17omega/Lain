"""A new structure written into the SCF's text (spec 40 R2.5).

``put_structure`` swaps the cell (``CELL_PARAMETERS angstrom``, ``ibrav = 0``: ``qe.cell_card``), the
positions (``ATOMIC_POSITIONS crystal``, 10 decimals, the ``if_pos`` flags of the model), ``nat``,
``ntyp`` and ``ATOMIC_SPECIES`` (the SCF's rows of the species the structure uses, in the SCF's
order; the keys indexed by species follow them). Every other line stays as written (``InputEditor``).
Cards that number atoms cannot follow a new structure: ``ATOMIC_FORCES`` / ``ATOMIC_VELOCITIES`` go
(with a note), ``CONSTRAINTS`` and Hubbard ``V`` terms are an error.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ...qe.cell_card import set_cell
from ...qe.input_edit import InputEditor
from ..edits import put_number
from ..species_keys import remap_hubbard, remap_species_keys
from . import SurfaceError
from .model import Flags, Model

__all__ = ["PER_ATOM_CARDS", "put_structure", "structure_problem"]

PER_ATOM_CARDS = ("ATOMIC_FORCES", "ATOMIC_VELOCITIES")
DECIMALS = 10
CONSTRAINTS = (
    "O SCF tem CONSTRAINTS, que numeram os átomos: remova o card para gerar a estrutura nova"
)
HUBBARD_V = (
    "O SCF tem termos Hubbard V, que numeram os átomos: remova-os para gerar a estrutura nova"
)


def _number(value: float) -> str:
    return f"{0.0 if abs(value) < 0.5 * 10**-DECIMALS else float(value):16.{DECIMALS}f}"


def _vector(values: np.ndarray) -> str:
    return "".join(_number(v) for v in values)


def _position(label: str, frac: np.ndarray, flag: Flags | None) -> str:
    row = f"{label:<4}{_vector(frac)}"
    return row if flag is None else f"{row}   {flag[0]} {flag[1]} {flag[2]}"


def structure_problem(editor: InputEditor, model: Model, species: Sequence[str]) -> str | None:
    """Why ``model`` cannot replace the SCF's structure (None: it can)."""
    if editor.card("CONSTRAINTS") is not None:
        return CONSTRAINTS
    hubbard = editor.card("HUBBARD")
    if hubbard is not None and any(line.split()[:1] == ["V"] for line in hubbard.lines):
        return HUBBARD_V
    if any(key.startswith("hubbard_v") for key in editor.keys("system")):
        return HUBBARD_V
    known = {row.split()[0] for row in species if row.split()}
    missing = [label for label in dict.fromkeys(model.labels) if label not in known]
    if missing:
        return f"Espécie sem linha em ATOMIC_SPECIES: {', '.join(missing)}"
    return None


def _species(editor: InputEditor, model: Model, rows: Sequence[str]) -> list[str]:
    used = set(model.labels)
    kept: list[str] = []
    mapping: dict[int, int] = {}
    dropped: set[str] = set()
    for old, row in enumerate(rows, 1):
        label = row.split()[0]
        if label in used:
            kept.append(row)
            mapping[old] = len(kept)
        else:
            dropped.add(label)
    notes: list[str] = []
    if dropped:
        editor.replace_card_rows("ATOMIC_SPECIES", kept)
        notes += remap_species_keys(editor, mapping)
        notes += remap_hubbard(editor, dropped, {}, max(len(model), 1))
        notes.append(
            f"Espécies sem átomo removidas de ATOMIC_SPECIES: {', '.join(sorted(dropped))}"
        )
    put_number(editor, "system", "ntyp", len(kept))
    return notes


def put_structure(editor: InputEditor, model: Model, species: Sequence[str]) -> list[str]:
    """Write ``model`` into ``editor``; ``species`` are the SCF's ``ATOMIC_SPECIES`` rows as written.
    Returns notes; raises ``SurfaceError`` before touching the text."""
    problem = structure_problem(editor, model, species)
    if problem is not None:
        raise SurfaceError(problem)
    notes: list[str] = []
    note = set_cell(editor, "angstrom", [_vector(row) for row in model.cell])
    if note is not None:
        notes.append(note)
    rows = [_position(label, model.frac[i], model.flag(i)) for i, label in enumerate(model.labels)]
    editor.replace_card("ATOMIC_POSITIONS", "crystal", rows)
    put_number(editor, "system", "nat", len(model))
    notes += _species(editor, model, species)
    for card in PER_ATOM_CARDS:
        if editor.remove_card(card):
            notes.append(f"{card} removido: os átomos mudaram")
    return notes
