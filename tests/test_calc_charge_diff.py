"""Spec 30: the "Diferença de carga" type: three SCFs (base, clean, isolated), four pp.x inputs and the script."""

import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.render import template_names
from qe_studio.core.calc_create.types import by_id, visible_fields
from qe_studio.core.calc_create.types.charge_diff import ATOMS_TAB, DIFF_TEMPLATE
from qe_studio.core.calc_create.writer import folder_name
from qe_studio.core.config import JobsConfig
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint

from calc_helpers import JOBS, from_text, runs

CHARGE_DIFF = by_id("charge_diff")
ILITA = from_text(SMALL)  # prefix 'ilita'; atoms 1-2 Fe, 3-4 O, 5-6 H
NAMES = [
    "charge_diff.qsub",
    "scf_ilita.in",
    "scf_ilita_clean.in",
    "scf_ilita_isolated.in",
    "pp_ilita_charge.in",
    "pp_ilita_clean_charge.in",
    "pp_ilita_isolated_charge.in",
    "pp_charge_diff.in",
]
# The input of the idea (specs/Ideias.md), for the prefix ilita and the defaults of the template.
IDEA = """&INPUTPP
prefix = 'ilita',
outdir = './tmp/',
filplot = 'ilita_charge_diff',
plot_num = 0
/
&PLOT
nfile = 3,
filepp(1) = 'ilita.charge',
filepp(2) = 'ilita_clean.charge',
filepp(3) = 'ilita_isolated.charge',
weight(1) = 1.0,
weight(2) = -1.0,
weight(3) = -1.0,
iflag = 3,
output_format = 5,
fileout = 'cdd_xsf/ilita_charge_diff.xsf'
/
"""


def plan(scf=ILITA, mode="padrao", atoms=(5, 6), jobs=JOBS, name="", **values):
    return CHARGE_DIFF.plan(scf, {"atoms": atoms, **values}, jobs, mode, name)


def text_of(result, key):
    planned = result.by_key(key)
    assert planned is not None, key
    return planned.text


def editor_of(result, key):
    return InputEditor.from_text(text_of(result, key))


def script_lines(result) -> list[str]:
    return [line for line in result.files[0].text.splitlines() if line.strip()]


# -- R1: the type and its files -----------------------------------------------------------------
def test_the_type_is_registered_after_charge():
    assert (CHARGE_DIFF.id, CHARGE_DIFF.label) == ("charge_diff", "Diferença de carga")
    assert (CHARGE_DIFF.folder_prefix, CHARGE_DIFF.script_name) == (
        "Diff_Charge",
        "charge_diff.qsub",
    )
    assert folder_name(CHARGE_DIFF, "ilita") == "Diff_Charge_ilita"
    assert CHARGE_DIFF.uses_name is False  # the names follow the SCF's prefix, not the folder's
    assert DIFF_TEMPLATE in template_names()
    assert CHARGE_DIFF.script_template in template_names()


def test_the_eight_files_in_tab_order():
    result = plan()
    assert result.errors == ()
    assert [f.name for f in result.files] == NAMES
    assert [f.key for f in result.files] == [
        "script",
        "scf",
        "scf_clean",
        "scf_isolated",
        "pp_base",
        "pp_clean",
        "pp_isolated",
        "pp_diff",
    ]
    assert [f.kind for f in result.files] == ["qsub", *["pw_input"] * 3, *["qe_input"] * 4]
    assert result.files[3].tab_label == "SCF isolated (scf_ilita_isolated.in)"


def test_each_scf_has_its_own_prefix():
    result = plan()
    assert [
        editor_of(result, key).get("control", "prefix")
        for key in ("scf", "scf_clean", "scf_isolated")
    ] == [
        "ilita",
        "ilita_clean",
        "ilita_isolated",
    ]
    for key, prefix in (
        ("pp_base", "ilita"),
        ("pp_clean", "ilita_clean"),
        ("pp_isolated", "ilita_isolated"),
    ):
        text = text_of(result, key)
        assert f"prefix = '{prefix}'," in text
        assert f"filplot = '{prefix}.charge'," in text
        assert f"filepp(1) = '{prefix}.charge'," in text
        assert f"fileout = 'cdd_xsf/{prefix}_charge.xsf'" in text
    assert "outdir = './tmp/'," in text_of(result, "pp_clean")


def test_a_scf_without_a_prefix_is_named_pwscf():
    result = plan(from_text(SMALL.replace("  prefix = 'ilita'\n", "")))
    assert [f.name for f in result.files][1:4] == [
        "scf_pwscf.in",
        "scf_pwscf_clean.in",
        "scf_pwscf_isolated.in",
    ]
    assert editor_of(result, "scf_clean").get("control", "prefix") == "pwscf_clean"
    assert "weight(3) = -1.0" in text_of(result, "pp_diff")


def test_pp_charge_diff_is_the_template_of_the_idea():
    assert text_of(plan(), "pp_diff") == IDEA
    assert lint(IDEA).issues == []
    other = plan(from_text(SMALL.replace("'ilita'", "'Mehg'")))
    assert text_of(other, "pp_diff") == IDEA.replace("ilita", "Mehg")


def test_every_input_lints_clean():
    result = plan()
    for planned in result.files[1:]:
        assert [i for i in lint(planned.text).issues if i.severity == "error"] == [], planned.name


# -- R1.3: what the three SCFs share --------------------------------------------------------------
def test_the_three_scfs_share_cell_cutoffs_and_mesh():
    result = plan()
    editors = [editor_of(result, key) for key in ("scf", "scf_clean", "scf_isolated")]
    for editor in editors:
        assert [editor.get("system", key) for key in ("ibrav", "ecutwfc", "ecutrho", "nspin")] == [
            "0",
            "40",
            "320",
            "2",
        ]
        for card in (
            "CELL_PARAMETERS",
            "K_POINTS",
        ):  # where the card stands may differ, not its text
            mine, first = editor.card(card), editors[0].card(card)
            assert mine is not None and first is not None
            assert (mine.option, mine.lines) == (first.option, first.lines)
        assert editor.get("control", "outdir") == "./tmp/"  # the folder's own, in the three
    fields = {f.id for f in CHARGE_DIFF.fields(ILITA, JOBS)}
    assert not fields & {"kmesh", "ecutwfc", "ecutrho", "ibrav", "celldm"}  # nothing to edit there


def test_the_base_copy_is_the_scf_of_the_unit():
    result = plan(jobs=JobsConfig(pseudo_dir="/Cluster/Pseudo"))
    base = editor_of(result, "scf")
    assert base.get("control", "pseudo_dir") == "/Cluster/Pseudo"
    assert editor_of(result, "scf_clean").get("control", "pseudo_dir") == "/Cluster/Pseudo"
    assert editor_of(result, "scf_isolated").get("control", "pseudo_dir") == "/Cluster/Pseudo"
    assert base.get("system", "nat") == "6" and base.get("system", "nbnd") == "40"  # whole system


# -- the selection --------------------------------------------------------------------------------
def test_the_selection_decides_the_fragments():
    hydrogens, iron = plan(atoms=(5, 6)), plan(atoms=(1, 2))
    assert editor_of(hydrogens, "scf_isolated").get("system", "nat") == "2"
    assert editor_of(hydrogens, "scf_clean").get("system", "nat") == "4"
    assert editor_of(iron, "scf_isolated").get("system", "nat") == "2"
    assert text_of(hydrogens, "scf_isolated") != text_of(iron, "scf_isolated")
    assert editor_of(iron, "scf_isolated").card_rows("ATOMIC_POSITIONS")[0].startswith("Fe 0 0 0")  # type: ignore[index]
    # the order and repeats of the choice do not matter
    assert text_of(plan(atoms=[6, 5, 5]), "scf_isolated") == text_of(hydrogens, "scf_isolated")


@pytest.mark.parametrize(
    "atoms, message",
    [
        ((), "Selecione os átomos do fragmento isolado"),
        ((1, 2, 3, 4, 5, 6), "Deixe ao menos um átomo fora da seleção: o SCF clean ficaria vazio"),
    ],
)
def test_an_empty_or_total_selection_blocks_creating(atoms, message):
    result = plan(atoms=atoms)
    assert result.errors == (message,) and not result.ok
    assert result.problems == {"atoms": message}  # the table is the one marked
    assert [f.name for f in result.files] == NAMES  # the tabs do not come and go
    base = editor_of(result, "scf")
    for key in ("scf_clean", "scf_isolated"):  # nothing was split: the base, with its own prefix
        assert editor_of(result, key).card("ATOMIC_POSITIONS") == base.card("ATOMIC_POSITIONS")


def test_without_the_field_the_selection_is_empty():
    result = CHARGE_DIFF.plan(ILITA, {}, JOBS)  # the window's first plan, before any form exists
    assert "Selecione os átomos do fragmento isolado" in result.errors
    assert [f.name for f in result.files] == NAMES


def test_a_structure_the_split_cannot_read_blocks_creating():
    result = plan(from_text(SMALL.replace("angstrom\nFe 0", "crystal_sg\nFe 0")))
    assert result.errors == ("Posições em crystal_sg não são suportadas",)
    assert [f.name for f in result.files] == NAMES


def test_constraints_block_creating():
    result = plan(from_text(SMALL + "CONSTRAINTS\n6 0.1\n'distance' 1 2\n"))
    assert any("CONSTRAINTS" in error for error in result.errors)


def test_the_notes_name_the_file_they_are_about():
    result = plan()
    assert (
        "scf_ilita_clean.in: nbnd removido: o pw.x escolhe pelo número de elétrons do fragmento"
        in (result.notes)
    )
    assert any(note.startswith("scf_ilita_isolated.in: nbnd removido") for note in result.notes)
    renamed = plan(**{"name:scf_isolated": "so_h.in"}, mode="avancado")
    assert any(note.startswith("so_h.in: nbnd removido") for note in renamed.notes)
    no_spin = plan(from_text(SMALL.replace("  nspin = 2\n", "").replace("  nbnd = 40\n", "")))
    assert not any("nbnd" in note or "starting_magnetization" in note for note in no_spin.notes)


# -- R4: the script -------------------------------------------------------------------------------
def test_the_script_runs_the_inputs_in_order():
    result = plan()
    assert runs(result.files[0].text) == [f.name for f in result.files if f.name.endswith(".in")]
    body = script_lines(result)
    start = body.index("mkdir -p cdd_xsf")
    assert body[start:] == [
        "mkdir -p cdd_xsf",
        '${MPICOMMAND} ${PWCOMMAND} -i "scf_ilita.in" > "scf_ilita.out"',
        '${MPICOMMAND} ${PWCOMMAND} -i "scf_ilita_clean.in" > "scf_ilita_clean.out"',
        '${PWCOMMAND_SINGLE} -i "scf_ilita_isolated.in" > "scf_ilita_isolated.out"',
        '${PPCOMMAND} -i "pp_ilita_charge.in" > "pp_ilita_charge.out"',
        '${PPCOMMAND} -i "pp_ilita_clean_charge.in" > "pp_ilita_clean_charge.out"',
        '${PPCOMMAND} -i "pp_ilita_isolated_charge.in" > "pp_ilita_isolated_charge.out"',
        '${PPCOMMAND} -i "pp_charge_diff.in" > "pp_charge_diff.out"',
        "#" * 52,
        "exit 0",
    ]


def test_the_isolated_run_has_no_mpi_and_no_pools():
    # As in the cluster's cargas.qsub: the fragment is small, its k-points few.
    script = plan().files[0].text
    assert 'PWCOMMAND="/opt/espresso-7.1/bin/pw.x -nk 4"' in script
    assert 'PWCOMMAND_SINGLE="/opt/espresso-7.1/bin/pw.x"' in script
    assert 'PPCOMMAND="/opt/espresso-7.1/bin/pp.x"' in script
    mpi = [line for line in script.splitlines() if line.startswith("${MPICOMMAND}")]
    assert len(mpi) == 2 and not any("isolated" in line for line in mpi)
    assert not any(line.startswith("${MPICOMMAND}") and "PPCOMMAND" in line for line in mpi)


def test_the_script_runs_the_names_chosen():
    result = plan(
        mode="avancado",
        **{"name:scf_clean": "sem_h.in", "name:pp_diff": "diferenca.in", "xsf_dir": "xsf"},
    )
    assert runs(result.files[0].text) == [f.name for f in result.files if f.name.endswith(".in")]
    assert 'sem_h.in" > "sem_h.out"' in result.files[0].text
    assert 'diferenca.in" > "diferenca.out"' in result.files[0].text


# -- R5: the modes --------------------------------------------------------------------------------
def test_the_standard_mode_asks_for_the_atoms_alone():
    fields = CHARGE_DIFF.fields(ILITA, JOBS)
    assert [f.id for f in visible_fields(fields, "padrao")] == ["atoms"]
    atoms = next(f for f in fields if f.id == "atoms")
    assert (atoms.kind, atoms.group, atoms.standard, atoms.required) == (
        "atoms",
        ATOMS_TAB,
        True,
        True,
    )
    assert atoms.data.unit == "angstrom" and len(atoms.data.rows) == 6
    assert "Δρ = ρ(base) − ρ(clean) − ρ(isolated)" in atoms.hint
    # whatever the window holds in a hidden field, the standard mode takes the default
    result = plan(iflag="2 — gráfico 2D", xsf_dir="outra", np=7)
    assert text_of(result, "pp_diff") == IDEA
    assert (
        "mkdir -p cdd_xsf" in result.files[0].text and "#$ -pe physica 64" in result.files[0].text
    )


def test_the_advanced_mode_shows_every_field():
    fields = CHARGE_DIFF.fields(ILITA, JOBS)
    assert visible_fields(fields, "avancado") == fields
    assert [f.id for f in fields] == [
        "job_name",
        "np",
        "nk",
        *[
            f"name:{key}"
            for key in (
                "scf",
                "scf_clean",
                "scf_isolated",
                "pp_base",
                "pp_clean",
                "pp_isolated",
                "pp_diff",
            )
        ],
        "atoms",
        "iflag",
        "output_format",
        "xsf_dir",
    ]


def test_the_format_and_the_folder_apply_to_the_four_pp_inputs():
    result = plan(
        mode="avancado",
        iflag="2 — gráfico 2D",
        output_format="3 — XCrySDen (2D ou região 3D)",
        xsf_dir="saida/xsf",
    )
    assert result.errors == ()
    for key in ("pp_base", "pp_clean", "pp_isolated", "pp_diff"):
        text = text_of(result, key)
        assert "iflag = 2," in text and "output_format = 3," in text
        assert "fileout = 'saida/xsf/" in text
    assert "fileout = 'saida/xsf/ilita_charge_diff.xsf'" in text_of(result, "pp_diff")
    assert "fileout = 'saida/xsf/ilita_isolated_charge.xsf'" in text_of(result, "pp_isolated")
    assert "mkdir -p saida/xsf" in result.files[0].text


def test_the_xsf_folder_is_checked():
    for bad in ("/abs/xsf", "../fora", "a/../../b", "~/xsf", "$HOME/xsf"):
        result = plan(mode="avancado", xsf_dir=bad)
        assert "xsf_dir" in result.problems and not result.ok, bad
        assert [f.name for f in result.files] == NAMES
    here = plan(mode="avancado", xsf_dir=".")
    assert here.ok and "fileout = 'ilita_charge_diff.xsf'" in text_of(here, "pp_diff")
    assert "mkdir" not in here.files[0].text  # the folder exists already
    assert plan(mode="avancado", xsf_dir="cdd_xsf/").ok  # a trailing slash is the same folder
    assert "mkdir -p 'com espaco'" in plan(mode="avancado", xsf_dir="com espaco").files[0].text


def test_a_format_that_does_not_fit_the_plot_is_marked():
    result = plan(mode="avancado", iflag="2 — gráfico 2D")  # 5 (XSF 3D) needs iflag = 3
    assert list(result.problems) == ["output_format"]
    assert "output_format = 5 não vale para iflag = 2" in result.errors[0]
    assert plan(mode="avancado", iflag="1 — gráfico 1D").ok  # pp.x ignores the format there


def test_the_names_are_checked_like_the_other_types():
    result = plan(mode="avancado", **{"name:scf_clean": "scf_ilita.in"})
    assert not result.ok and {"name:scf", "name:scf_clean"} <= set(result.problems)
    result = plan(mode="avancado", **{"name:pp_diff": "diferenca"})
    assert "name:pp_diff" in result.problems


def test_registered_templates_exist_for_every_pp_input():
    assert {"qe/charge/pp_charge.in.j2", DIFF_TEMPLATE} <= set(CHARGE_DIFF.input_templates)
