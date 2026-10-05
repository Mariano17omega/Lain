"""Spec 29: the "Carga" type: ``charge.qsub``, the SCF copy and ``pp_<nome>_charge.in`` (pp.x)."""

import pytest

from qe_studio.core.calc_create.render import TemplateFailure, render
from qe_studio.core.calc_create.types import by_id, visible_fields
from qe_studio.core.calc_create.types.charge import (
    FORMATS_OF_IFLAG,
    IFLAGS,
    OUTPUT_FORMATS,
    PP_TEMPLATE,
    choice,
    code_of,
    fileout_dir,
)
from qe_studio.core.calc_create.unit import UNIT_OUTDIR
from qe_studio.core.calc_create.writer import folder_name
from qe_studio.core.config import JobsConfig

from calc_helpers import AL_SCF, JOBS, al, from_text, runs

CHARGE = by_id("charge")
AL_UPPER = from_text(AL_SCF.read_text().replace("prefix='al'", "prefix='Al'"))
# The input of the idea (specs/Ideias.md), for the prefix Al.
IDEA = """&INPUTPP
prefix = 'Al',
outdir = './tmp/',
filplot = 'Al.charge',
plot_num = 0
/
&PLOT
nfile = 1,
filepp(1) = 'Al.charge',
weight(1) = 1.0,
iflag = 3,
output_format = 5,
fileout = 'cdd_xsf/Al_charge.xsf'
/
"""


def plan(scf=AL_UPPER, mode="padrao", name="Al", **values):
    return CHARGE.plan(scf, values, JOBS, mode, name)


def pp_of(result):
    planned = result.by_key("pp_charge")
    assert planned is not None
    return planned


def script_lines(result) -> list[str]:
    return [line for line in result.files[0].text.splitlines() if line.strip()]


# -- R1: the type and its files -----------------------------------------------------------------
def test_the_type_is_registered_after_pdos():
    assert by_id("charge") is CHARGE
    assert (CHARGE.label, CHARGE.folder_prefix, CHARGE.script_name) == (
        "Carga",
        "Charge",
        "charge.qsub",
    )
    assert CHARGE.uses_name and not by_id("pdos").uses_name


def test_files_take_the_folder_name():
    result = plan(name="Al")
    assert not result.errors, result.errors
    assert [f.name for f in result.files] == ["charge.qsub", "scf_Al.in", "pp_Al_charge.in"]
    assert [f.tab_label for f in result.files] == [
        "Script (charge.qsub)",
        "SCF (scf_Al.in)",
        "pp_Al_charge.in",
    ]
    assert [f.kind for f in result.files] == ["qsub", "pw_input", "qe_input"]


def test_no_name_is_pp_charge_and_the_folder_is_charge():
    result = plan(name="")
    assert [f.name for f in result.files] == ["charge.qsub", "scf_Al.in", "pp_charge.in"]
    assert folder_name(CHARGE, "") == "Charge" and folder_name(CHARGE, "Al") == "Charge_Al"
    assert [f.name for f in plan(name="  ").files][2] == "pp_charge.in"


def test_the_scf_copy_is_the_unit_copy():
    text = AL_SCF.read_text()
    copy = plan().by_key("scf").text
    assert copy == text.replace("prefix='al'", "prefix='Al'").replace(
        "outdir='./tmp'", "outdir='./tmp/'"
    )


def test_the_other_types_ignore_the_name():
    for type_id in ("scf", "bandas", "pdos"):
        calc_type = by_id(type_id)
        assert not calc_type.uses_name
        assert [f.name for f in calc_type.input_files(al(), "Al")] == [
            f.name for f in calc_type.input_files(al())
        ]


# -- R2: the pp.x input -------------------------------------------------------------------------
def test_the_standard_input_is_the_idea():
    assert pp_of(plan()).text == IDEA


def test_the_template_needs_every_variable():
    values = {
        "prefix": "Al",
        "outdir": UNIT_OUTDIR,
        "filplot": "Al.charge",
        "plot_num": 0,
        "iflag": 3,
        "output_format": 5,
        "fileout": "cdd_xsf/Al_charge.xsf",
    }
    assert render(PP_TEMPLATE, values) == IDEA
    for missing in values:
        with pytest.raises(TemplateFailure):
            render(PP_TEMPLATE, {k: v for k, v in values.items() if k != missing})


def test_a_prefix_with_a_quote_is_escaped():
    scf = from_text(AL_SCF.read_text().replace("prefix='al'", 'prefix="O\'Neil"'))
    text = pp_of(plan(scf)).text
    assert "prefix = 'O''Neil'," in text and "filplot = 'O''Neil.charge'," in text


# -- R3: the script -----------------------------------------------------------------------------
def test_the_script_makes_the_folder_then_runs_pw_then_pp_without_mpi():
    result = plan(name="Al")
    lines = script_lines(result)
    mkdir = lines.index("mkdir -p cdd_xsf")
    pw = lines.index('${MPICOMMAND} ${PWCOMMAND} -i "scf_Al.in" > "scf_Al.out"')
    pp = lines.index('${PPCOMMAND} -i "pp_Al_charge.in" > "pp_Al_charge.out"')
    assert mkdir < pw < pp
    assert 'PPCOMMAND="/opt/espresso-7.1/bin/pp.x"' in lines
    assert not any("MPICOMMAND" in line for line in lines if "PPCOMMAND}" in line)
    assert runs(result.files[0].text) == ["scf_Al.in", "pp_Al_charge.in"]


def test_np_and_nk_are_the_config_defaults():
    text = plan().files[0].text
    assert "#$ -pe physica 64" in text and 'PWCOMMAND="/opt/espresso-7.1/bin/pw.x -nk 4"' in text


def test_the_mkdir_follows_fileout():
    other = plan(mode="avancado", fileout="saida/xsf/Al.xsf")
    assert "mkdir -p saida/xsf" in script_lines(other) and "mkdir -p cdd_xsf" not in script_lines(
        other
    )
    bare = plan(mode="avancado", fileout="Al.xsf")
    assert not any(line.startswith("mkdir") for line in script_lines(bare))
    dotted = plan(mode="avancado", fileout="./Al.xsf")
    assert not any(line.startswith("mkdir") for line in script_lines(dotted))
    assert "fileout = 'Al.xsf'" in pp_of(bare).text


def test_a_folder_with_a_space_is_quoted():
    assert fileout_dir("cdd_xsf/a.xsf") == "cdd_xsf"
    assert fileout_dir("minha pasta/a.xsf") == "'minha pasta'"
    assert fileout_dir("a.xsf") is None


def test_a_renamed_input_is_the_one_the_script_runs():
    result = plan(mode="avancado", **{"name:pp_charge": "carga.in", "name:scf": "base.in"})
    assert [f.name for f in result.files] == ["charge.qsub", "base.in", "carga.in"]
    assert runs(result.files[0].text) == ["base.in", "carga.in"]
    assert '-i "carga.in" > "carga.out"' in result.files[0].text


# -- R4: fields and validation ------------------------------------------------------------------
def test_the_standard_mode_asks_for_nothing():
    fields = CHARGE.fields(AL_UPPER, JOBS, "Al")
    assert visible_fields(fields, "padrao") == []
    assert [f.id for f in visible_fields(fields, "avancado")][-4:] == [
        "plot_num",
        "iflag",
        "output_format",
        "fileout",
    ]
    assert {
        f.group for f in fields if f.id in ("plot_num", "iflag", "output_format", "fileout")
    } == {"pp_charge"}


def test_the_name_field_defaults_to_the_standard_name():
    fields = {f.id: f.default for f in CHARGE.fields(AL_UPPER, JOBS, "Fe")}
    assert fields["name:pp_charge"] == "pp_Fe_charge.in"
    assert fields["fileout"] == "cdd_xsf/Al_charge.xsf"


def test_advanced_values_reach_the_input():
    result = plan(
        mode="avancado",
        plot_num=0,
        iflag=choice(3, IFLAGS),
        output_format=choice(6, OUTPUT_FORMATS),
        fileout="cdd_xsf/Al.cube",
    )
    assert not result.errors, result.errors
    text = pp_of(result).text
    assert "output_format = 6," in text and "fileout = 'cdd_xsf/Al.cube'" in text


def test_the_standard_mode_drops_what_the_window_holds():
    result = plan(mode="padrao", fileout="outra/Al.xsf", output_format=choice(6, OUTPUT_FORMATS))
    assert pp_of(result).text == IDEA


@pytest.mark.parametrize("fileout", ["../Al.xsf", "/tmp/Al.xsf", "a/../../Al.xsf", "~/Al.xsf"])
def test_fileout_must_stay_inside_the_folder(fileout):
    result = plan(mode="avancado", fileout=fileout)
    assert result.errors and not result.ok
    assert "fileout" in result.problems and "dentro da pasta" in result.problems["fileout"]


@pytest.mark.parametrize(
    ("iflag", "output_format", "ok"),
    [
        (3, 5, True),
        (3, 6, True),
        (3, 3, True),
        (3, 7, False),
        (3, 0, False),
        (2, 5, False),
        (2, 7, True),
        (2, 2, True),
        (0, 0, True),
        (1, 5, True),  # pp.x ignores the format of a 1D plot
        (4, 5, True),
    ],
)
def test_the_format_must_fit_the_plot(iflag, output_format, ok):
    result = plan(
        mode="avancado",
        iflag=choice(iflag, IFLAGS),
        output_format=choice(output_format, OUTPUT_FORMATS),
    )
    assert result.ok is ok, result.errors
    assert ("output_format" in result.problems) is (not ok)
    if not ok:
        assert "iflag" in result.problems["output_format"]


def test_a_negative_plot_num_is_an_error():
    result = plan(mode="avancado", plot_num=-1)
    assert not result.ok and "plot_num" in result.problems
    assert plan(mode="avancado", plot_num=5).ok


def test_the_choices_are_the_codes_of_the_input_pp_doc():
    fields = {f.id: f for f in CHARGE.fields(AL_UPPER, JOBS)}
    assert [code_of(c, -1) for c in fields["iflag"].choices] == [0, 1, 2, 3, 4]
    assert [code_of(c, -1) for c in fields["output_format"].choices] == [0, 2, 3, 5, 6, 7]
    assert fields["iflag"].default == choice(3, IFLAGS)
    assert fields["output_format"].default == choice(5, OUTPUT_FORMATS)
    assert code_of("", 9) == 9 and code_of(None, 9) == 9 and code_of("x", 9) == 9
    assert set(FORMATS_OF_IFLAG[3]) <= set(OUTPUT_FORMATS)
    assert set(FORMATS_OF_IFLAG[2]) <= set(OUTPUT_FORMATS)


def test_a_bad_name_is_marked_like_any_other_file_name():
    result = plan(mode="avancado", **{"name:pp_charge": "carga"})
    assert not result.ok and "name:pp_charge" in result.problems


def test_the_cluster_settings_come_from_the_config():
    jobs = JobsConfig(qe_bin="/sw/qe-7.3/bin", cores=32, nk=2)
    text = CHARGE.plan(AL_UPPER, {}, jobs, "padrao", "Al").files[0].text
    assert 'PPCOMMAND="/sw/qe-7.3/bin/pp.x"' in text and "#$ -pe physica 32" in text
