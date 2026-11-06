"""Spec 41 R1: the diagonal supercell of ``surface/supercell.py`` against the user's scripts
(``supercell_001`` / ``supercell_010`` of ``surface_golden.json``) and its limits."""

from __future__ import annotations

import itertools
import re

import numpy as np
import pytest

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.kmesh import rescale_mesh
from qe_studio.core.calc_create.surface.model import model_of
from qe_studio.core.calc_create.surface.supercell import (
    MAX_ATOMS,
    MAX_REPEAT,
    make_supercell,
    repeat_problem,
    size_problem,
)

from surface_helpers import SLAB_001, SLAB_010, golden, golden_model, read, same_atoms

SLABS = {"supercell_001": SLAB_001, "supercell_010": SLAB_010}


@pytest.mark.parametrize("case", list(SLABS))
def test_the_2x1x1_is_the_scripts(case):
    model = make_supercell(model_of(read(SLABS[case])), (2, 1, 1))
    assert same_atoms(model, golden_model(case))
    assert np.allclose(model.cell, golden(case)["cell"], atol=1e-9, rtol=0)


def test_one_copy_is_the_same_model():
    model = model_of(read(SLAB_001))
    same = make_supercell(model, (1, 1, 1))
    assert same_atoms(same, model, tol=0)
    assert np.array_equal(same.frac, model.frac) and np.array_equal(same.cell, model.cell)
    assert same.flags == model.flags


def test_every_copy_keeps_the_flags_of_its_atom():
    model = model_of(read(SLAB_001))
    assert sum(1 for flag in model.flags if flag == (0, 0, 0)) == 14
    double = make_supercell(model, (2, 1, 1))
    assert double.flags == tuple(flag for flag in model.flags for _ in range(2))
    assert sum(1 for flag in double.flags if flag == (0, 0, 0)) == 28


def test_each_atom_is_followed_by_its_copies_with_i_slowest():
    model = model_of(read(SLAB_001))
    n = (1, 2, 3)
    cell = make_supercell(model, n)
    assert len(cell) == 6 * len(model)
    assert np.allclose(cell.cell, model.cell * np.array(n)[:, None])
    shifts = np.array(list(itertools.product(range(1), range(2), range(3))))
    for atom in (0, len(model) - 1):
        copies = cell.frac[6 * atom : 6 * atom + 6] * n - model.frac[atom]
        assert np.allclose(copies, shifts)
        assert cell.labels[6 * atom : 6 * atom + 6] == (model.labels[atom],) * 6
    assert cell.frac.max() < 1  # never wrapped, never past the cell either


@pytest.mark.parametrize(
    "n, text",
    [
        ((MAX_REPEAT + 1, 1, 1), f"Repetições ao longo de a: de 1 a {MAX_REPEAT}"),
        ((1, 0, 1), f"Repetições ao longo de b: de 1 a {MAX_REPEAT}"),
        ((8, 8, 1), f"Supercélula grande demais para o Lain: 2176 átomos (máximo {MAX_ATOMS})"),
    ],
)
def test_the_limits(n, text):
    with pytest.raises(SurfaceError, match=re.escape(text)):
        make_supercell(model_of(read(SLAB_001)), n)


def test_the_problems_alone():
    assert (
        repeat_problem(2, 8) is None
        and repeat_problem(2, 9) == "Repetições ao longo de c: de 1 a 8"
    )
    assert size_problem(250, (8, 1, 1)) is None
    assert size_problem(667, (3, 1, 1)) == (
        "Supercélula grande demais para o Lain: 2001 átomos (máximo 2000)"
    )


def test_a_bulk_mesh_is_divided_on_every_axis():
    mesh = KMesh((6, 4, 4), (1, 0, 1))
    axes = {0: 0, 1: 1, 2: 2}
    assert rescale_mesh(mesh, axes, {0: 2, 1: 2, 2: 1}, vacuum_axis=None) == KMesh(
        (3, 2, 4), (1, 0, 1)
    )
    assert rescale_mesh(mesh, {0: 0, 1: 1}, {0: 2}) == KMesh((3, 4, 1), (1, 0, 0))
