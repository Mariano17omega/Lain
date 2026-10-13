"""Spec 40 R3: the slab of the bulk (``make_slab``, the port of ``make_surface``) against what the user's
scripts make of the same SCFs (``surface_golden.json``)."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.model import Model, model_of
from qe_studio.core.calc_create.surface.molecule import molecule_of
from qe_studio.core.calc_create.surface.slab import (
    NEED_O_H,
    NO_BULK_H,
    SlabOptions,
    make_slab,
)

from surface_helpers import BULK, MOLECULE, golden, golden_model, read, same_atoms

VACUUM_MIN, ADS_DISTANCE = 10.5, 2.0


@pytest.fixture(scope="module")
def bulk() -> Model:
    return model_of(read(BULK))


def script_vacuum() -> float:
    return VACUUM_MIN + molecule_of(read(MOLECULE)).extent + ADS_DISTANCE


SCRIPT_OPTIONS = {
    "slab_001": dict(axis="c", flip=False, complete=False),
    "slab_010": dict(axis="b", flip=True, complete=True),
}


@pytest.mark.parametrize("case", sorted(SCRIPT_OPTIONS))
def test_the_scripts_slabs(bulk, case):
    data = golden(case)
    assert script_vacuum() == pytest.approx(data["vacuum"], abs=1e-9)
    result = make_slab(bulk, SlabOptions(vacuum=script_vacuum(), **SCRIPT_OPTIONS[case]))
    assert np.allclose(result.model.cell, data["cell"], atol=1e-6, rtol=0)
    assert result.f == pytest.approx(data["f"], abs=1e-6)
    assert same_atoms(result.model, golden_model(case))
    assert result.axis_map == {int(k): v for k, v in data["axis_map"].items()}
    assert [[h.h, h.partner] for h in result.healed] == [row[:2] for row in data["healed"]]
    assert [[result.model.labels[a.metal], a.metal, a.partner] for a in result.added] == [
        row[:3] for row in data["added"]
    ]


def test_the_010_numbers(bulk):
    result = make_slab(bulk, SlabOptions(**SCRIPT_OPTIONS["slab_010"], vacuum=script_vacuum()))
    assert len(result.model) == 40 and result.model.labels[34:] == ("O", "H") * 3
    lengths = np.linalg.norm(result.model.cell, axis=1)
    assert np.allclose(lengths, (5.190, 7.403, 26.425), atol=5e-4)
    assert [round(h.distance, 3) for h in result.healed] == [0.974, 0.971]
    assert [round(a.distance, 3) for a in result.added] == [2.038, 1.867, 1.64]


@pytest.mark.parametrize(
    "options",
    [SlabOptions(axis="a"), SlabOptions(axis="c", flip=True), SlabOptions(axis="b")],
    ids=["a", "c-flip", "b"],
)
def test_the_cell_is_right_handed_with_the_plane_flat(bulk, options):
    cell = make_slab(bulk, options).model.cell
    assert np.linalg.det(cell) > 0
    assert cell[0, 1] == pytest.approx(0, abs=1e-12)  # t0 along +x
    assert np.allclose(cell[:2, 2], 0, atol=1e-12)  # the plane is z = 0
    assert cell[2, 2] > 0


def test_without_a_molecule_the_vacuum_is_the_minimum(bulk):
    model = make_slab(bulk, SlabOptions(vacuum=VACUUM_MIN)).model
    heights = model.cart[:, 2]
    assert model.cell[2, 2] - np.ptp(heights) == pytest.approx(VACUUM_MIN)
    assert np.isclose(model.frac[:, 2].mean(), 0.5)


def test_heal_without_h_changes_nothing():
    cell = np.diag([4.0, 4.0, 4.0])
    model = Model(cell, ("Al", "Al"), np.array([[0, 0, 0], [0.5, 0.5, 0.5]]))
    healed = make_slab(model, SlabOptions(heal=True))
    plain = make_slab(model, SlabOptions(heal=False))
    assert healed.healed == () and np.allclose(healed.model.frac, plain.model.frac)


def test_an_h_without_bonded_neighbour_is_noted():
    cell = np.diag([6.0, 6.0, 6.0])
    model = Model(cell, ("Al", "H"), np.array([[0, 0, 0], [0.5, 0.5, 0.5]]))
    assert make_slab(model, SlabOptions()).notes == ("H 2 sem vizinho ligado: não reconectado",)


def oxide(labels: tuple[str, ...]) -> Model:
    """Al and O bonded across the c edge (and an H far from both when asked)."""
    frac = np.array([[0, 0, 0.05], [0, 0, 0.85], [0.5, 0.5, 0.5]])[: len(labels)]
    return Model(np.diag([5.0, 5.0, 2.0]), labels, frac)


def test_complete_needs_o_and_h(bulk):
    with pytest.raises(SurfaceError, match=NEED_O_H):
        make_slab(oxide(("Al", "O")), SlabOptions(complete=True, metals=("Al",)))
    with pytest.raises(SurfaceError, match=NO_BULK_H):
        make_slab(oxide(("Al", "O")), SlabOptions(complete=True), species=("Al", "O", "H"))
    result = make_slab(oxide(("Al", "O", "H")), SlabOptions(complete=True, metals=("Al",)))
    assert result.cut_bonds == {"Al": 1} and len(result.added) == 1


@pytest.mark.parametrize("complete", [False, True])
def test_cut_bonds(bulk, complete):
    def cut(axis: str, flip: bool) -> dict[str, int]:
        options = SlabOptions(axis=axis, flip=flip, complete=complete)
        return make_slab(bulk, options).cut_bonds

    assert cut("c", False) == {}
    assert cut("b", True) == {"Al": 2, "Si": 1}


def test_only_the_metals_listed_are_completed(bulk):
    result = make_slab(bulk, SlabOptions(axis="b", flip=True, complete=True, metals=("Al",)))
    assert result.cut_bonds == {"Al": 2, "Si": 1}
    assert [result.model.labels[a.metal] for a in result.added] == ["Al", "Al"]
    assert len(result.model) == 38


def test_an_unknown_axis_and_no_vacuum_are_errors(bulk):
    with pytest.raises(SurfaceError, match="desconhecido"):
        make_slab(bulk, SlabOptions(axis="d"))
    with pytest.raises(SurfaceError, match="maior que zero"):
        make_slab(bulk, SlabOptions(vacuum=0))
