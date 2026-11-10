"""Spec 25 R2, R6: the packaged Jinja2 templates and the .qsub scripts they make (with the names of
spec 28 R1, which the scripts receive as variables), in the cluster's new model (spec 86)."""

import fnmatch
import re
from importlib.resources import files

import pytest

from qe_studio.core.calc_create.render import (
    TemplateFailure,
    fortran_number,
    fortran_string,
    render,
    template_names,
    warm_templates,
)
from qe_studio.core.calc_create.scf_info import read_scf
from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.core.calc_create.types.base import Work
from qe_studio.core.calc_create.types.script import MYEMAIL_NOTE
from qe_studio.core.config import JobsConfig
from qe_studio.core.viewer.qsub_lint import lint_script
from reference_helpers import REFERENCE, needs_reference

from calc_helpers import AL_PATH, AL_SCF, JOBS, al, expanded, ni, runs, script_inputs

ROOT = files("qe_studio.resources").joinpath("templates")
NEW_MODEL = REFERENCE / "Novo_modelo_de_scripts_QSUB" / "bands.qsub"
EMAIL = "usuario@mail.com"


def test_once_warm_a_plan_reads_no_template(monkeypatch):
    warm_templates()

    def no_disk(name):
        raise AssertionError(f"read {name}")

    monkeypatch.setattr("qe_studio.core.calc_create.render._resource", no_disk)
    result = by_id("charge").plan(al(), {}, JOBS)
    assert result.ok and len(result.files) == 3


def test_reading_an_scf_warms_the_templates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "qe_studio.core.calc_create.scf_info.warm_templates", lambda: calls.append(1)
    )
    read_scf(AL_SCF)
    assert calls == [1]


def test_every_template_is_packaged_and_found():
    names = template_names()
    assert "qsub/_base.qsub.j2" in names
    for calc_type in REGISTRY:
        for name in (calc_type.script_template, *calc_type.input_templates):
            assert name in names
            resource = ROOT
            for part in name.split("/"):
                resource = resource.joinpath(part)
            assert resource.is_file()


def test_the_common_header_exists_once():
    scripts = [name for name in template_names() if name.startswith("qsub/")]
    assert [name for name in scripts if "_base" in name] == ["qsub/_base.qsub.j2"]
    for name in scripts:
        if name != "qsub/_base.qsub.j2":
            text = ROOT.joinpath("qsub").joinpath(name.removeprefix("qsub/")).read_text()
            assert text.startswith('{% extends "qsub/_base.qsub.j2" %}')
            assert "#$" not in text and "MPICOMMAND=" not in text


def test_a_missing_variable_names_itself():
    with pytest.raises(TemplateFailure, match="'myemail' is undefined"):
        render("qsub/scf.qsub.j2", {})
    with pytest.raises(TemplateFailure, match="não encontrado"):
        render("qsub/nada.qsub.j2", {})


def test_fortran_literals():
    assert fortran_string("it's") == "'it''s'"
    assert fortran_number(-25.0) == "-25.0"
    assert fortran_number(0.01) == "0.01"
    assert fortran_number(3) == "3"
    assert fortran_number(True) == ".true."


def _ours(type_id, scf, values):
    plan = by_id(type_id).plan(scf, values, JOBS, "avancado")
    assert not plan.errors
    return plan.files[0].text


def _model_lines() -> list[str]:
    """The cluster's model, line by line, as it is on disk (line 64 ends in a space)."""
    return NEW_MODEL.read_bytes().decode().splitlines(keepends=True)


@needs_reference
def test_the_bands_script_is_the_cluster_model_byte_for_byte():
    """R2.5: all but lines 2-4 of the model, which hold no one's name or e-mail (R4.3)."""
    values = {
        "job_name": "Bands-kao-001-p",
        "np": 32,
        "nk": 4,
        "kpath": AL_PATH,
        "name:scf": "scf.in",
        "name:bands": "bands.in",
        "name:bands_pp": "bands_pp.in",
    }
    plan = by_id("bandas").plan(al(), values, JobsConfig(myemail=EMAIL), "avancado")
    assert plan.ok
    lines = _model_lines()
    assert plan.files[0].text == lines[0] + "".join(lines[4:])
    assert "@" not in "".join(lines[1:4])


@needs_reference
@pytest.mark.parametrize("np_", [32, 64, 128])
def test_the_cluster_block_is_intact_in_every_type(np_):
    """R2.2: from ``Grid setup`` to ``sendMail "Running ..."`` only the job and its cores change."""
    block = "".join(_model_lines()[29:50])
    assert block.startswith("###       Grid setup") and block.endswith('sendMail "Running ..."\n')
    assert "###\t\tStart simulation\t\t\t###" in block
    block = block.replace("Bands-kao-001-p", "teste").replace("physica 32", f"physica {np_}")
    for calc_type in REGISTRY:
        values = {"job_name": "teste", "np": np_, "kpath": AL_PATH}
        assert block in calc_type.plan(al(), values, JOBS, "avancado").files[0].text, calc_type.id


@pytest.mark.parametrize("scf", [al, ni])
def test_every_script_passes_the_write_checks(scf):
    for calc_type in REGISTRY:
        script = calc_type.plan(scf(), {"kpath": AL_PATH}, JOBS).files[0].text
        assert lint_script(script) == [], calc_type.id


def test_the_email_reaches_the_script_of_every_type():
    for calc_type in REGISTRY:
        plan = calc_type.plan(al(), {"kpath": AL_PATH}, JobsConfig(myemail=EMAIL))
        assert f'MYEMAIL="{EMAIL}"\n' in plan.files[0].text, calc_type.id
        assert MYEMAIL_NOTE not in plan.notes


def test_without_an_email_the_script_goes_out_with_a_note():
    for calc_type in REGISTRY:
        plan = calc_type.plan(al(), {"kpath": AL_PATH}, JOBS)
        assert 'MYEMAIL=""\n' in plan.files[0].text, calc_type.id
        assert MYEMAIL_NOTE in plan.notes
    assert by_id("scf").plan(al(), {}, JOBS).ok  # a note: it never blocks


def _inputs_of(type_id, scf, values=None):
    return script_inputs(_ours(type_id, scf(), {"kpath": AL_PATH, **(values or {})}))


def test_the_inputs_go_into_variables_named_by_their_keys():
    assert _inputs_of("bandas", al) == {
        "QE_INPUTFILE": "scf_al.in",
        "QE_INPUTFILE_BANDS": "bands.in",
        "QE_INPUTFILE_BANDS_PP": "bands_pp.in",
    }
    assert _inputs_of("bandas", ni) == {
        "QE_INPUTFILE": "scf_ni.in",
        "QE_INPUTFILE_BANDS": "bands.in",
        "QE_INPUTFILE_BANDS_PP_UP": "bands_pp_up.in",
        "QE_INPUTFILE_BANDS_PP_DW": "bands_pp_dw.in",
    }
    assert _inputs_of("pdos", al) == {
        "QE_INPUTFILE": "scf_al.in",
        "QE_INPUTFILE_NSCF": "nscf_al.in",
        "QE_INPUTFILE_PROJWFC": "projwfc.in",
    }


def test_run_makes_a_shell_variable_of_any_key():
    work = Work(al(), {}, JOBS, names={"scf": "a.in", "vc-relax": "b.in"})
    assert work.run("scf") == ("${QE_INPUTFILE}", "${QE_INPUTFILE%.in}.out")
    assert work.run("vc-relax") == ("${QE_INPUTFILE_VC_RELAX}", "${QE_INPUTFILE_VC_RELAX%.in}.out")
    assert work.script_inputs == [("QE_INPUTFILE", "a.in"), ("QE_INPUTFILE_VC_RELAX", "b.in")]


def test_every_input_variable_is_a_shell_name_and_used_once():
    for calc_type in REGISTRY:
        for scf in (al(), ni()):
            script = calc_type.plan(scf, {"kpath": AL_PATH}, JOBS).files[0].text
            for variable in script_inputs(script):
                assert re.fullmatch(r"[A-Z_][A-Z0-9_]*", variable), variable
                assert script.count(f"{variable}=") == 1
                assert script.count(f'-i "${{{variable}}}"') == 1


def test_a_renamed_input_is_the_value_of_its_variable():
    script = _ours("bandas", al(), {"kpath": AL_PATH, "name:bands": "caminho.in"})
    assert 'QE_INPUTFILE_BANDS="caminho.in"\n' in script
    assert runs(script) == ["scf_al.in", "caminho.in", "bands_pp.in"]
    assert '-i "caminho.in" > "caminho.out"' in expanded(script)


def test_steps_of_each_type_in_order():
    assert runs(_ours("scf", al(), {})) == ["scf_al.in"]
    assert runs(_ours("relax", al(), {})) == ["relax_al.in"]
    assert runs(_ours("vc-relax", al(), {})) == ["vc-relax_al.in"]
    bands = _ours("bandas", al(), {"kpath": AL_PATH})
    assert runs(bands) == ["scf_al.in", "bands.in", "bands_pp.in"]
    spin = _ours("bandas", ni(), {"kpath": AL_PATH})
    assert runs(spin) == ["scf_ni.in", "bands.in", "bands_pp_up.in", "bands_pp_dw.in"]
    pdos = expanded(_ours("pdos", al(), {}))
    assert re.findall(r'-i "([^"]+)"', pdos) == ["scf_al.in", "nscf_al.in", "projwfc.in"]
    moved = pdos.index("mkdir -p orbitals\nmv *pdos_atm#* orbitals/ 2>/dev/null")
    assert pdos.index("projwfc.out") < moved < pdos.index('sendMail "Job done" "$?"')  # R2.4
    assert "${MPICOMMAND} ${BANDSCOMMAND}" not in spin  # bands.x runs serial, like the reference


@pytest.mark.parametrize("filpdos", ["pdos.dat", "wfc_teste.dat"])
def test_pdos_mv_takes_only_the_projections(filpdos):
    script = _ours("pdos", al(), {"filpdos": filpdos})
    pattern = re.search(r"^mv (\S+) orbitals/", script, re.MULTILINE)
    assert pattern is not None
    projections = [f"{filpdos}.pdos_atm#1(Al)_wfc#1(s)", f"{filpdos}.pdos_atm#1(Al)_wfc#2(p)"]
    others = [
        "scf_al.in",
        "scf_al.out",
        "nscf_al.in",
        "nscf_al.out",
        "projwfc.in",
        "projwfc.out",
        f"{filpdos}.pdos_tot",
    ]
    moved = [n for n in (*others, *projections) if fnmatch.fnmatchcase(n, pattern.group(1))]
    assert moved == projections  # a "wfc" glob would also take projwfc.in/out


def test_scripts_run_exactly_the_planned_inputs():
    for calc_type in REGISTRY:
        for scf in (al(), ni()):
            plan = calc_type.plan(scf, {"kpath": AL_PATH}, JOBS)
            inputs = [f.name for f in plan.files if f.name.endswith(".in")]
            assert runs(plan.files[0].text) == inputs


def test_no_script_template_names_an_input():
    """Spec 28 R1.4: the names reach the scripts as variables, so a renamed input is run."""
    scripts = [name for name in template_names() if name.startswith("qsub/")]
    assert "qsub/bands.qsub.j2" in scripts and "qsub/bandas.qsub.j2" not in scripts
    for name in scripts:
        text = ROOT.joinpath("qsub").joinpath(name.removeprefix("qsub/")).read_text()
        assert not re.search(r"[\w.-]+\.(in|out)\b", text), name


def test_only_np_nk_and_the_email_come_from_the_config():
    """The rest of the cluster side is fixed in the templates, as in the cluster's model."""
    jobs = JobsConfig(cores=32, nk=2, myemail=EMAIL)
    text = by_id("scf").plan(al(), {}, jobs, "avancado").files[0].text
    for line in (
        f'MYEMAIL="{EMAIL}"\n',
        "NK=2\n",
        'QE_COMMAND="/opt/espresso-7.1/bin/pw.x -nk $NK"\n',
        "#$ -pe physica 32\n",
        "export OMP_NUM_THREADS=1\nexport I_MPI_PIN_DOMAIN=core\n"
        "source /opt/intel/oneapi/mkl/latest/env/vars.sh\n"
        "source /opt/intel/oneapi/mpi/latest/env/vars.sh\n"
        "source /opt/bin/sendmail.sh\n",
        'MPICOMMAND="/opt/intel/oneapi/mpi/latest/bin/mpiexec -bootstrap ssh"\n',
    ):
        assert line in text


def test_pdos_mails_the_status_of_projwfc_not_of_mv():
    pdos = expanded(_ours("pdos", al(), {}))
    assert pdos.index("PROJWFC_STATUS=$?") < pdos.index("mv *pdos_atm#*")
    assert pdos.index("(exit ${PROJWFC_STATUS})") < pdos.index('sendMail "Job done" "$?"')
