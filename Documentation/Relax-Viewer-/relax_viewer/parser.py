from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import RelaxationResult, RelaxationStep, Atom, Structure

NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][-+]?\d+)?"

ENERGY_THRESHOLD_RE = re.compile(
    rf"(?:energy\s+convergence\s+thresh\.|etot_conv_thr)\s*=?\s*(?P<value>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
FORCE_THRESHOLD_RE = re.compile(
    rf"(?:force\s+convergence\s+thresh\.|forc_conv_thr)\s*=?\s*(?P<value>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
CRITERIA_RE = re.compile(
    rf"criteria:\s*energy\s*<\s*(?P<energy>{NUMBER_PATTERN})\s*Ry,\s*"
    rf"force\s*<\s*(?P<force>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
CONVERGED_ENERGY_RE = re.compile(
    rf"^\s*!\s+total\s+energy\s*=\s*(?P<value>{NUMBER_PATTERN})\s*Ry",
    re.IGNORECASE,
)
TOTAL_FORCE_RE = re.compile(
    rf"\bTotal\s+force\s*=\s*(?P<value>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
BFGS_STEPS_RE = re.compile(
    r"\bnumber\s+of\s+bfgs\s+steps\s*=\s*(?P<value>\d+)",
    re.IGNORECASE,
)
SCF_CYCLES_RE = re.compile(
    r"\bnumber\s+of\s+scf\s+cycles\s*=\s*(?P<value>\d+)",
    re.IGNORECASE,
)
BFGS_CONVERGED_RE = re.compile(r"\bbfgs\s+converged\b", re.IGNORECASE)
FINAL_SCF_RE = re.compile(r"\bFinal\s+scf\s+calculation\b", re.IGNORECASE)

CELL_HEADER_RE = re.compile(
    r"^\s*CELL_PARAMETERS\s*(?:\((?P<unit>\w+)\))?",
    re.IGNORECASE,
)
ATOM_HEADER_RE = re.compile(
    r"^\s*ATOMIC_POSITIONS\s*(?:\((?P<unit>\w+)\))?",
    re.IGNORECASE,
)
ATOM_LINE_RE = re.compile(
    rf"^\s*(?P<element>[A-Za-z]+[0-9]*)\s+(?P<x>{NUMBER_PATTERN})\s+(?P<y>{NUMBER_PATTERN})\s+(?P<z>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
ALAT_RE = re.compile(
    rf"^\s*lattice\s+parameter\s*\(alat\)\s*=\s*(?P<value>{NUMBER_PATTERN})\s+a\.u\.",
    re.IGNORECASE,
)
AXIS_RE = re.compile(
    rf"^\s*a\((?P<index>[1-3])\)\s*=\s*\(\s*(?P<x>{NUMBER_PATTERN})\s+(?P<y>{NUMBER_PATTERN})\s+(?P<z>{NUMBER_PATTERN})\s*\)",
    re.IGNORECASE,
)


def parse_relax_output(path: str | Path) -> RelaxationResult:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8", errors="replace")
    return parse_relax_output_text(text, source_path=source_path)


def parse_relax_output_text(
    text: str,
    source_path: str | Path = Path("relax.out"),
) -> RelaxationResult:
    source = Path(source_path)
    energy_threshold: float | None = None
    force_threshold: float | None = None
    bfgs_converged = False
    saw_final_scf = False
    truncated_steps = 0
    steps: list[RelaxationStep] = []
    pending: dict[str, Any] | None = None

    current_alat: float | None = None
    current_crystal_axes: list[tuple[float, float, float]] = []
    current_cell_parameters: list[tuple[float, float, float]] = []
    current_cell_unit: str | None = None
    last_structure: Structure | None = None

    def emit_pending_if_complete() -> bool:
        nonlocal pending
        if pending is None:
            return False
        if (
            pending.get("energy") is None
            or pending.get("force") is None
            or pending.get("bfgs_step") is None
        ):
            return False

        steps.append(
            RelaxationStep(
                sequence=len(steps) + 1,
                bfgs_step=int(pending["bfgs_step"]),
                total_energy_ry=float(pending["energy"]),
                total_force_ry_bohr=float(pending["force"]),
                scf_cycles=pending.get("scf_cycles"),
            )
        )
        pending = None
        return True

    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        criteria_match = CRITERIA_RE.search(line)
        if criteria_match:
            energy_threshold = _parse_number(criteria_match.group("energy"))
            force_threshold = _parse_number(criteria_match.group("force"))

        if energy_threshold is None:
            match = ENERGY_THRESHOLD_RE.search(line)
            if match:
                energy_threshold = _parse_number(match.group("value"))

        if force_threshold is None:
            match = FORCE_THRESHOLD_RE.search(line)
            if match:
                force_threshold = _parse_number(match.group("value"))

        if BFGS_CONVERGED_RE.search(line):
            bfgs_converged = True

        if FINAL_SCF_RE.search(line):
            saw_final_scf = True
            break

        alat_match = ALAT_RE.search(line)
        if alat_match:
            current_alat = _parse_number(alat_match.group("value"))

        axis_match = AXIS_RE.search(line)
        if axis_match:
            idx = int(axis_match.group("index")) - 1
            x = _parse_number(axis_match.group("x"))
            y = _parse_number(axis_match.group("y"))
            z = _parse_number(axis_match.group("z"))
            while len(current_crystal_axes) <= idx:
                current_crystal_axes.append((0.0, 0.0, 0.0))
            current_crystal_axes[idx] = (x, y, z)

        cell_match = CELL_HEADER_RE.search(line)
        if cell_match:
            unit = cell_match.group("unit") or "bohr"
            cell_unit = unit.lower()
            cell_parameters = []
            for _ in range(3):
                i += 1
                if i < n:
                    parts = lines[i].split()
                    if len(parts) >= 3:
                        cell_parameters.append((
                            _parse_number(parts[0]),
                            _parse_number(parts[1]),
                            _parse_number(parts[2])
                        ))
            if len(cell_parameters) == 3:
                current_cell_parameters = cell_parameters
                current_cell_unit = cell_unit
            i += 1
            continue

        atom_match = ATOM_HEADER_RE.search(line)
        if atom_match:
            atom_unit = (atom_match.group("unit") or "angstrom").lower()
            atoms = []
            i += 1
            while i < n:
                atom_line = lines[i]
                line_match = ATOM_LINE_RE.match(atom_line)
                if not line_match:
                    i -= 1
                    break
                element = line_match.group("element")
                x = _parse_number(line_match.group("x"))
                y = _parse_number(line_match.group("y"))
                z = _parse_number(line_match.group("z"))
                atoms.append(Atom(element=element, x=x, y=y, z=z))
                i += 1

            cell_to_use = None
            cell_unit_to_use = None
            if current_cell_parameters:
                cell_to_use = tuple(current_cell_parameters)
                cell_unit_to_use = current_cell_unit
            elif len(current_crystal_axes) == 3 and current_alat is not None:
                factor = current_alat * 0.5291772109
                cell_to_use = tuple(
                    (ax * factor, ay * factor, az * factor)
                    for ax, ay, az in current_crystal_axes
                )
                cell_unit_to_use = "angstrom"

            last_structure = Structure(
                cell_parameters=cell_to_use,
                atoms=tuple(atoms),
                unit=atom_unit,
                cell_unit=cell_unit_to_use
            )
            i += 1
            continue

        energy_match = CONVERGED_ENERGY_RE.search(line)
        if energy_match:
            if pending is not None:
                truncated_steps += 1
            pending = {
                "energy": _parse_number(energy_match.group("value")),
                "force": None,
                "bfgs_step": None,
                "scf_cycles": None,
            }
            i += 1
            continue

        if pending is not None:
            force_match = TOTAL_FORCE_RE.search(line)
            if force_match:
                pending["force"] = _parse_number(force_match.group("value"))
                emit_pending_if_complete()
                i += 1
                continue

            scf_match = SCF_CYCLES_RE.search(line)
            if scf_match:
                pending["scf_cycles"] = int(scf_match.group("value"))
                i += 1
                continue

            bfgs_match = BFGS_STEPS_RE.search(line)
            if bfgs_match:
                pending["bfgs_step"] = int(bfgs_match.group("value"))
                emit_pending_if_complete()

        i += 1

    if pending is not None:
        truncated_steps += 1

    return RelaxationResult(
        source_path=source,
        energy_threshold_ry=energy_threshold,
        force_threshold_ry_bohr=force_threshold,
        bfgs_converged=bfgs_converged,
        steps=tuple(steps),
        saw_final_scf=saw_final_scf,
        truncated_steps=truncated_steps,
        structure=last_structure,
    )


def _parse_number(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))

