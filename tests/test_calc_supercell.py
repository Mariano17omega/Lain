"""Spec 41 R2: the "Supercélula" type of "Criar cálculo": the plan of the user's scripts (stage 2), a bulk's
supercell, its fields, defaults, limits, notes and ``geracao.md``."""

from __future__ import annotations

import re

import numpy as np
import pytest

from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME
from qe_studio.core.calc_create.types import by_id, visible_fields
from qe_studio.core.calc_create.types.slab import NO_MESH
from qe_studio.core.calc_create.types.supercell import GAMMA_NOTE, GROUP, STACKED_NOTE
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint

from calc_helpers import JOBS, from_text
from surface_helpers import (
    BULK,
    SLAB_001,
    SLAB_010,
    fixed_of,
    golden,
    golden_model,
    model_from_plan,
    read,
    same_atoms,
)

SUPERCELL = by_id("supercell")
SLABS = {"supercell_001": SLAB_001, "supercell_010": SLAB_010}
SCRIPT_RULES = {"supercell_001": "espécies e vizinhos", "supercell_010": "camada inferior"}
SLAB_TEXT = SLAB_001.read_text()
BULK_NOTE = "SCF sem vácuo: supercélula de bulk, cell_dofree = 'all'"
_FLAGS = re.compile(r"^([A-Z][a-z]?\s+\S+\s+\S+\s+\S+)\s+0\s+0\s+0[ \t]*$", re.MULTILINE)


def plan(scf: ScfInfo | None = None, mode: str = "avancado", **values):
    return SUPERCELL.plan(scf or read(SLAB_001), values, JOBS, mode)  # type: ignore[arg-type]


def input_text(result) -> str:
    return result.by_key("vc-relax").text


def editor_of(result) -> InputEditor:
    return InputEditor.from_text(input_text(result))


def report(result) -> str:
    return result.by_key(REPORT_KEY).text


def defaults(scf: ScfInfo) -> dict:
    return {f.id: f.default for f in SUPERCELL.fields(scf, JOBS)}


def many_atoms(count: int) -> ScfInfo:
    """An Al SCF of ``count`` atoms on a 10 × 10 × 10 grid of a 40 bohr cubic cell (no vacuum)."""
    rows = [
        f"Al {i % 10 / 10:.2f} {i // 10 % 10 / 10:.2f} {i // 100 / 10:.2f}" for i in range(count)
    ]
    text = "\n".join(
        [
            "&CONTROL\n  calculation = 'scf'\n  prefix = 'big'\n/",
            f"&SYSTEM\n  ibrav = 1, celldm(1) = 40.0, nat = {count}, ntyp = 1, ecutwfc = 30\n/",
            "&ELECTRONS\n/",
            "ATOMIC_SPECIES\nAl 26.98 Al.pbe-n-kjpaw_psl.1.0.0.UPF",
            "ATOMIC_POSITIONS crystal",
            *rows,
            "K_POINTS automatic\n2 2 2 0 0 0\n",
        ]
    )
    return from_text(text, "big.in")


@pytest.mark.parametrize("case", list(SLABS))
@pytest.mark.parametrize("rule", ["", "script"])
def test_the_plan_reproduces_the_scripts(case, rule):
    """The fixed atoms are the script's both from the SCF's flags (the default) and by its rule."""
    values = {"fix_rule": SCRIPT_RULES[case]} if rule else {}
    result = plan(read(SLABS[case]), **values)
    assert result.errors == ()
    stem = SLABS[case].stem.removeprefix("scf-")
    assert [f.name for f in result.files] == ["supercell.qsub", f"vc-relax_{stem}.in", REPORT_NAME]
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
    assert editor.get("system", "nat") == str(len(data["labels"]))
    assert editor.get("system", "nbnd") is None and data["nbnd"] is None  # as in the SCF
    assert [i for i in lint(text).issues if i.severity == "error"] == []


def test_the_report_of_the_001():
    text = report(plan())
    assert text.startswith(
        "# Relatório da geração\n\n- **SCF de origem**: scf-kaolinite-slab-001.in\n"
    )
    for line in (
        "- **Repetições**: 2 × 1 × 1",
        "- **Átomos**: 68 (Al 8, Si 8, O 36, H 16)",
        "- **|a|, |b|, |c|**: 10.379; 9.008; 21.126 Å",
        "- **Vácuo medido**: 15.07 Å ao longo de c",
        "- **Átomos fixos**: 28/68 (Si 8, O 20), regra 'do SCF'",
        "- **nbnd**: não definido no SCF (o padrão do pw.x)",
        "- **k-points**: 3 4 1 0 0 0 (do SCF 6 4 1 0 0 0, ÷ repetições; vácuo 1)",
    ):
        assert line in text.splitlines()


def test_the_report_of_the_010():
    text = report(plan(read(SLAB_010), fix_rule="camada inferior"))
    assert "- **Vácuo medido**: 15.25 Å ao longo de c" in text
    assert "- **|a|, |b|, |c|**: 10.379; 7.403; 26.425 Å" in text
    assert "- **Átomos fixos**: 36/80 (Al 4, Si 4, O 20, H 8), regra 'camada inferior'" in text


def test_a_bulk_supercell():
    result = plan(read(BULK), n1=2, n2=2, n3=1)
    assert not result.errors
    editor = editor_of(result)
    assert editor.get("cell", "cell_dofree") == "all"
    assert editor.card("K_POINTS").lines == ("3 2 4 0 0 0",)
    assert editor.get("control", "prefix") == "kaolinite-2x2x1"
    assert editor.get("system", "nat") == "136"
    assert BULK_NOTE in result.notes
    assert fixed_of(model_from_plan(input_text(result))) == []
    assert "- **Vácuo medido**: sem vácuo (bulk)" in report(result)
    assert "- **Átomos fixos**: 0/136, regra 'nenhum'" in report(result)
    assert not any("eixos não ortogonais" in note for note in result.notes)  # 'all'


def test_the_defaults_follow_the_scf():
    assert {k: defaults(read(SLAB_001))[k] for k in ("n1", "n2", "n3")} == {
        "n1": 2,
        "n2": 1,
        "n3": 1,
    }
    surface = defaults(read(SLAB_001))
    assert (surface["cell_dofree"], surface["fix_rule"]) == ("2Dxy", "do SCF")
    bulk = defaults(read(BULK))
    assert (bulk["cell_dofree"], bulk["fix_rule"]) == ("all", "nenhum")
    no_flags = from_text(_FLAGS.sub(r"\1", SLAB_TEXT), "slab.in")
    assert defaults(no_flags)["fix_rule"] == "camada inferior"
    assert defaults(no_flags)["kmesh"] is None


def test_nbnd_follows_the_copies():
    scf = from_text(
        SLAB_TEXT.replace("   ntyp             = 4\n", "   ntyp             = 4\n   nbnd = 90\n")
    )
    result = plan(scf)
    assert editor_of(result).get("system", "nbnd") == "180"
    assert "- **nbnd**: 90 → 180" in report(result)
    assert editor_of(plan(scf, n1=2, n2=3)).get("system", "nbnd") == "540"


def test_nine_copies_are_a_problem_of_the_field():
    result = plan(n2=9)
    assert result.problems["n2"] == "Repetições ao longo de b: de 1 a 8"
    assert "n1" not in result.problems
    assert [f.key for f in result.files] == ["script", "vc-relax", REPORT_KEY]
    assert plan(n1=0).problems["n1"] == "Repetições ao longo de a: de 1 a 8"


def test_too_many_atoms_are_a_problem_of_the_fields_that_grew():
    result = plan(many_atoms(667), n1=3, n2=1, n3=1)
    text = "Supercélula grande demais para o Lain: 2001 átomos (máximo 2000)"
    assert result.problems == {"n1": text}
    assert [f.key for f in result.files] == ["script", "vc-relax", REPORT_KEY]
    both = plan(many_atoms(667), n1=2, n2=2, n3=1).problems
    assert both["n1"] == both["n2"] and "n3" not in both
    largest = plan(many_atoms(250), n1=8, n2=1, n3=1)
    assert not largest.errors
    assert editor_of(largest).get("system", "nat") == "2000"


def test_the_standard_mode_shows_the_repetitions():
    fields = SUPERCELL.fields(read(SLAB_001), JOBS)
    shown = [f.id for f in visible_fields(fields, "padrao")]
    assert shown == ["n1", "n2", "n3"]
    assert {f.group for f in fields if f.id in shown} == {GROUP}
    standard = plan(mode="padrao", fix_rule="nenhum", vacuum_min=99)  # hidden: their defaults
    assert "regra 'do SCF'" in report(standard)
    assert not any("abaixo do mínimo" in note for note in standard.notes)


def test_vacuum_below_the_minimum_is_a_note():
    result = plan(vacuum_min=16)
    assert "Vácuo de 15.1 Å ao longo de c, abaixo do mínimo de 16.0 Å" in result.notes
    assert not result.errors
    assert not any("abaixo do mínimo" in note for note in plan().notes)
    assert "vacuum_min" in plan(vacuum_min=-1).problems


def test_copies_along_the_vacuum_are_noted():
    result = plan(n1=1, n3=2)
    assert STACKED_NOTE in result.notes
    mesh = editor_of(result).card("K_POINTS").lines[0].split()
    assert mesh == ["6", "4", "1", "0", "0", "0"]  # the SCF's: the vacuum axis stays 1
    assert STACKED_NOTE not in plan().notes
    assert STACKED_NOTE not in plan(read(BULK), n3=2).notes  # a bulk has no vacuum


def test_a_gamma_scf_keeps_gamma():
    scf = from_text(re.sub(r"K_POINTS automatic\n.*\n", "K_POINTS gamma\n", SLAB_TEXT))
    result = plan(scf)
    assert editor_of(result).card("K_POINTS").option == "gamma"
    assert GAMMA_NOTE in result.notes and not result.errors


def test_another_card_needs_a_mesh():
    scf = from_text(re.sub(r"K_POINTS automatic\n.*\n", "K_POINTS tpiba\n1\n0 0 0 1\n", SLAB_TEXT))
    assert plan(scf).problems["kmesh"] == NO_MESH
    typed = plan(scf, kmesh="2 2 1 0 0 0")
    assert not typed.errors
    assert editor_of(typed).card("K_POINTS").lines == ("2 2 1 0 0 0",)
    assert "- **k-points**: 2 2 1 0 0 0 (digitada)" in report(typed)


def test_constraints_are_an_error_and_the_files_stay():
    result = plan(from_text(SLAB_TEXT + "\nCONSTRAINTS\n1\n'distance' 1 2 2.0\n"))
    assert any("CONSTRAINTS" in error for error in result.errors)
    assert [f.key for f in result.files] == ["script", "vc-relax", REPORT_KEY]
    assert "Estrutura não gerada" in report(result)


def test_errors_go_to_their_fields():
    assert "fix_species" in plan(fix_rule="espécies e vizinhos", fix_species="Fe").problems
    assert "fix_fraction" in plan(fix_rule="camada inferior", fix_fraction=0).problems
    assert "bond_scale" in plan(bond_scale=0).problems
    assert "fix_rule" in plan(fix_rule="espécies e vizinhos", fix_species="Al Si O H").problems


def test_the_report_is_written_with_the_rest(tmp_path):
    created = create_folder(tmp_path, SUPERCELL, "kao", plan())
    assert created.folder.name == "Supercell_kao"
    names = [p.name for p in created.files]
    assert names == ["supercell.qsub", "vc-relax_kaolinite-slab-001.in", REPORT_NAME]
    assert "regra 'do SCF'" in (created.folder / REPORT_NAME).read_text()
    assert "vc-relax_kaolinite-slab-001.in" in (created.folder / "supercell.qsub").read_text()
