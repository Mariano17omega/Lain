"""Spec 40 R4: the fixed atoms and the k-point mesh of a new cell."""

from __future__ import annotations

import pytest

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.fixing import (
    ALL_FIXED,
    BOTTOM,
    FROM_SCF,
    NONE,
    SPECIES,
    apply_fix,
    fixed_atoms,
)
from qe_studio.core.calc_create.surface.kmesh import rescale_mesh
from qe_studio.core.calc_create.surface.model import model_of
from qe_studio.core.calc_create.surface.slab import SlabOptions, make_slab

from surface_helpers import BULK, SLAB_001, golden, golden_model, read


def test_the_scripts_rules_give_the_scripts_fixed_atoms():
    fixed_001 = fixed_atoms(golden_model("slab_001"), SPECIES, species=("Si",), neighbors=("O",))
    assert list(fixed_001.indices) == golden("slab_001")["fixed"] and len(fixed_001.indices) == 14
    assert fixed_001.notes == ()
    fixed_010 = fixed_atoms(golden_model("slab_010"), BOTTOM, fraction=0.5)
    assert list(fixed_010.indices) == golden("slab_010")["fixed"] and len(fixed_010.indices) == 18


def test_from_the_scf():
    model = model_of(read(SLAB_001))
    result = fixed_atoms(model, FROM_SCF)
    assert len(result.indices) == 14
    assert apply_fix(model, result, FROM_SCF) is model  # the flags as written


def test_apply_fix_writes_0_0_0_on_the_fixed_atoms_only():
    model = golden_model("slab_010")
    fixed = apply_fix(model, fixed_atoms(model, BOTTOM), BOTTOM)
    assert [i for i, flag in enumerate(fixed.flags) if flag == (0, 0, 0)] == golden("slab_010")[
        "fixed"
    ]
    assert {flag for flag in fixed.flags} == {(0, 0, 0), None}


def test_everything_fixed_is_an_error():
    model = golden_model("slab_001")
    with pytest.raises(SurfaceError, match=ALL_FIXED):
        fixed_atoms(model, SPECIES, species=("Al", "Si", "O", "H"))


def test_nothing_fixed_is_a_note_unless_asked():
    model = golden_model("slab_001")
    assert fixed_atoms(model, SPECIES, species=("Fe",)).notes == (
        "Nenhum átomo ficou fixo pela regra 'espécies e vizinhos'",
    )
    assert fixed_atoms(model, NONE).indices == () and fixed_atoms(model, NONE).notes == ()


def test_species_above_the_middle_plane_are_noted():
    model = golden_model("slab_010")  # turned over: the Al layer is on top
    notes = fixed_atoms(model, SPECIES, species=("Al",)).notes
    assert notes and "acima do plano médio" in notes[0]


def test_only_the_slab_counts():
    bulk = model_of(read(BULK))
    model = make_slab(bulk, SlabOptions()).model
    fixed = fixed_atoms(model, BOTTOM, n_slab=20)
    assert max(fixed.indices) < 20


def test_rescale_mesh():
    assert rescale_mesh(KMesh((6, 4, 4)), {0: 0, 1: 2}) == KMesh((6, 4, 1))
    assert rescale_mesh(KMesh((6, 4, 4)), {0: 0, 1: 1}, {0: 2}) == KMesh((3, 4, 1))
    assert rescale_mesh(KMesh((6, 4, 4), (1, 0, 1)), {0: 1, 1: 2}) == KMesh((4, 4, 1), (0, 1, 0))
    assert rescale_mesh(KMesh((1, 1, 1)), {0: 0, 1: 1}, {0: 2, 1: 3}) == KMesh((1, 1, 1))
