"""Spec 102: the pools (``pw.x -nk``) the "Criar cálculo" script gets from NP and the k-points.

The cluster's rules (a multiple of 4, at most 16, dividing NP, 4 cores a pool at least) and the count of
k-points the pools share (irreducible, from the structure of each input) are checked apart, then in the plans.
"""

import pytest

from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.types.pools import (
    auto_pools,
    kpoint_count,
    planned_kpoints,
    pool_choices,
)
from qe_studio.core.calc_create.types.script import pool_notes

from calc_helpers import AL_PATH, AL_SCF, JOBS, NI_SCF, SCRIPT_INPUT, al, from_text

MESH = "10 10 10 0 0 0"  # Al fcc: 47 irreducible k-points


def al_mesh(mesh: str):
    return AL_SCF.read_text().replace(MESH, mesh)


def plan(type_id="scf", scf=None, mode="avancado", **values):
    return by_id(type_id).plan(scf or al(), {"kpath": AL_PATH, **values}, JOBS, mode)


def nk_of(result) -> int:
    text = result.files[0].text
    [line] = [line for line in text.splitlines() if line.startswith("NK=")]
    return int(line.removeprefix("NK="))


# -- the cluster's rules -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "np_, choices",
    [
        (32, [4, 8]),
        (64, [4, 8, 16]),
        (128, [4, 8, 16]),
        (48, [4, 8, 12]),
        (16, [4]),
        (10, []),
        (8, []),
    ],
)
def test_the_choices_are_multiples_of_4_up_to_16_with_4_cores_a_pool(np_, choices):
    assert pool_choices(np_) == choices


# The table of spec 102: k-points → nk. A star is more pools than k-points (the plan says so).
TABLE = {
    32: {1: 1, 2: 4, 3: 4, 6: 4, 10: 4, 20: 8, 36: 8, 47: 8, 100: 8},
    64: {1: 1, 2: 4, 3: 4, 6: 4, 10: 4, 20: 8, 36: 8, 47: 16, 100: 16},
    128: {1: 1, 2: 4, 3: 4, 6: 4, 10: 4, 20: 8, 36: 8, 47: 16, 100: 16},
}


@pytest.mark.parametrize("np_, row", TABLE.items())
def test_the_pools_follow_np_and_the_k_points(np_, row):
    assert {nks: auto_pools(np_, nks) for nks in row} == row


def test_an_unknown_count_takes_the_manuals_rule_and_no_fit_takes_one():
    assert [auto_pools(np_, None) for np_ in (32, 64, 128)] == [8, 16, 16]  # N/4, 16 at most
    assert auto_pools(10, 47) == 1 and auto_pools(8, 47) == 1  # no multiple of 4 fits
    assert auto_pools(0, 47) == 1


def test_a_pool_stays_at_least_four_fifths_busy():
    # 20 k-points: 8 pools take 3 rounds (20 / 24 = 83 %), 16 take 2 (20 / 32 = 62 %).
    assert auto_pools(64, 20) == 8
    # 36: 16 pools take 3 rounds (75 %), 8 take 5 (90 %).
    assert auto_pools(64, 36) == 8


# -- the k-points of an input ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mesh, count", [(MESH, 47), ("4 4 4 0 0 0", 8), ("4 4 4 1 1 1", 10), ("2 2 2 0 0 0", 3)]
)
def test_the_irreducible_k_points_of_a_mesh_are_pw_xs(mesh, count):
    assert kpoint_count(al_mesh(mesh)) == count  # QE's "number of k points" for fcc Al


def test_gamma_or_no_card_is_one_k_point():
    gamma = AL_SCF.read_text().replace("K_POINTS automatic\n" + MESH, "K_POINTS gamma")
    assert kpoint_count(gamma) == 1
    bare = AL_SCF.read_text().replace("K_POINTS automatic\n" + MESH, "")
    assert kpoint_count(bare) == 1


def test_a_list_gives_its_count_and_a_band_path_none():
    listed = AL_SCF.read_text().replace(
        "K_POINTS automatic\n" + MESH, "K_POINTS tpiba\n2\n0 0 0 1\n0.5 0 0 1"
    )
    assert kpoint_count(listed) == 2
    path = AL_SCF.read_text().replace(
        "K_POINTS automatic\n" + MESH, "K_POINTS crystal_b\n2\n0 0 0 10\n0.5 0 0 1"
    )
    assert kpoint_count(path) is None


def test_lsda_counts_both_spins():
    text = NI_SCF.read_text()
    assert kpoint_count(text.replace("nspin= 2,", "nspin= 1,")) == 29
    assert kpoint_count(text) == 58  # QE 7.3 divides nkstot, up and down together (kunit = 1)


def test_the_input_with_the_fewest_k_points_decides():
    result = plan("bandas", nbnd=12)
    assert planned_kpoints(result.files) == 47  # the path of the bands input says nothing
    assert nk_of(result) == 16
    sparse = plan("bandas", from_text(al_mesh("2 2 2 0 0 0")), nbnd=12)
    assert planned_kpoints(sparse.files) == 3 and nk_of(sparse) == 4


# -- the plan ----------------------------------------------------------------------------------------
def test_the_script_and_the_plan_carry_the_computed_pools():
    result = plan()
    assert nk_of(result) == 16 and result.auto == {"nk": 16}
    assert result.files[0].name == "scf.qsub"
    assert nk_of(plan(np=32)) == 8
    assert nk_of(plan(np=128)) == 16
    assert nk_of(plan(mode="padrao")) == 16  # the mode hides NP and nk: NP is jobs.cores


def test_jobs_nk_is_ignored():
    jobs = JOBS.model_copy(update={"nk": 2})
    result = by_id("scf").plan(al(), {}, jobs, "avancado")
    assert nk_of(result) == 16


def test_a_typed_nk_is_used_as_it_is():
    result = plan(nk=8)
    assert nk_of(result) == 8 and result.auto == {}
    assert not [note for note in result.notes if "cluster" in note]


def test_gamma_gets_one_pool_and_no_note():
    gamma = from_text(AL_SCF.read_text().replace("K_POINTS automatic\n" + MESH, "K_POINTS gamma"))
    result = plan("scf", gamma)
    assert nk_of(result) == 1 and result.auto == {"nk": 1}
    assert not [note for note in result.notes if "Gamma-only" in note or "pools" in note]


def test_the_script_is_still_the_first_file_and_its_notes_come_first():
    result = plan(np=10, nk=4)  # NP not a multiple of nk: a note of the script
    assert result.files[0].name == "scf.qsub"
    assert result.notes.index(next(n for n in result.notes if "NP = 10" in n)) < result.notes.index(
        next(n for n in result.notes if "jobs.myemail" in n)
    )
    assert SCRIPT_INPUT.search(result.files[0].text)


@pytest.mark.parametrize(
    "np_, nk, fragment",
    [
        (64, 2, "múltiplo de 4 e no máximo 16 (nk = 2)"),
        (128, 32, "múltiplo de 4 e no máximo 16 (nk = 32)"),
    ],
)
def test_a_pool_count_the_cluster_does_not_ask_for_is_noted(np_, nk, fragment):
    assert any(fragment in note for note in pool_notes(np_, nk))
    result = plan(np=np_, nk=nk)
    assert not result.errors and any(fragment in note for note in result.notes)  # never blocks


def test_more_pools_than_k_points_is_noted():
    sparse = from_text(al_mesh("2 2 2 0 0 0"))  # 3 k-points
    notes = [n for n in plan("scf", sparse, nk=8).notes if "ociosos" in n]
    assert len(notes) == 1 and "nk = 8" in notes[0] and "cerca de 3" in notes[0]
    assert "5 pools" in notes[0]
    auto = [
        n for n in plan("scf", sparse).notes if "ociosos" in n
    ]  # the floor of 4 pools leaves one
    assert len(auto) == 1 and "nk = 4" in auto[0]
    assert not [n for n in pool_notes(64, 4, 47) if "ociosos" in n]
    assert pool_notes(64, 4, None) == []


def test_every_type_that_runs_pw_x_gets_pools():
    for type_id in ("scf", "relax", "bandas", "pdos", "charge"):
        result = plan(type_id, nbnd=12)
        assert result.auto == {"nk": 16}, type_id
        assert nk_of(result) == 16, type_id
