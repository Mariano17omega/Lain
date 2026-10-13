"""Spec 42 R2: the surface atoms a molecule can sit on, grouped by symmetry with spglib, against what the
user's script (``qe_slab_candidates.find_candidates``) found on the relaxed 2×1×1 (001)."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.surface.candidates import (
    candidate_note,
    candidates,
    candidates_for,
    no_candidates_text,
    surface_frame,
    top_atoms,
)
from qe_studio.core.calc_create.surface.model import model_of
from qe_studio.core.calc_create.types.adsorption_fields import site_rows

from surface_helpers import SUPERCELL_001, golden, read, with_structure

PARAMS = {"window": 1.5, "symprec": 1e-3, "bond_scale": 1.15}


@pytest.fixture(scope="module")
def model():
    return model_of(read(SUPERCELL_001))


def find(model, species=("O",), **changes):
    params = {**PARAMS, **changes}
    return candidates(model, species, params["window"], params["symprec"], params["bond_scale"])


def test_the_window_holds_the_scripts_atoms(model):
    assert len(top_atoms(model, 1.5)) == golden("candidates_001")["n_top"] == 24


def test_the_groups_are_the_scripts(model):
    """Each group of the script (0-based members) is one letter here, its members 1-based."""
    found = find(model)
    expected = [[m + 1 for m in c["members"]] for c in golden("candidates_001")["candidates"]]
    groups: dict[str, list[int]] = {}
    for candidate in found:
        groups.setdefault(candidate.group, []).append(candidate.index)
    assert list(groups.values()) == expected
    assert list(groups) == ["A", "B", "C"]
    assert {c.multiplicity for c in found} == {4}
    assert {c.label for c in found} == {"O"}


def test_the_neighbours_are_the_scripts(model):
    by_index = {c.index: c for c in find(model)}
    for row in golden("candidates_001")["candidates"]:
        candidate = by_index[row["index"] + 1]
        assert [label for label, _d in candidate.neighbors] == [s for s, _d in row["neighbors"]]
        assert np.allclose([d for _l, d in candidate.neighbors], [d for _s, d in row["neighbors"]])
    assert candidate_note(by_index[41]) == "A (4) · H 0,97 · Al 1,91 · Al 1,92"


def test_a_narrower_window_leaves_no_o(model):
    """At 0,5 Å only the hydroxyl H are on top: no O, the script's own error there."""
    assert golden("candidates_001")["variants"]["window_0.5"]["error"].startswith("no surface O")
    assert find(model, window=0.5) == ()
    assert len(find(model, window=1.0)) == 12
    assert no_candidates_text(("O",), 0.5) == "Nenhum átomo de O a até 0,5 Å do topo"


def test_species_o_h_adds_the_hydrogens(model):
    variant = golden("candidates_001")["variants"]["species_O_H"]
    found = find(model, ("O", "H"))
    assert sorted({c.index for c in found}) == sorted(
        m + 1 for c in variant["candidates"] for m in c["members"]
    )
    assert [c.group for c in found if c.label == "H"][:1] == ["D"]  # letters by the smallest index


def test_an_element_matches_its_labels(model):
    labelled = model.replace(
        labels=tuple("O1" if label == "O" else label for label in model.labels)
    )
    assert [c.index for c in find(labelled)] == [c.index for c in find(model)]


def test_a_slab_across_the_edge_of_c_lists_the_same(model):
    shifted = model.replace(frac=(model.frac + [0.0, 0.0, 0.45]) % 1.0)
    frame = surface_frame(shifted)
    assert np.ptp(frame.frac[:, 2]) < 0.5  # contiguous again
    assert [(c.index, c.group, c.multiplicity) for c in find(shifted)] == [
        (c.index, c.group, c.multiplicity) for c in find(model)
    ]


def test_a_frame_keeps_a_slab_as_written(model):
    assert np.allclose(surface_frame(model).frac, model.frac)
    assert np.allclose(surface_frame(model).normal, [0, 0, 1])


def test_cached_by_text_and_parameters():
    scf = read(SUPERCELL_001)
    first = candidates_for(scf, ("O",), 1.5, 1e-3, 1.15)
    assert candidates_for(scf, ["O"], 1.5, 1e-3, 1.15) is first
    assert candidates_for(scf, ("O",), 1.0, 1e-3, 1.15) is not first


def test_the_table_rows(model):
    rows = site_rows(read(SUPERCELL_001), {})
    assert rows.unit == "crystal" and rows.error == "" and len(rows.rows) == 12
    first = rows.rows[0]
    assert (first.index, first.label, first.note) == (41, "O", "A (4) · H 0,97 · Al 1,91 · Al 1,92")
    assert first.x == f"{model.frac[40, 0]:.5f}"
    assert site_rows(read(SUPERCELL_001), {"height_window": "0.5"}).error == (
        "Nenhum átomo de O a até 0,5 Å do topo"
    )
    assert site_rows(read(SUPERCELL_001), {"height_window": "-1"}).error == (
        "A janela da superfície deve ser maior que zero"
    )
    assert site_rows(read(SUPERCELL_001), {"site_species": ","}).error == (
        "Preencha Espécies candidatas"
    )
    assert len(site_rows(read(SUPERCELL_001), {"site_species": "O H"}).rows) == 24
    assert len(site_rows(read(SUPERCELL_001), {"site_species": " "}).rows) == 12  # empty: "O"


def test_a_rotated_surface_finds_the_same(model):
    """The normal is a1 × a2, not z: a structure turned whole keeps its candidates."""
    angle = np.radians(30)
    turn = np.array(
        [[1, 0, 0], [0, np.cos(angle), -np.sin(angle)], [0, np.sin(angle), np.cos(angle)]]
    )
    turned = model.replace(cell=model.cell @ turn.T)
    assert [(c.index, c.group) for c in find(turned)] == [(c.index, c.group) for c in find(model)]
    scf = with_structure(SUPERCELL_001, turned)
    assert len(site_rows(scf, {}).rows) == 12
