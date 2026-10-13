"""Spec 42 R3: a molecule on one surface atom or between two, against what the user's scripts
(``qe_slab_adsorb.generate_adsorbed`` / ``generate_adsorbed_bidentate``) made of the relaxed 2×1×1 (001)
and the H3CHg molecule, with the anchor's H removed."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.surface.adsorb import (
    REMOVE_H_LABEL,
    SiteError,
    SiteRequest,
    adsorb,
    parse_coords,
    site_atoms,
)
from qe_studio.core.calc_create.surface.model import Model, model_of
from qe_studio.core.calc_create.surface.molecule import molecule_of

from surface_helpers import (
    ADSORBED,
    MOLECULE,
    SUPERCELL_001,
    golden,
    golden_model,
    read,
    same_atoms,
)


@pytest.fixture(scope="module")
def surface():
    return model_of(read(SUPERCELL_001))


@pytest.fixture(scope="module")
def molecule():
    return molecule_of(read(MOLECULE))


def put(surface, molecule, sites, **options):
    options.setdefault("remove_h", True)
    return adsorb(surface, SiteRequest(len(sites) == 2, tuple(sites)), molecule, **options)


@pytest.mark.parametrize("case", list(ADSORBED))
def test_the_scripts_structure(surface, molecule, case):
    data, sites = golden(case), ADSORBED[case]
    result = put(surface, molecule, sites)
    assert same_atoms(result.model, golden_model(case), 1e-5)
    assert len(result.model) == data["n_atoms"] == (72 if len(sites) == 1 else 71)
    assert result.n_slab == len(result.model) - 5
    assert result.removed == tuple(h + 1 for h in data["removed_h"])
    assert result.sites == sites
    assert result.lift == pytest.approx(data["lift"], abs=1e-3)
    assert result.vacuum == pytest.approx(data["vacuum"], abs=1e-2)
    assert result.model.labels[result.n_slab :] == ("Hg", "C", "H", "H", "H")
    assert result.anchor == result.n_slab  # Hg, the heaviest, first in its SCF
    assert all(d == pytest.approx(2.0, abs=0.04) for d in result.site_distances)
    assert result.notes == ()


def test_the_lifts_of_the_bidentate_pairs(surface, molecule):
    lifts = [put(surface, molecule, ADSORBED[c]).lift for c in ADSORBED if c.startswith("ads_bi")]
    assert [round(lift, 2) for lift in lifts] == [1.08, 1.11, 1.41, 1.44]


def test_without_removing_the_h_the_atoms_stay(surface, molecule):
    result = put(surface, molecule, (43,), remove_h=False)
    assert len(result.model) == 73 and result.removed == ()
    assert result.lift > 0  # the hydroxyl H stands above the O: the anchor rises over it


def offset(surface: Model, number: int, shift_angstrom: float) -> str:
    """The coordinates of atom ``number`` moved ``shift_angstrom`` along x, as typed."""
    cart = surface.frac[number - 1] @ surface.cell + [shift_angstrom, 0.0, 0.0]
    return " ".join(f"{v:.6f}" for v in cart @ np.linalg.inv(surface.cell))


def test_coordinates_choose_the_atom_of_the_list(surface, molecule):
    listed = put(surface, molecule, (43, 46))
    typed = adsorb(
        surface,
        SiteRequest(True, coords=(offset(surface, 43, 0.3), offset(surface, 46, -0.3))),
        molecule,
        remove_h=True,
    )
    assert same_atoms(typed.model, listed.model, 1e-9) and typed.sites == (43, 46)


def test_coordinates_too_far_are_refused(surface):
    text = offset(surface, 43, 0.8)
    with pytest.raises(SiteError) as caught:
        site_atoms(surface, SiteRequest(coords=(text,)))
    assert caught.value.role == "first"
    shown = " ".join(f"{float(v):g}".replace(".", ",") for v in text.split())
    assert str(caught.value) == (
        f"As coordenadas {shown} estão a 0,8 Å do átomo mais próximo (O 43): nenhum átomo a até "
        "0,5 Å"
    )


def test_coordinates_typed_with_commas_or_semicolons():
    assert np.allclose(parse_coords("0,25 0,5 0,75"), [0.25, 0.5, 0.75])
    assert np.allclose(parse_coords("0.25; 0.5; 0.75"), [0.25, 0.5, 0.75])
    assert parse_coords("0.25 0.5") is None and parse_coords("a b c") is None
    assert parse_coords("nan 0 0") is None


@pytest.mark.parametrize(
    "request_, role, text",
    [
        (
            SiteRequest(marked=(41, 42, 43)),
            "selection",
            "Monodentado: marque um átomo da lista (marcados: 3)",
        ),
        (
            SiteRequest(True, (43,)),
            "selection",
            "Bidentado: marque dois átomos da lista (marcados: 1)",
        ),
        (SiteRequest(marked=(9,)), "selection", "O átomo 9 (Si) não está na superfície"),
        (SiteRequest(marked=(57,)), "selection", "O átomo 57 (H) não é de O"),
        (SiteRequest(marked=(99,)), "selection", "O átomo 99 não existe (1 a 68)"),
        (
            SiteRequest(coords=("1 2",)),
            "first",
            "Coordenadas do átomo 1: escreva três números, x y z",
        ),
    ],
)
def test_the_site_problems(surface, request_, role, text):
    with pytest.raises(SiteError) as caught:
        site_atoms(surface, request_)
    assert (caught.value.role, str(caught.value)) == (role, text)


def test_the_same_atom_twice_by_coordinates(surface):
    here = offset(surface, 43, 0.0)
    with pytest.raises(SiteError, match=r"os dois átomos são o mesmo \(O 43\)") as caught:
        site_atoms(surface, SiteRequest(True, coords=(here, here)))
    assert caught.value.role == "second"


def test_removing_the_h_of_an_o_without_one(surface, molecule):
    """The O 43 of a surface already without its H 59: 0 H to remove."""
    keep = [i for i in range(len(surface)) if i != 58]
    bare = Model(surface.cell, tuple(surface.labels[i] for i in keep), surface.frac[keep])
    with pytest.raises(SiteError) as caught:
        put(bare, molecule, (43,))
    assert caught.value.role == "deprotonation"
    assert str(caught.value) == f"O 43 tem 0 H ligados: desmarque '{REMOVE_H_LABEL}'"


def test_a_short_distance_is_a_contact(surface, molecule):
    with pytest.raises(SiteError) as caught:
        put(surface, molecule, (43,), distance=1.2)
    assert caught.value.role == "distance"
    assert str(caught.value) == "O âncora fica a 1,2 Å de O 43: aumente a distância de adsorção"


def test_low_clearance_and_vacuum_are_notes(surface, molecule):
    result = put(surface, molecule, (43, 46), h_clearance=2.5, vacuum_min=13.0)
    assert result.notes == (
        "Folga abaixo de 2,5 Å: âncora···H 2,17 Å; o relax ajusta",
        "Vácuo de 12,4 Å acima da molécula, abaixo do mínimo de 13,0 Å",
    )


def test_a_rotated_surface_takes_the_molecule_along_its_normal(surface, molecule):
    """Turned whole about x, the surface's normal is no longer z: the molecule turns with it, and the
    fractions are the scripts' (on the unturned one)."""
    angle = np.radians(25)
    turn = np.array(
        [[1, 0, 0], [0, np.cos(angle), -np.sin(angle)], [0, np.sin(angle), np.cos(angle)]]
    )
    turned = surface.replace(cell=surface.cell @ turn.T)
    result = put(turned, molecule, (43, 46))
    expected = golden_model("ads_bi_O42-O45")
    assert same_atoms(result.model, expected.replace(cell=expected.cell @ turn.T), 1e-5)
