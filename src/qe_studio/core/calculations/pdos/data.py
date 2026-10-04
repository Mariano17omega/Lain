"""PDOS dataset: the projections of projwfc.x plus the Fermi energies of the SCF / NSCF runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...qe import projwfc
from ...qe.pw_output import PwOutput
from ..base import DetectionResult, LoadError, SniffFn


@dataclass
class PdosDataset:
    folder: Path
    data: projwfc.PdosData
    fermi_scf: float | None
    fermi_nscf: float | None
    warnings: list[str] = field(default_factory=list)
    # Fixed magnetization: one Fermi energy per spin channel (↑, ↓) of each run.
    channels_scf: tuple[float, float] | None = None
    channels_nscf: tuple[float, float] | None = None
    magnetization: float | None = None  # total, μB/cell

    def _use_nscf(self, source: str) -> bool:
        if source == "nscf" and self.fermi_nscf is not None:
            return True
        return self.fermi_scf is None

    def fermi(self, source: str) -> float | None:
        return self.fermi_nscf if self._use_nscf(source) else self.fermi_scf

    def fermi_channels(self, source: str) -> tuple[float, float] | None:
        """E_F of the ↑ and ↓ channels of the run ``fermi(source)`` reads, if it printed two."""
        return self.channels_nscf if self._use_nscf(source) else self.channels_scf


def load_dataset(result: DetectionResult, sniff: SniffFn) -> PdosDataset:
    tot = result.file("pdos_tot")
    try:
        data = projwfc.load_pdos(result.files.get("pdos_atm", []), tot)
    except (OSError, ValueError) as exc:
        raise LoadError(f"Não foi possível ler a PDOS: {exc}") from exc

    def pw_of(role: str) -> PwOutput | None:
        path = result.file(role)
        return sniff(path).pw if path else None

    scf, nscf = pw_of("scf_out"), pw_of("nscf_out")
    magnetization = next(
        (pw.total_magnetization for pw in (scf, nscf) if pw and pw.total_magnetization is not None),
        None,
    )
    dataset = PdosDataset(
        result.folder,
        data,
        scf.fermi if scf else None,
        nscf.fermi if nscf else None,
        list(dict.fromkeys([*result.warnings, *data.warnings])),
        channels_scf=scf.fermi_up_down if scf else None,
        channels_nscf=nscf.fermi_up_down if nscf else None,
        magnetization=magnetization,
    )
    if dataset.fermi("scf") is None:
        dataset.warnings.append("energia de Fermi não encontrada: energias absolutas")
    return dataset
