"""Spec 40 R5: the "Slab" type of "Criar cálculo": the plan of the user's scripts, its fields, notes,
errors and ``geracao.md``."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME
from qe_studio.core.calc_create.types import by_id, visible_fields
from qe_studio.core.calc_create.types.slab import GAMMA_NOTE, NO_MESH, NO_MOLECULE_NOTE
from qe_studio.core.calc_create.types.slab_fields import GROUP
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.config import JobsConfig
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint

from calc_helpers import AL_SCF, JOBS, al, from_text
from surface_helpers import (
    BULK,
    MOLECULE,
    SCRIPT_FIELDS,
    SLAB_001,
    fixed_of,
    golden,
    golden_model,
    model_from_plan,
    read,
    same_atoms,
)

SLAB = by_id("slab")
BULK_TEXT = BULK.read_text()
CUT_NOTE = (
    "3 ligações metal–O cortadas na borda (Al 2, Si 1); marque 'Completar poliedros de borda "
    "(O + H)' para fechá-las com OH"
)


def plan(scf: ScfInfo | None = None, mode: str = "avancado", jobs=JOBS, **values):
    return SLAB.plan(scf or read(BULK), values, jobs, mode)  # type: ignore[arg-type]


def input_text(result) -> str:
    return result.by_key("vc-relax").text


def report(result) -> str:
    return result.by_key(REPORT_KEY).text


def script_plan(case: str):
    return plan(molecule=read(MOLECULE), **SCRIPT_FIELDS[case])


@pytest.mark.parametrize("case", ["slab_001", "slab_010"])
def test_the_plan_reproduces_the_scripts(case):
    result = script_plan(case)
    assert result.errors == ()
    assert [f.name for f in result.files] == ["slab.qsub", "vc-relax_kaolinite.in", REPORT_NAME]
    text = input_text(result)
    data = golden(case)
    model = model_from_plan(text)
    assert same_atoms(model, golden_model(case))
    assert np.allclose(model.cell, data["cell"], atol=1e-6, rtol=0)
    assert fixed_of(model) == data["fixed"]
    editor = InputEditor.from_text(text)
    assert editor.card("K_POINTS").lines == (" ".join(map(str, data["kmesh"] + data["koffset"])),)
    assert editor.get("control", "prefix") == data["prefix"]
    assert editor.get("control", "calculation") == data["calculation"] == "vc-relax"
    assert editor.get("cell", "cell_dofree") == "2Dxy"
    assert editor.get("system", "nbnd") is None and data["nbnd"] is None  # as in the SCF
    assert [i for i in lint(text).issues if i.severity == "error"] == []


def test_the_report_of_the_010():
    text = report(script_plan("slab_010"))
    assert text.startswith("# Relatório da geração\n\n- **SCF de origem**: scf-kaolinite.in\n")
    for line in (
        "- **Vácuo pedido**: 15,10 Å = 10,50 + molécula 2,60 + adsorção 2,00",
        "- **Vácuo medido**: 15,10 Å",
        "- **Superfície**: eixo b empilhado (010), invertida",
        "- **Átomos**: 40 (Al 4, Si 4, O 21, H 11)",
        "- **|a|, |b|, |c|**: 5,190; 7,403; 26,425 Å",
        "- **Fator f**: 2,9334 × eixo b do bulk",
        "- **Átomos fixos**: 18/40 (Al 2, Si 2, O 10, H 4), regra 'camada inferior'",
        "- **H reconectados**: H27–O19 (0,974 Å), H32–O24 (0,971 Å)",
        "- **k-points**: 6 4 1 0 0 0 (do SCF 6 4 4 0 0 0; vácuo 1)",
    ):
        assert line in text.splitlines()
    assert "Al2: O35 + H36 (Al–O 2,038 Å)" in text


def test_the_001_with_the_molecule_has_15_10_of_vacuum():
    result = script_plan("slab_001")
    assert "- **Vácuo medido**: 15,10 Å" in report(result)
    assert "- **Átomos fixos**: 14/34 (Si 4, O 10), regra 'espécies e vizinhos'" in report(result)
    assert NO_MOLECULE_NOTE not in result.notes


def test_without_a_molecule_the_vacuum_is_the_minimum():
    result = plan()
    model = model_from_plan(input_text(result))
    assert model.cell[2, 2] - np.ptp(model.cart[:, 2]) == pytest.approx(10.5, abs=1e-6)
    assert NO_MOLECULE_NOTE in result.notes
    assert "- **Vácuo pedido**: 10,50 Å (o vácuo mínimo; sem molécula)" in report(result)


def test_the_folder_is_a_unit():
    jobs = JobsConfig(pseudo_dir="/opt/pseudo")
    editor = InputEditor.from_text(input_text(plan(jobs=jobs)))
    assert editor.get("control", "outdir") == "./tmp/"
    assert editor.get("control", "pseudo_dir") == "/opt/pseudo"


def test_the_standard_mode_shows_the_four_fields():
    fields = SLAB.fields(read(BULK), JOBS)
    shown = [f.id for f in visible_fields(fields, "padrao")]
    assert shown == ["molecule", "axis", "vacuum_min", "complete"]
    assert {f.group for f in fields if f.id in shown} == {GROUP}
    assert plan(mode="padrao", fix_rule="nenhum").by_key("vc-relax") is not None


def test_the_standard_mode_keeps_the_defaults():
    """Fields the mode hides take their defaults: the bottom half is fixed, nothing is turned."""
    result = plan(mode="padrao", fix_rule="nenhum", flip=True)
    assert "regra 'camada inferior'" in report(result) and "não invertida" in report(result)


def test_cut_bonds_left_open_are_noted():
    assert CUT_NOTE in plan(axis="b (010)", flip=True).notes
    assert not any("ligaç" in note.lower() for note in script_plan("slab_010").notes)
    assert not any("ligaç" in note.lower() for note in script_plan("slab_001").notes)
    partly = plan(axis="b (010)", flip=True, complete=True, metals="Al")
    assert (
        "Ligações Si–O cortadas não foram completadas: Si não está em 'Metais da borda'"
        in partly.notes
    )


def test_a_gamma_scf_keeps_gamma():
    scf = from_text(BULK_TEXT.replace("K_POINTS automatic\n6 4 4 0 0 0", "K_POINTS gamma"))
    result = plan(scf)
    assert InputEditor.from_text(input_text(result)).card("K_POINTS").option == "gamma"
    assert GAMMA_NOTE in result.notes and not result.errors


def test_another_card_needs_a_mesh():
    scf = from_text(
        BULK_TEXT.replace("K_POINTS automatic\n6 4 4 0 0 0", "K_POINTS tpiba\n1\n0 0 0 1")
    )
    result = plan(scf)
    assert result.problems["kmesh"] == NO_MESH
    typed = plan(scf, kmesh="3 2 1 0 0 0")
    assert not typed.errors
    assert InputEditor.from_text(input_text(typed)).card("K_POINTS").lines == ("3 2 1 0 0 0",)


def test_constraints_are_an_error_and_the_files_stay():
    scf = from_text(BULK_TEXT + "\nCONSTRAINTS\n1\n'distance' 1 2 2.0\n")
    result = plan(scf)
    assert any("CONSTRAINTS" in error for error in result.errors)
    assert [f.key for f in result.files] == ["script", "vc-relax", REPORT_KEY]
    assert "Estrutura não gerada" in report(result)


def test_errors_go_to_their_fields():
    assert "complete" in plan(al(), complete=True).problems  # no O nor H in the Al SCF
    assert "metals" in plan(complete=True, metals="Al Fe").problems
    assert "vacuum_min" in plan(vacuum_min=0).problems
    assert "fix_species" in plan(fix_rule="espécies e vizinhos", fix_species="Fe").problems
    assert "fix_species" not in plan(fix_species="Fe").problems  # the rule does not read it
    assert "fix_rule" in plan(fix_rule="espécies e vizinhos", fix_species="Al Si O H").problems
    assert "fix_fraction" in plan(fix_fraction=1.5).problems


def test_a_molecule_without_structure_is_a_problem_of_its_field():
    broken = from_text(MOLECULE.read_text().replace("ibrav = 14", "ibrav = 99"), "mol.in")
    result = plan(molecule=broken)
    assert result.problems["molecule"].startswith("SCF da molécula: Estrutura de mol.in ilegível")


def test_a_molecule_that_is_no_molecule_is_noted():
    result = plan(molecule=read(BULK))
    assert any("não parece isolada" in note for note in result.notes)


def test_a_scf_that_already_has_vacuum_is_noted():
    notes = plan(read(SLAB_001)).notes
    assert "O SCF já tem 15,1 Å de vácuo ao longo de c: parece uma superfície" in notes


def test_a_skewed_cell_with_2dxy_is_noted():
    assert any("eixos não ortogonais" in note for note in plan().notes)
    assert not any("eixos não ortogonais" in note for note in plan(cell_dofree="all").notes)


def test_another_axis_names_the_prefix():
    editor = InputEditor.from_text(input_text(plan(axis="a (100)")))
    assert editor.get("control", "prefix") == "kaolinite-slab-100"


def test_the_report_is_written_with_the_rest(tmp_path):
    result = script_plan("slab_010")
    created = create_folder(tmp_path, SLAB, "kao", result)
    assert [p.name for p in created.files] == ["slab.qsub", "vc-relax_kaolinite.in", REPORT_NAME]
    assert "H27–O19 (0,974 Å)" in (created.folder / REPORT_NAME).read_text()


def test_the_al_scf_plans_too():
    result = plan(al())
    assert not result.errors
    assert len(model_from_plan(input_text(result))) == 1
    assert AL_SCF.name in report(result)
