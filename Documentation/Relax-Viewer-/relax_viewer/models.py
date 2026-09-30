from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Atom:
    element: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Structure:
    cell_parameters: tuple[tuple[float, float, float], ...] | None  # 3x3 matrix (a1, a2, a3)
    atoms: tuple[Atom, ...]
    unit: str  # 'crystal', 'angstrom', 'bohr', etc.
    cell_unit: str | None = None


@dataclass(frozen=True)
class RelaxationStep:
    sequence: int
    bfgs_step: int
    total_energy_ry: float
    total_force_ry_bohr: float
    scf_cycles: int | None = None


@dataclass(frozen=True)
class EnergyDelta:
    step: RelaxationStep
    delta_ry: float


@dataclass(frozen=True)
class RelaxationResult:
    source_path: Path
    energy_threshold_ry: float | None
    force_threshold_ry_bohr: float | None
    bfgs_converged: bool
    steps: tuple[RelaxationStep, ...]
    saw_final_scf: bool = False
    truncated_steps: int = 0
    structure: Structure | None = None

    @property
    def final_step(self) -> RelaxationStep | None:
        if not self.steps:
            return None
        return self.steps[-1]

    @property
    def energy_deltas(self) -> tuple[EnergyDelta, ...]:
        deltas: list[EnergyDelta] = []
        for previous, current in zip(self.steps, self.steps[1:]):
            deltas.append(
                EnergyDelta(
                    step=current,
                    delta_ry=abs(current.total_energy_ry - previous.total_energy_ry),
                )
            )
        return tuple(deltas)

