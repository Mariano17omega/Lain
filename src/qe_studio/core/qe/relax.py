"""Relaxation progress (relax / vc-relax) from a pw.x output: energy and force per BFGS step.

Ported from the step/threshold part of the Relax-Viewer reference app (``parser.py``,
``diagnostics.py``; removed from ``Documentation/``, see git history). The file is read line by
line: vc-relax outputs can be hundreds of MB.

A step is complete once its ``!`` total energy, ``Total force`` and step identification are
read. The identification is ``number of bfgs steps = k`` or, for the last SCF of a run,
``bfgs converged in N scf cycles and M bfgs steps`` / ``bfgs failed after …`` (the reference
dropped that one). The SCF after ``Final scf calculation`` (vc-relax, new plane-wave basis) is
not a BFGS step.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .. import cancel
from .structure import SITE, format_formula

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][-+]?\d+)?"
QE_DEFAULT_THRESHOLDS = (1.0e-4, 1.0e-3)  # etot_conv_thr (Ry), forc_conv_thr (Ry/Bohr)

HEADER, CRITERIA, INPUT, QE_DEFAULT = "cabeçalho", "critérios", "entrada", "padrão do QE"

_ENERGY = re.compile(rf"^\s*!+\s*total\s+energy\s*=\s*({NUMBER})\s*Ry", re.I)
_FORCE = re.compile(rf"\bTotal\s+force\s*=\s*({NUMBER})", re.I)
_BFGS_STEPS = re.compile(r"\bnumber\s+of\s+bfgs\s+steps\s*=\s*(\d+)", re.I)
_SCF_CYCLES = re.compile(r"\bnumber\s+of\s+scf\s+cycles\s*=\s*(\d+)", re.I)
_BFGS_END = re.compile(  # "bfgs failed after …": history reset twice, convergence not achieved
    r"\bbfgs\s+(converged|failed)\s+(?:in|after)\s+(\d+)\s+scf\s+cycles\s+and\s+(\d+)\s+bfgs",
    re.I,
)
_ENERGY_THR = re.compile(rf"energy\s+convergence\s+thresh\.\s*=\s*({NUMBER})", re.I)
_FORCE_THR = re.compile(rf"force\s+convergence\s+thresh\.\s*=\s*({NUMBER})", re.I)
_CRITERIA = re.compile(rf"criteria:\s*energy\s*<\s*({NUMBER})\s*Ry,\s*force\s*<\s*({NUMBER})", re.I)


def _number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


@dataclass(frozen=True)
class RelaxStep:
    index: int  # sequential position among complete steps (the plot's X)
    bfgs_step: int  # as printed by pw.x
    energy_ry: float
    force_ry_bohr: float
    scf_cycles: int | None = None


@dataclass
class RelaxData:
    calculation: str  # relax | vc-relax
    steps: list[RelaxStep]
    energy_threshold: float
    force_threshold: float
    energy_threshold_source: str
    force_threshold_source: str
    converged: bool
    job_done: bool
    truncated_steps: int = 0
    final_scf_energy: float | None = None
    formula: str | None = None
    bfgs_converged: bool = field(default=False, repr=False)

    @property
    def energy_deltas(self) -> list[float]:
        """|E_i − E_{i−1}| for i ≥ 1 (Ry)."""
        return [
            abs(b.energy_ry - a.energy_ry) for a, b in zip(self.steps, self.steps[1:], strict=False)
        ]

    @property
    def defaulted_thresholds(self) -> bool:
        return QE_DEFAULT in (self.energy_threshold_source, self.force_threshold_source)


def parse_relax(
    lines: Iterable[str], fallback: tuple[float | None, float | None] = (None, None)
) -> RelaxData:
    """``fallback`` = (etot_conv_thr, forc_conv_thr) from the input, used when the output
    printed no thresholds."""
    steps: list[RelaxStep] = []
    pending: dict | None = None
    truncated = 0
    header: list[float | None] = [None, None]
    criteria: tuple[float, float] | None = None
    bfgs_converged = job_done = vc_relax = final_scf = False
    final_energy: float | None = None
    species: dict[str, int] = {}
    in_header = True

    def close(bfgs_step: int, scf_cycles: int | None = None) -> None:
        nonlocal pending
        if pending is None or pending["force"] is None:
            return
        steps.append(
            RelaxStep(
                len(steps),
                bfgs_step,
                pending["energy"],
                pending["force"],
                scf_cycles if scf_cycles is not None else pending["scf"],
            )
        )
        pending = None

    for line in cancel.checked(lines):
        # Substring checks first: most lines match nothing and regexes are the slow part.
        if "JOB DONE" in line:
            job_done = True
            continue
        if final_scf:
            if final_energy is None and "!" in line and (match := _ENERGY.match(line)):
                final_energy = _number(match.group(1))
            continue
        if "!" in line and (match := _ENERGY.match(line)):
            if pending is not None:
                truncated += 1
            pending = {"energy": _number(match.group(1)), "force": None, "scf": None}
            in_header = False
            continue
        if in_header:
            if "tau(" in line and (match := SITE.match(line)):
                name = match.group("species")
                species[name] = species.get(name, 0) + 1
            elif "thresh." in line:
                for i, pattern in enumerate((_ENERGY_THR, _FORCE_THR)):
                    if header[i] is None and (match := pattern.search(line)):
                        header[i] = _number(match.group(1))
            continue
        if "Final scf calculation" in line:
            final_scf = True
        elif "Total force" in line and pending is not None and (match := _FORCE.search(line)):
            pending["force"] = _number(match.group(1))
        elif "scf cycles" in line:
            if match := _BFGS_END.search(line):
                bfgs_converged = match.group(1).lower() == "converged"
                close(int(match.group(3)), int(match.group(2)))
            elif pending is not None and (match := _SCF_CYCLES.search(line)):
                pending["scf"] = int(match.group(1))
        elif "bfgs steps" in line and (match := _BFGS_STEPS.search(line)):
            close(int(match.group(1)))
        elif "criteria:" in line and (match := _CRITERIA.search(line)):
            criteria = (_number(match.group(1)), _number(match.group(2)))
        elif "Final enthalpy" in line or "new unit-cell volume" in line:
            vc_relax = True
    if pending is not None:
        truncated += 1

    thresholds, sources = [], []
    for i in range(2):
        for value, source in (
            (header[i], HEADER),
            (criteria[i] if criteria else None, CRITERIA),
            (fallback[i], INPUT),
            (QE_DEFAULT_THRESHOLDS[i], QE_DEFAULT),
        ):
            if value is not None:
                thresholds.append(value)
                sources.append(source)
                break
    data = RelaxData(
        calculation="vc-relax" if vc_relax else "relax",
        steps=steps,
        energy_threshold=thresholds[0],
        force_threshold=thresholds[1],
        energy_threshold_source=sources[0],
        force_threshold_source=sources[1],
        converged=False,
        job_done=job_done,
        truncated_steps=truncated,
        final_scf_energy=final_energy,
        formula=format_formula(species),
        bfgs_converged=bfgs_converged,
    )
    data.converged = bfgs_converged or is_relaxed(data)
    return data


def is_relaxed(data: RelaxData) -> bool:
    """``diagnostics.is_relaxed`` of the reference: the last |ΔE| and force below thresholds."""
    if data.bfgs_converged:
        return True
    deltas = data.energy_deltas
    if not deltas:
        return False
    return deltas[-1] <= data.energy_threshold and data.steps[-1].force_ry_bohr <= (
        data.force_threshold
    )


def read_relax(path: Path, fallback: tuple[float | None, float | None] = (None, None)) -> RelaxData:
    """Stream ``path`` (never read whole: vc-relax outputs can be huge)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_relax(handle, fallback)
