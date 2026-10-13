"""Shared pieces of the surface tests (specs 40–42): the user's reference SCFs and what the user's
scripts make of them (``surface_golden.json``, captured once from ``Documentation/Exemplo-SLAB`` with
pymatgen 2026.9.24, ase 3.29.0 and spglib 2.8.0; indices 0-based)."""

from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

from qe_studio.core.calc_create.scf_info import ScfInfo, scf_info
from qe_studio.core.calc_create.surface.model import Model, flags_of
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.lattice import crystal_from_editor

from conftest import FIXTURES

KAO = FIXTURES / "kao_surface_inputs"
BULK = KAO / "scf-kaolinite.in"
MOLECULE = KAO / "scf-H3CHg.in"
SLAB_001 = KAO / "scf-kaolinite-slab-001.in"
SLAB_010 = KAO / "scf-kaolinite-slab-010.in"
SUPERCELL_001 = KAO / "scf-kaolinite-slab-001-2x1x1.in"
GOLDEN = Path(__file__).parent / "surface_golden.json"

# The scripts' parameters (generate_surface.py) as the fields of the Slab type.
SCRIPT_FIELDS = {
    "slab_001": {"axis": "c (001)", "fix_rule": "espécies e vizinhos"},
    "slab_010": {"axis": "b (010)", "flip": True, "complete": True, "fix_rule": "camada inferior"},
}


def read(path: Path) -> ScfInfo:
    return scf_info(path.read_text(), path)


@functools.cache
def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def golden(case: str) -> dict:
    return _golden()[case]


def golden_model(case: str) -> Model:
    data = golden(case)
    return Model(np.array(data["cell"]), tuple(data["labels"]), np.array(data["frac"]))


def model_from_plan(text: str) -> Model:
    """The structure of a generated input, ``if_pos`` flags included."""
    crystal = crystal_from_editor(InputEditor.from_text(text))
    return Model(crystal.cell, crystal.labels, crystal.frac, flags_of(text))


def atom_distances(a: Model, b: Model) -> np.ndarray:
    """Per atom (same order), the distance in Å between the two positions, by minimum image in
    ``b``'s cell."""
    delta = (a.cart - b.cart) @ np.linalg.inv(b.cell)
    delta -= np.round(delta)
    return np.linalg.norm(delta @ b.cell, axis=1)


def same_atoms(a: Model, b: Model, tol: float = 1e-5) -> bool:
    return a.labels == b.labels and len(a) == len(b) and bool(np.all(atom_distances(a, b) <= tol))


def fixed_of(model: Model) -> list[int]:
    """The atoms written with ``0 0 0``."""
    return [i for i in range(len(model)) if model.flag(i) == (0, 0, 0)]
