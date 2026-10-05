"""Relaxation progress (relax / vc-relax) from a pw.x output: energy and force per BFGS step and,
for a vc-relax, enthalpy, pressure, volume and cell.

Ported from the step/threshold part of the Relax-Viewer reference app (``parser.py``,
``diagnostics.py``; removed from ``Documentation/``, see git history). The file is read line by
line: vc-relax outputs can be hundreds of MB.

A step is complete once its ``!`` total energy, ``Total force`` and step identification are
read. The identification is ``number of bfgs steps = k`` or, for the last SCF of a run,
``bfgs converged in N scf cycles and M bfgs steps`` / ``bfgs failed after …`` (the reference
dropped that one). The SCF after ``Final scf calculation`` (vc-relax, new plane-wave basis) is
not a BFGS step.

A BFGS block of a vc-relax is ``!`` energy, ``Total force``, the stress (``P=``), ``number of bfgs
steps = k``, ``enthalpy new`` (of the geometry just computed) and then ``new unit-cell volume`` and
``CELL_PARAMETERS``, which are the geometry of step k + 1. So the pressure and the enthalpy go to
step k, and the volume and cell to the step whose SCF ran on them: the next one (only when its
``bfgs_step`` follows, a trimmed output leaves ``None``), or the last one for the ``Begin final
coordinates`` block of a converged run. The step 0 geometry is never printed in the run: the
header volume is the *input* cell, wrong after ``restart_mode = 'restart'``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .. import cancel
from .structure import SITE, format_formula

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][-+]?\d+)?"
BOHR_TO_ANGSTROM = 0.529177210903
# etot_conv_thr (Ry), forc_conv_thr (Ry/Bohr), press_conv_thr (kbar)
QE_DEFAULT_THRESHOLDS = (1.0e-4, 1.0e-3, 0.5)

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
_PRESS_THR = re.compile(rf"press\s+convergence\s+thresh\.\s*=\s*({NUMBER})", re.I)
_CRITERIA = re.compile(  # the cell part only in a vc-relax
    rf"criteria:\s*energy\s*<\s*({NUMBER})\s*Ry,\s*force\s*<\s*({NUMBER})"
    rf"(?:\s*Ry/Bohr\s*,\s*cell\s*<\s*({NUMBER}))?",
    re.I,
)
_PRESSURE = re.compile(rf"\(kbar\)\s+P=\s*({NUMBER})")
_ENTHALPY_NEW = re.compile(rf"\benthalpy\s+new\s*=\s*({NUMBER})\s*Ry", re.I)
_FINAL_ENTHALPY = re.compile(rf"\bFinal\s+enthalpy\s*=\s*({NUMBER})\s*Ry", re.I)
_NEW_VOLUME = re.compile(
    rf"new\s+unit-cell\s+volume\s*=\s*{NUMBER}\s*a\.u\.\^3\s*\(\s*({NUMBER})\s*Ang\^3", re.I
)
_CELL_HEADER = re.compile(
    rf"^\s*CELL_PARAMETERS\s*\(\s*(?:alat\s*=\s*({NUMBER})|(angstrom)|(bohr))\s*\)", re.I
)


def _number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def _cell_row(line: str) -> tuple[float, float, float] | None:
    tokens = line.split()
    if len(tokens) != 3:
        return None
    try:
        return (_number(tokens[0]), _number(tokens[1]), _number(tokens[2]))
    except ValueError:
        return None


Cell = tuple[tuple[float, float, float], ...]  # three rows, Å


@dataclass(frozen=True)
class RelaxStep:
    index: int  # sequential position among complete steps (the plot's X)
    bfgs_step: int  # as printed by pw.x
    energy_ry: float
    force_ry_bohr: float
    scf_cycles: int | None = None
    # vc-relax only (None when the run did not print it for this step)
    enthalpy_ry: float | None = None
    pressure_kbar: float | None = None
    volume_ang3: float | None = None
    cell: Cell | None = None  # rows in Å


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
    pressure_threshold: float = QE_DEFAULT_THRESHOLDS[2]  # press_conv_thr (kbar)
    pressure_threshold_source: str = QE_DEFAULT
    target_pressure_kbar: float = 0.0  # ``press`` of the input

    @property
    def energy_deltas(self) -> list[float]:
        """|E_i − E_{i−1}| for i ≥ 1 (Ry)."""
        return [
            abs(b.energy_ry - a.energy_ry) for a, b in zip(self.steps, self.steps[1:], strict=False)
        ]

    def enthalpy_deltas(self) -> list[tuple[float, bool]]:
        """(|H_i − H_{i−1}|, True) for i ≥ 1 (Ry): the quantity a vc-relax BFGS compares to
        ``etot_conv_thr``. A pair without the enthalpy at either end falls back to |ΔE| (False)."""
        out = []
        for a, b in zip(self.steps, self.steps[1:], strict=False):
            if a.enthalpy_ry is not None and b.enthalpy_ry is not None:
                out.append((abs(b.enthalpy_ry - a.enthalpy_ry), True))
            else:
                out.append((abs(b.energy_ry - a.energy_ry), False))
        return out

    def convergence_deltas(self) -> list[tuple[float, bool]]:
        """What the energy panel draws: |ΔH| in a vc-relax, |ΔE| otherwise (the bool says which)."""
        if self.calculation == "vc-relax":
            return self.enthalpy_deltas()
        return [(delta, False) for delta in self.energy_deltas]

    @property
    def has_pressure(self) -> bool:
        return any(step.pressure_kbar is not None for step in self.steps)

    @property
    def has_volume(self) -> bool:
        return any(step.volume_ang3 is not None for step in self.steps)

    @property
    def defaulted_thresholds(self) -> bool:
        return QE_DEFAULT in (self.energy_threshold_source, self.force_threshold_source)


def parse_relax(
    lines: Iterable[str],
    fallback: tuple[float | None, float | None] = (None, None),
    *,
    target_pressure: float | None = None,
    press_conv_thr: float | None = None,
) -> RelaxData:
    """``fallback`` = (etot_conv_thr, forc_conv_thr) from the input, used when the output
    printed no thresholds; ``press_conv_thr`` likewise, ``target_pressure`` is the input's
    ``press`` (kbar, default 0)."""
    steps: list[RelaxStep] = []
    pending: dict | None = None
    truncated = 0
    header: list[float | None] = [None, None, None]
    criteria: tuple[float | None, ...] | None = None
    bfgs_converged = job_done = vc_relax = final_scf = False
    final_energy: float | None = None
    species: dict[str, int] = {}
    in_header = True
    # vc-relax: where a value printed in this block belongs (see the module docstring)
    block: int | None = None  # the step the current block closed
    carry: dict | None = None  # volume / cell of the geometry of the next step
    final_coords = False  # inside "Begin final coordinates" of a converged run
    cell_rows: list[tuple[float, float, float]] | None = None
    cell_scale = 1.0

    def close(bfgs_step: int, scf_cycles: int | None = None) -> None:
        nonlocal pending, block, carry
        if pending is None or pending["force"] is None:
            return
        volume, cell = None, None
        if carry is not None and carry["after"] + 1 == bfgs_step:
            volume, cell = carry["volume"], carry["cell"]
        carry = None
        block = len(steps)
        steps.append(
            RelaxStep(
                block,
                bfgs_step,
                pending["energy"],
                pending["force"],
                scf_cycles if scf_cycles is not None else pending["scf"],
                pressure_kbar=pending["pressure"],
                volume_ang3=volume,
                cell=cell,
            )
        )
        pending = None

    def set_enthalpy(value: float) -> None:
        if block is not None:
            steps[block] = replace(steps[block], enthalpy_ry=value)

    def set_geometry(volume: float | None = None, cell: Cell | None = None) -> None:
        """The volume / cell printed in this block: the last step's own geometry in the final
        coordinates, else the next step's."""
        nonlocal carry
        if block is None:
            return
        if final_coords:
            step = steps[block]
            fill: dict = {}
            if volume is not None and step.volume_ang3 is None:
                fill["volume_ang3"] = volume
            if cell is not None and step.cell is None:
                fill["cell"] = cell
            if fill:
                steps[block] = replace(step, **fill)
            return
        after = steps[block].bfgs_step
        if carry is None or carry["after"] != after or volume is not None:
            carry = {"after": after, "volume": None, "cell": None}  # a block's own, never stale
        if volume is not None:
            carry["volume"] = volume
        if cell is not None:
            carry["cell"] = cell

    for line in cancel.checked(lines):
        # Substring checks first: most lines match nothing and regexes are the slow part.
        if "JOB DONE" in line:
            job_done = True
            continue
        if final_scf:
            if final_energy is None and "!" in line and (match := _ENERGY.match(line)):
                final_energy = _number(match.group(1))
            continue
        if cell_rows is not None:
            if (row := _cell_row(line)) is not None:
                cell_rows.append(row)
                if len(cell_rows) == 3:
                    set_geometry(
                        cell=tuple(
                            (x * cell_scale, y * cell_scale, z * cell_scale)
                            for x, y, z in cell_rows
                        )
                    )
                    cell_rows = None
                continue
            cell_rows = None  # not a cell row (a cut file, another block): read it as any line
        if "!" in line and (match := _ENERGY.match(line)):
            if pending is not None:
                truncated += 1
            pending = {
                "energy": _number(match.group(1)),
                "force": None,
                "scf": None,
                "pressure": None,
            }
            block = None
            in_header = False
            continue
        if in_header:
            if "tau(" in line and (match := SITE.match(line)):
                name = match.group("species")
                species[name] = species.get(name, 0) + 1
            elif "thresh." in line:
                for i, pattern in enumerate((_ENERGY_THR, _FORCE_THR, _PRESS_THR)):
                    if header[i] is None and (match := pattern.search(line)):
                        header[i] = _number(match.group(1))
            continue
        if block is not None:  # the tail of a block: after its step closed, up to ATOMIC_POSITIONS
            if "ATOMIC_POSITIONS" in line:
                block, final_coords = None, False
            elif "enthalpy" in line:
                vc_relax = True
                pattern = _FINAL_ENTHALPY if "Final" in line else _ENTHALPY_NEW
                if match := pattern.search(line):
                    set_enthalpy(_number(match.group(1)))
            elif "new unit-cell volume" in line:
                vc_relax = True
                if match := _NEW_VOLUME.search(line):
                    set_geometry(volume=_number(match.group(1)))
            elif "CELL_PARAMETERS" in line and (match := _CELL_HEADER.match(line)):
                alat, _angstrom, bohr = match.groups()
                if alat is not None:
                    cell_scale = BOHR_TO_ANGSTROM * _number(alat)
                else:
                    cell_scale = BOHR_TO_ANGSTROM if bohr is not None else 1.0
                cell_rows = []
            elif "Begin final coordinates" in line:
                final_coords = bfgs_converged
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
            criteria = tuple(None if g is None else _number(g) for g in match.groups())
        elif pending is not None and "P=" in line and (match := _PRESSURE.search(line)):
            pending["pressure"] = _number(match.group(1))
    if pending is not None:
        truncated += 1

    fallbacks = (fallback[0], fallback[1], press_conv_thr)
    thresholds, sources = [], []
    for i in range(3):
        for value, source in (
            (header[i], HEADER),
            (criteria[i] if criteria else None, CRITERIA),
            (fallbacks[i], INPUT),
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
        pressure_threshold=thresholds[2],
        pressure_threshold_source=sources[2],
        target_pressure_kbar=target_pressure if target_pressure is not None else 0.0,
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


def read_relax(
    path: Path,
    fallback: tuple[float | None, float | None] = (None, None),
    *,
    target_pressure: float | None = None,
    press_conv_thr: float | None = None,
) -> RelaxData:
    """Stream ``path`` (never read whole: vc-relax outputs can be huge)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_relax(
            handle, fallback, target_pressure=target_pressure, press_conv_thr=press_conv_thr
        )
