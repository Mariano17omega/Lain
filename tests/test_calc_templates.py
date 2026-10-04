"""Spec 25 R2, R6: the packaged Jinja2 templates and the .qsub scripts they make."""

from importlib.resources import files
from pathlib import Path

import pytest

from qe_studio.core.calc_create.render import (
    TemplateFailure,
    fortran_number,
    fortran_string,
    render,
    template_names,
)
from qe_studio.core.calc_create.types import REGISTRY, by_id

from calc_helpers import AL_PATH, JOBS, al, ni, runs

ROOT = files("qe_studio.resources").joinpath("templates")
REFERENCE = Path(__file__).parents[1] / "Documentation" / "Referencia_de_scripts_QSUB"


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
    with pytest.raises(TemplateFailure, match="qe_bin"):
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
    plan = by_id(type_id).plan(scf, values, JOBS)
    assert not plan.errors
    return plan.files[0].text


# Reference lines that are not the scripts' business: authorship, an unused plotband.x and the
# heredoc that became projwfc.in.
_IGNORED = ("# Executa o programa", "# Cicero", "# Mariano", "PLOTCOMMAND=")


def _reference(name: str, rename: dict[str, str] | None = None) -> list[str]:
    lines, heredoc = [], False
    for line in (REFERENCE / name).read_text().splitlines():
        line = line.rstrip()
        if line.startswith("cat >"):
            heredoc = True
        if heredoc:
            heredoc = line != "EOF"
            continue
        if line and not line.startswith(_IGNORED):
            for old, new in (rename or {}).items():
                line = line.replace(old, new)
            lines.append(line)
    return lines


def _split(lines: list[str]) -> tuple[list[str], list[str]]:
    """Header (up to the "Executa" banner) and the commands after it, banners dropped."""
    end = next(i for i, line in enumerate(lines) if "Executa as Simulacao" in line) + 2
    body = [line for line in lines[end:] if line and not set(line) <= {"#"}]
    return lines[:end], body


@pytest.mark.parametrize(
    "type_id, reference, scf, values, rename",
    [
        ("relax", "relax.qsub", al, {"job_name": "test", "nk": 8}, None),
        ("vc-relax", "vc-relax.qsub", al, {"job_name": "test", "nk": 8}, None),
        ("scf", "relax.qsub", al, {"job_name": "test", "nk": 8}, {"relax": "scf"}),
        ("bandas", "bands.qsub", al, {"job_name": "BD010o1", "kpath": AL_PATH}, None),
        ("pdos", "PDOS.qsub", al, {"job_name": "pdo2"}, {"proj.": "projwfc."}),
    ],
)
def test_scripts_reproduce_the_reference(type_id, reference, scf, values, rename):
    ours = [line.rstrip() for line in _ours(type_id, scf(), values).splitlines() if line.strip()]
    header, body = _split(ours)
    ref_header, ref_body = _split(_reference(reference, rename))
    assert header == ref_header
    assert body == ref_body
    assert ours[-1] == "exit 0"


def test_steps_of_each_type_in_order():
    assert runs(_ours("scf", al(), {})) == ["scf.in"]
    assert runs(_ours("relax", al(), {})) == ["relax.in"]
    assert runs(_ours("vc-relax", al(), {})) == ["vc-relax.in"]
    assert runs(_ours("bandas", al(), {"kpath": AL_PATH})) == ["scf.in", "bands.in", "bands_pp.in"]
    spin = _ours("bandas", ni(), {"kpath": AL_PATH})
    assert runs(spin) == ["scf.in", "bands.in", "bands_pp_up.in", "bands_pp_dw.in"]
    pdos = _ours("pdos", al(), {})
    assert runs(pdos) == ["scf.in", "nscf.in", "projwfc.in"]
    assert pdos.index("projwfc.out") < pdos.index(
        "mkdir -p orbitals\nmv *wfc* orbitals/ 2>/dev/null"
    )
    assert "${MPICOMMAND} ${BANDSCOMMAND}" not in spin  # bands.x runs serial, like the reference


def test_scripts_run_exactly_the_planned_inputs():
    for calc_type in REGISTRY:
        for scf in (al(), ni()):
            plan = calc_type.plan(scf, {"kpath": AL_PATH}, JOBS)
            inputs = [f.name for f in plan.files if f.name.endswith(".in")]
            assert runs(plan.files[0].text) == inputs


def test_cluster_settings_come_from_the_config():
    jobs = JOBS.model_copy(
        update={
            "qe_bin": "/sw/qe-7.3/bin",
            "mpi_command": "mpirun",
            "parallel_env": "mpi",
            "omp_threads": 2,
            "env_lines": ["module load qe"],
        }
    )
    text = by_id("scf").plan(al(), {"np": 32, "nk": 2}, jobs).files[0].text
    for line in (
        'PWCOMMAND="/sw/qe-7.3/bin/pw.x -nk 2"',
        "#$ -pe mpi 32",
        "export OMP_NUM_THREADS=2\nmodule load qe\n",
        'MPICOMMAND="mpirun"',
    ):
        assert line in text
