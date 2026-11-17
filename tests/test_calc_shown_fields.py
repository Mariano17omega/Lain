"""The fields of "Criar cálculo" that only a choice or a file makes useful (``FormField.shown_when``):
what each type shows for its values, and that a hidden field never reaches the plan."""

from __future__ import annotations

import pytest

from qe_studio.core.calc_create.types import by_id, shown_fields
from qe_studio.core.calc_create.types.charge import IFLAGS, OUTPUT_FORMATS, choice

from calc_helpers import AL_PATH, JOBS, al
from surface_helpers import BULK, MOLECULE, SUPERCELL_001, read

BOTTOM, SPECIES, FROM_SCF, NONE = "camada inferior", "espécies e vizinhos", "do SCF", "nenhum"
RULE_PARAMS = {"fix_fraction", "fix_species", "fix_neighbors"}
PARAMS_OF_RULE = {
    BOTTOM: {"fix_fraction"},
    SPECIES: {"fix_species", "fix_neighbors"},
    FROM_SCF: set(),
    NONE: set(),
}
SURFACE_TYPES = [
    ("slab", BULK, (BOTTOM, SPECIES, NONE)),
    ("supercell", SUPERCELL_001, (BOTTOM, SPECIES, FROM_SCF, NONE)),
    ("adsorption", SUPERCELL_001, (BOTTOM, SPECIES, FROM_SCF, NONE)),
]


def shown(type_id, scf, mode="avancado", **values) -> set[str]:
    fields = by_id(type_id).fields(scf, JOBS)
    return {f.id for f in shown_fields(fields, mode, values)}


@pytest.mark.parametrize(
    "type_id, path, rule",
    [(type_id, path, rule) for type_id, path, rules in SURFACE_TYPES for rule in rules],
)
def test_a_rule_shows_only_its_parameters(type_id, path, rule):
    assert shown(type_id, read(path), fix_rule=rule) & RULE_PARAMS == PARAMS_OF_RULE[rule]


@pytest.mark.parametrize("type_id, path, _rules", SURFACE_TYPES)
def test_the_standard_mode_shows_no_rule_parameter(type_id, path, _rules):
    assert not shown(type_id, read(path), "padrao", fix_rule=BOTTOM) & RULE_PARAMS


def test_the_adsorption_distance_of_a_slab_waits_for_the_molecule():
    bulk = read(BULK)
    assert "ads_distance" not in shown("slab", bulk)
    assert "ads_distance" in shown("slab", bulk, molecule=read(MOLECULE))


def test_the_edge_metals_wait_for_complete():
    bulk = read(BULK)
    assert "metals" not in shown("slab", bulk, complete=False)
    assert "metals" in shown("slab", bulk, complete=True)


def test_the_bond_tolerance_of_a_supercell_follows_the_species_rule():
    surface = read(SUPERCELL_001)
    assert "bond_scale" in shown("supercell", surface, fix_rule=SPECIES)
    for rule in (BOTTOM, FROM_SCF, NONE):
        assert "bond_scale" not in shown("supercell", surface, fix_rule=rule)


def test_only_a_surface_has_a_vacuum_to_check():
    assert "vacuum_min" in shown("supercell", read(SUPERCELL_001))
    bulk = read(BULK)
    assert "vacuum_min" not in shown("supercell", bulk)
    assert not by_id("supercell").plan(bulk, {}, JOBS, "avancado").errors


@pytest.mark.parametrize(
    "occupations, broadening",
    [
        ("smearing", True),
        ("fixed", True),
        ("tetrahedra", False),
        ("tetrahedra_opt", False),
        ("tetrahedra_lin", False),
    ],
)
def test_the_broadening_of_a_pdos_follows_the_occupations(occupations, broadening):
    ids = shown("pdos", al(), occupations=occupations)
    assert {"degauss", "ngauss"} <= ids if broadening else not {"degauss", "ngauss"} & ids


@pytest.mark.parametrize("type_id", ["charge", "charge_diff"])
@pytest.mark.parametrize("code, used", [(0, False), (1, False), (2, True), (3, True), (4, False)])
def test_the_output_format_follows_the_plot(type_id, code, used):
    assert ("output_format" in shown(type_id, al(), iflag=choice(code, IFLAGS))) is used


@pytest.mark.parametrize(
    "type_id, path, hidden, field_id, showing",
    [
        ("slab", BULK, {"fix_rule": NONE, "fix_fraction": "abc"}, "fix_fraction", {"fix_rule": BOTTOM}),
        ("slab", BULK, {"fix_rule": NONE, "fix_species": "Xx"}, "fix_species", {"fix_rule": SPECIES}),
        ("slab", BULK, {"complete": False, "metals": "Xx"}, "metals", {"complete": True}),
        ("slab", BULK, {"ads_distance": "abc"}, "ads_distance", {"molecule": MOLECULE}),
        ("supercell", SUPERCELL_001, {"fix_rule": NONE, "bond_scale": 0}, "bond_scale", {"fix_rule": SPECIES}),
    ],
)  # fmt: skip
def test_a_hidden_field_takes_its_default(type_id, path, hidden, field_id, showing):
    calc_type, scf = by_id(type_id), read(path)
    clean = {key: value for key, value in hidden.items() if key != field_id}
    expected = calc_type.plan(scf, clean, JOBS, "avancado")
    result = calc_type.plan(scf, hidden, JOBS, "avancado")
    assert field_id not in result.problems
    assert [f.text for f in result.files] == [f.text for f in expected.files]
    molecule = {k: read(v) for k, v in showing.items() if k == "molecule"}
    values = {**hidden, **showing, **molecule}
    assert field_id in calc_type.plan(scf, values, JOBS, "avancado").problems


def test_an_output_format_hidden_by_the_plot_blocks_nothing():
    values = {"iflag": choice(1, IFLAGS), "output_format": choice(6, OUTPUT_FORMATS)}
    result = by_id("charge").plan(al(), {"kpath": AL_PATH, **values}, JOBS, "avancado")
    assert "output_format" not in result.problems
    assert "output_format = 5," in result.by_key("pp_charge").text  # its default: pp.x ignores it
