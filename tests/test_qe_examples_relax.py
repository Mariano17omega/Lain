"""Real relax and vc-relax runs: BFGS steps, convergence, final structure and the SCF made of it."""

import re

import pytest

from qe_studio.core.qe.final_structure import read_final_structure
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.relax import DAMPED_DYNAMICS, read_relax
from qe_studio.core.qe.scf_from_relax import scf_from_relax

from qe_examples_helpers import (
    PW,
    bfgs_marks,
    damped_marks,
    is_bfgs,
    is_damped,
    number_setting,
    params,
    select,
    total_energies,
)

RELAX = ("relax", "vc-relax")
BFGS_CASES = select(PW, RELAX, where=lambda case: is_bfgs(case.output_text))
DAMPED_CASES = select(PW, RELAX, where=lambda case: is_damped(case.output_text))
DAMPED_CELL = [case for case in DAMPED_CASES if case.calculation == "vc-relax"]
DAMPED_IONS = [case for case in DAMPED_CASES if case.calculation == "relax"]
# FCP prints only the closing line of its own optimization: no step to read
OTHER_DYNAMICS = select(
    PW, RELAX, where=lambda case: not is_bfgs(case.output_text) and not is_damped(case.output_text)
)
FINISHED = [case for case in BFGS_CASES if "Begin final coordinates" in case.output_text]


def test_every_kind_of_run_is_present():
    assert BFGS_CASES and OTHER_DYNAMICS and FINISHED
    assert DAMPED_CELL and DAMPED_IONS


@pytest.mark.parametrize("case", params(BFGS_CASES))
def test_steps_are_the_announced_ones(case):
    data = read_relax(case.output_path)
    assert data.calculation == case.calculation
    assert len(data.steps) == bfgs_marks(case.output_text)


@pytest.mark.parametrize("case", params(BFGS_CASES))
def test_convergence_follows_the_text(case):
    assert read_relax(case.output_path).bfgs_converged is ("bfgs converged" in case.output_text)


@pytest.mark.parametrize("case", params(OTHER_DYNAMICS))
def test_other_dynamics_have_no_steps(case):
    """FCP prints no step the reader knows: the module refuses it, a limit held here on purpose
    (FIRE is the same, with no real output to test)."""
    assert read_relax(case.output_path).steps == []


@pytest.mark.parametrize("case", params(DAMPED_CASES))
def test_damped_steps_are_the_announced_ones(case):
    """Spec 101: every SCF of a damped dynamics is a step, numbered from 0 as the BFGS ones."""
    data = read_relax(case.output_path)
    assert data.dynamics == DAMPED_DYNAMICS and data.calculation == case.calculation
    assert (
        len(data.steps) == damped_marks(case.output_text) == len(total_energies(case.output_text))
    )
    assert [step.bfgs_step for step in data.steps] == list(range(len(data.steps)))
    assert data.truncated_steps == 0


@pytest.mark.parametrize("case", params(DAMPED_CASES))
def test_damped_convergence_follows_the_text(case):
    """The run that stops at ``nstep`` (50 steps) prints no convergence message."""
    data = read_relax(case.output_path)
    assert data.bfgs_converged is ("convergence achieved" in case.output_text)
    assert not data.bfgs_converged or data.converged


@pytest.mark.parametrize("case", params(BFGS_CASES))
def test_bfgs_runs_are_not_damped(case):
    assert read_relax(case.output_path).dynamics != DAMPED_DYNAMICS


@pytest.mark.parametrize("case", params(DAMPED_CELL))
def test_damped_cell_reads_pressure_volume_and_cell_but_no_enthalpy(case):
    data = read_relax(case.output_path)
    assert data.has_pressure and data.has_volume
    assert all(step.cell is not None for step in data.steps[1:])  # step 0's is never printed
    assert not any(step.enthalpy_ry is not None for step in data.steps)
    assert all(flag is False for __, flag in data.convergence_deltas())  # |ΔE|, not |ΔH|


@pytest.mark.parametrize("case", params(DAMPED_CELL))
def test_damped_cell_thresholds_are_the_ones_the_run_printed(case):
    printed = re.search(r"EPSE =\s*(\S+)\s+EPSF =\s*(\S+)", case.output_text)
    assert printed is not None
    data = read_relax(case.output_path)
    assert (data.energy_threshold, data.force_threshold) == (
        float(printed.group(1)),
        float(printed.group(2)),
    )


@pytest.mark.parametrize("case", params(DAMPED_IONS))
def test_damped_ions_keep_the_cell_fixed(case):
    """The run prints ``new unit-cell volume`` in its final coordinates anyway (spec 92)."""
    data = read_relax(case.output_path)
    assert data.calculation == "relax"
    assert not data.has_pressure and not data.has_volume
    assert all(step.cell is None for step in data.steps)


@pytest.mark.parametrize("case", params(FINISHED))
def test_final_structure_has_every_atom(case):
    final = read_final_structure(case.output_path)
    assert final is not None
    assert len(final.positions.lines) == number_setting(case.input_text, "nat")
    assert (final.cell is not None) is (case.calculation == "vc-relax")


@pytest.mark.parametrize("case", params(FINISHED))
def test_scf_made_from_the_relax_is_valid(case):
    final = read_final_structure(case.output_path)
    assert final is not None
    result = scf_from_relax(final, case.input_text)
    doc = lint(result.text)
    assert [issue for issue in doc.issues if issue.severity == "error"] == []
    assert doc.get("control", "calculation").value_text.strip("'\"") == "scf"
