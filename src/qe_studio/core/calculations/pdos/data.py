"""PDOS dataset: the projections of projwfc.x plus the Fermi energies of the SCF / NSCF runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...compounds import Compound, GeometryDrift, compound_of
from ...qe import projwfc
from ...qe.pw_output import PwOutput
from ...qe.structure import Site, read_sites
from ..base import DetectionResult, LoadError, SniffFn
from .gap import GapInfo, pdos_gap


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
    gap: GapInfo | None = None  # of the system, not of what is drawn
    sites: tuple[
        Site, ...
    ] = ()  # atoms of the SCF / NSCF header, in input order (empty: unreadable)
    compound: Compound | None = None  # who they are, for the saved atom selection
    # The saved selection in force was chosen with other positions (spec 27-6): set from the store
    # when the session is built (``atoms.stored_params``; the loader has no store), cleared on save.
    selection_drift: GeometryDrift | None = None

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
    sites: tuple[Site, ...] = ()
    for role in ("scf_out", "nscf_out"):
        if (path := result.file(role)) and (found := read_sites(path)):
            sites = tuple(found)
            break
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
        gap=pdos_gap(scf, nscf, data),
        sites=sites,
        compound=compound_of(sites),
    )
    if dataset.fermi("scf") is None:
        dataset.warnings.append("energia de Fermi não encontrada: energias absolutas")
    return dataset
