"""The real runs of ``fixtures/qe_examples/`` and independent readings of their text.

``manifest.json`` lists them. The functions below read QE's text with their own patterns, on
purpose apart from ``core/qe``: the tests compare Lain's parsers with them.

Most outputs predate QE 7.1, which Lain does not support: a difference that only an older format
causes goes in a table of the test, with its reason, and no code changes for it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import QE_EXAMPLES

PW = "pw.x"
BANDS = "bands.x"
PROJWFC = "projwfc.x"
DOS = "dos.x"
PP = "pp.x"
# The 3D-RISM solver prints this phrase inside the SCF loop, and core/qe/scf.py takes it for the
# end of the SCF: the iterations are lost and the output refused.
RISM_GAP = "3D-RISM: the solver's 'convergence has been achieved' ends the SCF in core/qe/scf.py"
RISM_CASES = {"PW/RISM_example/H2O.NaCl_aq", "PW/RISM_example/HCHO.aq"}
# Valid Fortran, and in inputs of current QE: ASE's namelist reader keeps the double quotes, so
# QEInput.calculation is '"relax"' (InputEditor reads the same input correctly).
DOUBLE_QUOTE_GAP = 'calculation = "x": parse_input keeps the double quotes in the value'
_DOUBLE_QUOTED = re.compile(r"\bcalculation\s*=\s*\"", re.I)


@dataclass(frozen=True)
class Case:
    id: str
    source: str
    program: str
    version: str
    supported: bool
    calculation: str | None
    input: str
    output: str
    reason: str
    covers: tuple[str, ...]

    @property
    def input_path(self) -> Path:
        return QE_EXAMPLES / self.input

    @property
    def output_path(self) -> Path:
        return QE_EXAMPLES / self.output

    @property
    def input_text(self) -> str:
        return self.input_path.read_text(encoding="utf-8", errors="replace")

    @property
    def output_text(self) -> str:
        return self.output_path.read_text(encoding="utf-8", errors="replace")


MANIFEST = json.loads((QE_EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
CASES = [Case(**{**entry, "covers": tuple(entry["covers"])}) for entry in MANIFEST["cases"]]
DATA_FILES: list[str] = MANIFEST["data_files"]
DOUBLE_QUOTE_GAPS = {
    case.id: DOUBLE_QUOTE_GAP for case in CASES if _DOUBLE_QUOTED.search(case.input_text)
}


def select(
    program: str | None = None,
    calculations: Iterable[str] | None = None,
    where: Callable[[Case], bool] | None = None,
) -> list[Case]:
    wanted = None if calculations is None else set(calculations)
    return [
        case
        for case in CASES
        if (program is None or case.program == program)
        and (wanted is None or case.calculation in wanted)
        and (where is None or where(case))
    ]


def params(cases: Iterable[Case], gaps: Mapping[str, str] | None = None) -> list:
    """``cases`` as parameters; one named in ``gaps`` must fail, and fails the test if it passes."""
    gaps = gaps or {}
    return [
        pytest.param(
            case,
            id=case.id,
            marks=[pytest.mark.xfail(strict=True, reason=gaps[case.id])] if case.id in gaps else [],
        )
        for case in cases
    ]


# -- what an input says -------------------------------------------------------------------------
def setting(text: str, key: str) -> str | None:
    """The value of ``key`` in a namelist, last one wins as Fortran reads it; no comment lines."""
    pattern = re.compile(rf"(?<![\w(]){re.escape(key)}\s*=\s*([^\s,/!]+)", re.I)
    lines = (line.split("!", 1)[0] for line in text.splitlines())
    found = [match.group(1) for line in lines for match in pattern.finditer(line)]
    return found[-1] if found else None


def number_setting(text: str, key: str) -> float | None:
    value = setting(text, key)
    return None if value is None else float(value.lower().replace("d", "e"))


def flag_setting(text: str, key: str) -> bool:
    value = setting(text, key)
    return value is not None and value.lower().strip(".").startswith("t")


# -- what a pw.x output says --------------------------------------------------------------------
_TOTAL = re.compile(r"^(!+)\s+total energy\s+=\s+(-?\d+\.\d+)\s+Ry", re.M)
_FERMI = re.compile(
    r"the Fermi energy is\s+(-?\d+\.\d+)\s+ev"
    r"|highest occupied, lowest unoccupied level \(ev\):\s+(-?\d+\.\d+)"
    r"|highest occupied level \(ev\):\s+(-?\d+\.\d+)"
)
_SPIN_FERMI = re.compile(r"the spin up/dw Fermi energies are\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+ev")
_REPORTED = re.compile(r"convergence has been achieved in\s+(\d+)\s+iterations")
_BFGS_STEP = re.compile(r"number of bfgs steps\s+=\s+(\d+)")
_BFGS_END = re.compile(r"bfgs (?:converged|failed) (?:in|after)\s+\d+\s+scf cycles")
_DAMPED_STEP = re.compile(r"Entering Dynamics[:;]\s+(?:iteration|it)\s+=")
_DAMPED_END = re.compile(r"Damped Dynamics: convergence achieved|convergence achieved, Efinal=")


def total_energies(text: str) -> list[float]:
    """Every ``!`` total energy, in order."""
    return [float(match.group(2)) for match in _TOTAL.finditer(text)]


def last_reference_energy(text: str) -> float | None:
    """The last Fermi or HOMO energy; a pair of spin Fermi energies counts as their mean."""
    last = (None, -1)
    for match in _FERMI.finditer(text):
        value = next(group for group in match.groups() if group is not None)
        last = (float(value), match.start())
    for match in _SPIN_FERMI.finditer(text):
        if match.start() > last[1]:
            last = ((float(match.group(1)) + float(match.group(2))) / 2, match.start())
    return last[0]


def reported_iterations(text: str) -> list[int]:
    return [int(value) for value in _REPORTED.findall(text)]


def bfgs_marks(text: str) -> int:
    """How many BFGS steps the output announces, its closing line included."""
    return len(_BFGS_STEP.findall(text)) + len(_BFGS_END.findall(text))


def damped_marks(text: str) -> int:
    """How many steps a damped dynamics announces (ions or cell): an ``Entering Dynamics`` after
    every SCF but the last, which the convergence message closes. A run that stops at ``nstep``
    prints no such message and an ``Entering Dynamics`` after its last SCF too."""
    return len(_DAMPED_STEP.findall(text)) + len(_DAMPED_END.findall(text))


def is_damped(text: str) -> bool:
    return damped_marks(text) > 0


def is_bfgs(text: str) -> bool:
    """A BFGS run whose steps are printed: with FCP only the closing line is."""
    return bfgs_marks(text) > 0 and "FCP Relaxation is activated" not in text


def unfinished_hybrid(text: str) -> bool:
    """A hybrid run stopped before its exchange loop closed, which prints no ``!!`` energy."""
    return "EXX: now go back" in text and "!!" not in text
