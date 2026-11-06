"""Spec 81 R1: the structures "Visualizar 3D" shows for a calculation being created (the core)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.scf_info import read_scf
from qe_studio.core.calc_create.structures import (
    default_index,
    plan_structures,
    same_cell,
    same_geometry,
)
from qe_studio.core.calc_create.types import CalcPlan, PlannedFile, by_id
from qe_studio.core.structure3d.options import DisplayOptions, carry_species
from structure3d_helpers import make_structure

from calc_helpers import JOBS, SI_SCF, al, from_text
from surface_helpers import BULK, MOLECULE, SLAB_001, SUPERCELL_001, read

COMPLEX = "Molécula na superfície (relax_kaolinite-slab-001-2x1x1.in)"


def labels(structures) -> list[str]:
    return [each.label for each in structures]


@pytest.mark.parametrize("type_id", ["bandas", "pdos", "relax", "vc-relax", "scf", "charge"])
def test_a_type_without_a_new_structure_gives_the_scf(type_id):
    scf = al()
    found = plan_structures(scf, by_id(type_id).plan(scf, {}, JOBS, "avancado"))
    assert labels(found) == ["SCF base (al.scf.in)"]
    assert found[0].path == scf.path and found[0].structure.source.path == str(scf.path)
    assert default_index(found) == 0


def test_without_a_plan_the_scf_alone():
    """Step 1: no plan yet."""
    found = plan_structures(al())
    assert labels(found) == ["SCF base (al.scf.in)"] and len(found[0].structure) == 1


def test_a_molecule_on_a_surface_gives_the_surface_and_the_complex():
    surface = read(SUPERCELL_001)
    values = {"molecule": read(MOLECULE), "site": (43,), "remove_h": True}
    found = plan_structures(surface, by_id("adsorption").plan(surface, values, JOBS, "avancado"))
    assert labels(found) == ["SCF base (scf-kaolinite-slab-001-2x1x1.in)", COMPLEX]
    base, complex_ = found
    assert len(base.structure) == 68 and len(complex_.structure) == 72
    assert complex_.path is None and complex_.structure.source.path is None
    assert complex_.name == "relax_kaolinite-slab-001-2x1x1.in"
    assert same_cell(base.structure, complex_.structure)
    assert default_index(found) == 1  # the window opens on the complex


def test_without_the_site_the_relax_is_the_surface():
    surface = read(SUPERCELL_001)
    plan = by_id("adsorption").plan(surface, {"molecule": read(MOLECULE)}, JOBS, "avancado")
    assert plan.errors  # the site is missing: the plan says it
    assert labels(plan_structures(surface, plan)) == ["SCF base (scf-kaolinite-slab-001-2x1x1.in)"]


def test_slab_and_supercell_add_the_new_structure():
    bulk, slab = read(BULK), read(SLAB_001)
    found = plan_structures(bulk, by_id("slab").plan(bulk, {}, JOBS, "padrao"))
    assert labels(found) == ["SCF base (scf-kaolinite.in)", "Slab (vc-relax_kaolinite.in)"]
    found = plan_structures(slab, by_id("supercell").plan(slab, {}, JOBS, "padrao"))
    assert [len(each.structure) for each in found] == [34, 68]


def test_a_charge_difference_gives_the_base_clean_and_isolated():
    scf = from_text(SMALL)  # atoms 1-2 Fe, 3-4 O, 5-6 H
    plan = by_id("charge_diff").plan(scf, {"atoms": (5, 6)}, JOBS, "padrao")
    found = plan_structures(scf, plan)
    assert labels(found) == [
        "SCF base (scf.in)",
        "SCF clean (scf_ilita_clean.in)",
        "SCF isolated (scf_ilita_isolated.in)",
    ]
    assert [len(each.structure) for each in found] == [6, 4, 2]
    assert default_index(found) == 2
    assert found[2].structure.labels == ("H", "H")


def test_the_scfs_of_an_adsorption_energy_without_their_copies():
    """Spec 79: the copies have the structure of their SCF and are not repeated."""
    scfs = (al(), read_scf(SI_SCF))
    plan = by_id("ads_energy").plan(scfs[0], {}, JOBS, "avancado", "", scfs)
    found = plan_structures(scfs[0], plan, scfs)
    assert labels(found) == ["al.scf.in", "si.scf.in"]
    assert [each.path for each in found] == [scf.path for scf in scfs]
    assert default_index(found) == 0  # nothing generated: the first SCF of the list
    assert labels(plan_structures(scfs[0], None, scfs)) == ["al.scf.in", "si.scf.in"]


def test_two_scfs_of_the_same_name_are_told_apart_by_their_folder():
    first, second = al(), dataclasses.replace(al(), path=Path("/runs/other/al.scf.in"))
    found = plan_structures(first, None, (first, second))
    assert labels(found) == ["al_bands/al.scf.in", "other/al.scf.in"]


def test_two_scfs_in_folders_of_the_same_name_are_told_apart_further_up():
    """The window picks a structure by its label: two with one label would show the first."""
    one = dataclasses.replace(al(), path=Path("/runs/ilita/0_SCF/scf.in"))
    two = dataclasses.replace(al(), path=Path("/runs/kaolin/0_SCF/scf.in"))
    alone = read_scf(SI_SCF)
    found = plan_structures(one, None, (one, alone, two))
    assert labels(found) == ["ilita/0_SCF/scf.in", "si.scf.in", "kaolin/0_SCF/scf.in"]


def test_a_path_inside_another_path_of_the_same_name_is_told_apart():
    one = dataclasses.replace(al(), path=Path("/a/scf.in"))
    two = dataclasses.replace(al(), path=Path("/x/a/scf.in"))
    assert labels(plan_structures(one, None, (one, two))) == ["/a/scf.in", "x/a/scf.in"]


def test_scfs_with_nothing_to_tell_them_apart_are_numbered():
    one = dataclasses.replace(al(), path=None)
    assert labels(plan_structures(one, None, (one, one))) == ["SCF", "SCF (2)"]


def test_an_input_of_the_plan_never_repeats_the_label_of_an_scf():
    scf = al()
    other = read_scf(SI_SCF)
    copy = PlannedFile("si.scf.in", "pw_input", other.text, "al.scf.in", "x")
    found = plan_structures(scf, CalcPlan((copy,)), (scf,))
    assert labels(found) == ["al.scf.in", "al.scf.in (2)"]


def test_a_text_that_gives_no_structure_is_skipped():
    scf = al()
    broken = PlannedFile("broken.in", "pw_input", "&CONTROL\n/\n", "Quebrado (broken.in)", "x")
    script = PlannedFile("run.qsub", "qsub", "#!/bin/bash\n", "Script", "script")
    plan = CalcPlan((script, broken), errors=("Estrutura ilegível",))
    assert labels(plan_structures(scf, plan)) == ["SCF base (al.scf.in)"]


def test_the_geometry_compares_cell_atoms_and_fractions():
    cell = [[3, 0, 0], [0, 3, 0], [0, 0, 3]]
    a = make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.5]], ["O", "H"])
    assert same_geometry(a, make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.5 + 1e-8]], ["O", "H"]))
    assert not same_geometry(a, make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.6]], ["O", "H"]))
    assert not same_geometry(a, make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.5]], ["O", "O"]))
    assert not same_geometry(a, make_structure(cell, [[0, 0, 0]], ["O"]))
    bigger = make_structure([[4, 0, 0], [0, 3, 0], [0, 0, 3]], [[0, 0, 0], [0.5] * 3], ["O", "H"])
    assert not same_geometry(a, bigger) and not same_cell(a, bigger)


def test_species_colors_and_visibility_follow_their_label():
    """R2.1: the complex adds species; what the user set for O stays on O."""
    cell = [[3, 0, 0], [0, 3, 0], [0, 0, 3]]
    old = make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.5]], ["Si", "O"])
    new = make_structure(cell, [[0, 0, 0], [0.5, 0.5, 0.5], [0.2] * 3], ["Hg", "O", "C"])
    options = DisplayOptions(species_colors={0: (1, 2, 3), 1: (4, 5, 6)}, species_hidden={0, 1})
    carry_species(options, old, new)
    assert options.species_colors == {1: (4, 5, 6)} and options.species_hidden == {1}
