"""Spec 103: the generated ``.qsub`` runs in bash and ends at the first step that did not finish.

The script is the one "Criar cálculo" writes, with only the cluster's paths swapped for stand-ins in
``tmp_path``: fake QE programs, no ``mpiexec``, a ``sendMail`` that writes each call down. Nothing
here reaches the cluster. pw.x leaves with status 0 and ``JOB DONE.`` also when the SCF does not
converge or a ``.EXIT`` stops it (``QE:PW/src/stop_run.f90``): the fakes print what pw.x prints.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.scf_info import read_scf
from qe_studio.core.calc_create.types import by_id

from calc_helpers import AL_PATH, AL_SCF, JOBS, SI_SCF, al, from_text, runs
from conftest import FIXTURES

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="runs the script in bash")

QE_BIN = "/opt/espresso-7.1/bin/"
MPI = 'MPICOMMAND="/opt/intel/oneapi/mpi/latest/bin/mpiexec -bootstrap ssh"'
INTEL = (
    "source /opt/intel/oneapi/mkl/latest/env/vars.sh",
    "source /opt/intel/oneapi/mpi/latest/env/vars.sh",
)
SENDMAIL = "source /opt/bin/sendmail.sh"
HOSTS = "node01 32 physica.q@node01 UNDEFINED\n"
# A QE program: it notes its ``-i`` input in ran.txt, prints ``<input>.fake`` (else what a run
# that went well ends with) and leaves with the status in ``<input>.status`` (else 0).
FAKE = r"""#!/bin/bash
while [ $# -gt 0 ]; do
    if [ "$1" = "-i" ]; then input=$2; fi
    shift
done
echo "$input" >> ran.txt
if [ -f "$input.fake" ]; then cat "$input.fake"; else printf '\n   JOB DONE.\n'; fi
exit "$(cat "$input.status" 2>/dev/null || echo 0)"
"""
NOT_CONVERGED = "\n     convergence NOT achieved after 100 iterations: stopping\n\n   JOB DONE.\n"
STOPPED = "\n     Program stopped by user request\n\n   JOB DONE.\n"
MAX_STEPS = "\n     The maximum number of steps has been reached.\n\n   JOB DONE.\n"
CRASHED = "\n     %%%%%%%%%%%%%%\n     Error in routine cdiaghg (1):\n"


@dataclass(frozen=True)
class Run:
    status: int
    log: str  # stdout and stderr, as SGE writes them to <name>.o<id> with ``-j y``
    mails: list[str]
    ran: list[str]
    folder: Path


def run_script(tmp_path: Path, script: str, fakes: dict[str, tuple[str, int]]) -> Run:
    """Run ``script`` in a folder of its own; ``fakes`` maps an input to its program's output and
    status."""
    programs = tmp_path / "bin"
    programs.mkdir()
    for program in ("pw.x", "bands.x", "projwfc.x", "pp.x"):
        (programs / program).write_text(FAKE)
        (programs / program).chmod(0o755)
    (tmp_path / "sendmail.sh").write_text('sendMail() { echo "$*" >> mails.txt; }\n')
    (tmp_path / "hosts").write_text(HOSTS)
    folder = tmp_path / "job"
    folder.mkdir()
    for name, (text, status) in fakes.items():
        (folder / f"{name}.fake").write_text(text)
        (folder / f"{name}.status").write_text(str(status))
    for line in (MPI, SENDMAIL, *INTEL):
        assert script.count(line) == 1, line
    local = script.replace(QE_BIN, f"{programs}/").replace(MPI, 'MPICOMMAND=""')
    local = local.replace(SENDMAIL, f'source "{tmp_path / "sendmail.sh"}"')
    for line in INTEL:
        local = local.replace(line, ":")
    assert not [line for line in local.split("\n") if "/opt/" in line and not line.startswith("#")]
    (folder / "job.qsub").write_text(local)
    env = {"PATH": os.environ["PATH"], "PE_HOSTFILE": str(tmp_path / "hosts")}
    result = subprocess.run(
        ["bash", "job.qsub"], cwd=folder, env=env, capture_output=True, text=True, timeout=30
    )
    mails = folder / "mails.txt"
    ran = folder / "ran.txt"
    return Run(
        result.returncode,
        result.stdout + result.stderr,
        mails.read_text().splitlines() if mails.exists() else [],
        ran.read_text().splitlines() if ran.exists() else [],
        folder,
    )


def script_of(type_id: str, values: dict | None = None) -> str:
    plan = by_id(type_id).plan(al(), {"kpath": AL_PATH, **(values or {})}, JOBS, "avancado")
    assert plan.ok, plan.errors
    return plan.files[0].text


def test_a_job_that_goes_well_runs_every_step_and_mails_done(tmp_path):
    script = script_of("bandas")
    run = run_script(tmp_path, script, {})
    assert run.ran == runs(script) == ["scf_al.in", "bands.in", "bands_pp.in"]
    assert all((run.folder / name.replace(".in", ".out")).is_file() for name in run.ran)
    assert run.mails == ["Running ...", "Job done 0"]
    assert run.log == HOSTS and run.status == 0  # the log of spec 85: only the machines


@pytest.mark.parametrize(
    ("output", "status"),
    [(NOT_CONVERGED, 0), (CRASHED, 1)],
    ids=["scf-not-converged", "pw-x-error"],
)
def test_a_failed_scf_stops_the_job_before_the_bands(tmp_path, output, status):
    run = run_script(tmp_path, script_of("bandas"), {"scf_al.in": (output, status)})
    assert run.ran == ["scf_al.in"]
    assert not (run.folder / "bands.out").exists()
    assert run.mails == ["Running ...", "Job failed: scf_al.out 1"]
    assert run.log == HOSTS + "Job failed: scf_al.out (status 1)\n"
    assert run.status == 1


def test_the_real_status_of_a_step_goes_in_the_mail_and_the_job_leaves_with_1(tmp_path):
    """99 would make SGE reschedule the job and 100 put it in error: the job leaves with 1."""
    run = run_script(tmp_path, script_of("scf"), {"scf_al.in": (CRASHED, 99)})
    assert run.mails[-1] == "Job failed: scf_al.out 99" and run.status == 1


def test_a_stop_by_exit_ends_the_job(tmp_path):
    """The cancel of spec 70: pw.x deletes ``<prefix>.EXIT``, so bands.x would run without it."""
    run = run_script(tmp_path, script_of("bandas"), {"bands.in": (STOPPED, 0)})
    assert run.ran == ["scf_al.in", "bands.in"]
    assert run.mails[-1] == "Job failed: bands.out 1" and run.status == 1


def test_a_relax_that_reaches_nstep_is_a_failure(tmp_path):
    run = run_script(tmp_path, script_of("relax"), {"relax_al.in": (MAX_STEPS, 0)})
    assert run.mails == ["Running ...", "Job failed: relax_al.out 1"] and run.status == 1


def test_a_post_processing_step_without_job_done_stops_the_difference(tmp_path):
    plan = by_id("charge_diff").plan(from_text(SMALL), {"atoms": (5, 6)}, JOBS, "padrao")
    assert plan.ok, plan.errors
    script = plan.files[0].text
    run = run_script(tmp_path, script, {"pp_ilita_clean_charge.in": ("\n   Bands\n", 0)})
    assert run.ran == runs(script)[:5]
    assert "pp_charge_diff.in" not in run.ran
    assert run.mails[-1] == "Job failed: pp_ilita_clean_charge.out 1"


def test_pdos_mails_done_with_0_also_with_no_projection_to_move(tmp_path):
    run = run_script(tmp_path, script_of("pdos"), {})
    assert run.ran == ["scf_al.in", "nscf_al.in", "projwfc.in"]
    assert (run.folder / "orbitals").is_dir()
    assert run.mails == ["Running ...", "Job done 0"] and run.status == 0


def test_a_failed_projwfc_is_mailed(tmp_path):
    run = run_script(tmp_path, script_of("pdos"), {"projwfc.in": (CRASHED, 1)})
    assert run.mails[-1] == "Job failed: projwfc.out 1" and run.status == 1
    assert not (run.folder / "orbitals").exists()


def test_adsorption_energy_stops_at_the_first_scf_that_fails(tmp_path):
    """Decided by the user: the SCFs do not depend on each other, but the job still stops."""
    listed = tuple(
        read_scf(path) for path in (SI_SCF, AL_SCF, FIXTURES / "qe731_ni_spin_fixed" / "ni.scf.in")
    )
    plan = by_id("ads_energy").plan(listed[0], {}, JOBS, "padrao", "", listed)
    assert plan.ok, plan.errors
    script = plan.files[0].text
    assert runs(script) == ["scf_silicon.in", "scf_al.in", "scf_nifix.in"]
    run = run_script(tmp_path, script, {"scf_al.in": (NOT_CONVERGED, 0)})
    assert run.ran == ["scf_silicon.in", "scf_al.in"]
    assert run.mails[-1] == "Job failed: scf_al.out 1" and run.status == 1
