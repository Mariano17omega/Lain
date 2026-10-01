"""SCF convergence from a pw.x output: energy, estimated accuracy and magnetization per iteration.

The file is read line by line, like ``relax.py``: relax and vc-relax outputs hold many SCF cycles and
can be hundreds of MB. Only the first cycle is read; ``cycles`` says how many the file has.

An iteration is complete once its ``total energy`` and ``estimated scf accuracy`` are read. The last
iteration of a converged run prints its energy as ``!    total energy``. A cut iteration (job running
or killed) is dropped and counted in ``truncated``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .relax import NUMBER

ScfStatus = Literal["converged", "not_converged", "running"]

_ITERATION = re.compile(r"^\s*iteration\s+#\s*(\d+)")
_ECUT = re.compile(rf"\becut\s*=\s*({NUMBER})\s*Ry")
_BETA = re.compile(rf"\bbeta\s*=\s*({NUMBER})")
_ENERGY = re.compile(rf"^\s*(!)?\s*total\s+energy\s*=\s*({NUMBER})\s*Ry")
_ACCURACY = re.compile(rf"estimated\s+scf\s+accuracy\s*<\s*({NUMBER})\s*Ry")
_HARRIS = re.compile(rf"Harris-Foulkes\s+estimate\s*=\s*({NUMBER})\s*Ry")
_TOTAL_MAG = re.compile(rf"total\s+magnetization\s*=\s*((?:{NUMBER}\s+){{1,3}})Bohr")
_ABS_MAG = re.compile(rf"absolute\s+magnetization\s*=\s*({NUMBER})\s*Bohr")
_CPU = re.compile(rf"total\s+cpu\s+time\s+spent\s+up\s+to\s+now\s+is\s+({NUMBER})\s*secs")
_THRESHOLD = re.compile(rf"\bconvergence\s+threshold\s*=\s*({NUMBER})")
_MIXING_BETA = re.compile(rf"^\s*mixing\s+beta\s*=\s*({NUMBER})")
_MIXING_MODE = re.compile(r"number\s+of\s+iterations\s+used\s*=\s*\d+\s+(\S+)\s+mixing")
_CONVERGED = re.compile(r"convergence\s+has\s+been\s+achieved\s+in\s+(\d+)\s+iterations")
_NOT_CONVERGED = re.compile(r"convergence\s+NOT\s+achieved\s+after\s+(\d+)\s+iterations")


def _number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


@dataclass(frozen=True)
class ScfIteration:
    index: int  # as printed by pw.x ("iteration #  n")
    energy_ry: float
    accuracy_ry: float
    ecut_ry: float | None = None
    beta: float | None = None
    harris_ry: float | None = None
    total_mag: float | None = None  # Bohr magnetons per cell (norm of the vector if non-collinear)
    abs_mag: float | None = None
    cpu_s: float | None = None


@dataclass
class ScfData:
    iterations: list[ScfIteration]
    status: ScfStatus
    threshold_ry: float | None = None  # conv_thr
    mixing_beta: float | None = None
    mixing_mode: str | None = None  # plain | TF | local-TF
    n_reported: int | None = None  # N of "convergence has been achieved in N iterations"
    final_energy_ry: float | None = None  # the "!" total energy
    job_done: bool = False
    truncated: int = 0
    cycles: int = 0  # SCF cycles in the file (relax and vc-relax have several)

    @property
    def spin(self) -> bool:
        return any(it.total_mag is not None or it.abs_mag is not None for it in self.iterations)

    @property
    def energy_deltas(self) -> list[float]:
        """|E_i − E_{i−1}| for i ≥ 1 (Ry)."""
        return [
            abs(b.energy_ry - a.energy_ry)
            for a, b in zip(self.iterations, self.iterations[1:], strict=False)
        ]


def _magnitude(values: str) -> float:
    return math.sqrt(sum(_number(v) ** 2 for v in values.split()))


def parse_scf(lines: Iterable[str]) -> ScfData:
    iterations: list[ScfIteration] = []
    current: dict | None = None
    threshold = mixing_beta = None
    mixing_mode: str | None = None
    status: ScfStatus = "running"
    n_reported: int | None = None
    final_energy: float | None = None
    job_done = False
    truncated = cycles = 0
    phase = "header"  # header → reading (first cycle) → after (first cycle closed)

    def close() -> None:
        """Keep the iteration being read if complete, else count it as cut."""
        nonlocal current, truncated
        if current is None:
            return
        if current["energy_ry"] is not None and current["accuracy_ry"] is not None:
            iterations.append(ScfIteration(**current))
        else:
            truncated += 1
        current = None

    for line in lines:
        # Substring checks first: most lines match nothing and regexes are the slow part.
        if "JOB DONE" in line:
            job_done = True
            continue
        if "iteration #" in line and (match := _ITERATION.match(line)):
            index = int(match.group(1))
            if phase == "after" or (phase == "reading" and index == 1):
                # A later SCF (relax): only counted.
                if index == 1:
                    cycles += 1
                close()
                phase = "after"
                continue
            if phase == "header":
                phase, cycles = "reading", 1
            close()
            ecut, beta = _ECUT.search(line), _BETA.search(line)
            current = {
                "index": index,
                "energy_ry": None,
                "accuracy_ry": None,
                "ecut_ry": _number(ecut.group(1)) if ecut else None,
                "beta": _number(beta.group(1)) if beta else None,
                "harris_ry": None,
                "total_mag": None,
                "abs_mag": None,
                "cpu_s": None,
            }
            continue
        if phase == "after":
            continue
        if phase == "header":
            if "threshold" in line and threshold is None and (m := _THRESHOLD.search(line)):
                threshold = _number(m.group(1))
            elif "mixing beta" in line and mixing_beta is None and (m := _MIXING_BETA.match(line)):
                mixing_beta = _number(m.group(1))
            elif (
                "iterations used" in line
                and mixing_mode is None
                and (m := _MIXING_MODE.search(line))
            ):
                mixing_mode = m.group(1)
            continue
        if "convergence" in line and (
            (match := _CONVERGED.search(line)) or (match := _NOT_CONVERGED.search(line))
        ):
            status = "converged" if match.re is _CONVERGED else "not_converged"
            n_reported = int(match.group(1))
            close()
            phase = "after"
        elif current is None:
            continue
        elif "total energy" in line and (match := _ENERGY.match(line)):
            current["energy_ry"] = _number(match.group(2))
            if match.group(1) and final_energy is None:
                final_energy = current["energy_ry"]
        elif "accuracy" in line and (match := _ACCURACY.search(line)):
            current["accuracy_ry"] = _number(match.group(1))
        elif "Harris" in line and (match := _HARRIS.search(line)):
            current["harris_ry"] = _number(match.group(1))
        elif "magnetization" in line:
            if match := _TOTAL_MAG.search(line):
                current["total_mag"] = _magnitude(match.group(1))
            elif match := _ABS_MAG.search(line):
                current["abs_mag"] = _number(match.group(1))
        elif "cpu time" in line and (match := _CPU.search(line)):
            current["cpu_s"] = _number(match.group(1))
    close()  # a cut iteration at the end of the file

    return ScfData(
        iterations=iterations,
        status=status,
        threshold_ry=threshold,
        mixing_beta=mixing_beta,
        mixing_mode=mixing_mode,
        n_reported=n_reported,
        final_energy_ry=final_energy,
        job_done=job_done,
        truncated=truncated,
        cycles=cycles,
    )


def read_scf(path: Path) -> ScfData:
    """Stream ``path`` (never read whole: relax outputs hold many SCF cycles)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_scf(handle)
