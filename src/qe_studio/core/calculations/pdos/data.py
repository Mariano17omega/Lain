"""PDOS dataset: the projections of projwfc.x plus the Fermi energies of the SCF / NSCF runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ....i18n import _
from ...project.compounds import Compound, GeometryDrift, compound_of
from ...qe import projwfc
from ...qe.pw_output import PwOutput
from ...qe.structure import Site, read_sites
from ..base import DetectionResult, LoadError, SniffFn
from .gap import GapInfo, pdos_gap, pdos_midgap, printed_pair


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
    homo_lumo: tuple[float, float] | None = None  # printed by the NSCF, else SCF (gap method)
    sites: tuple[
        Site, ...
    ] = ()  # atoms of the SCF / NSCF header, in input order (empty: unreadable)
    compound: Compound | None = None  # who they are, for the saved atom selection
    # The saved selection in force was chosen with other positions (spec 27-6): set from the store
    # when the session is built (``atoms.stored_params``; the loader has no store), cleared on save.
    selection_drift: GeometryDrift | None = None
    proven_midgap: float | None = None  # only of a proven insulator (``pdos_midgap``)
    # What each run printed as ``fermi``: "fermi", "homo", "homo_lumo", "spin_fermi".
    kind_scf: str | None = None
    kind_nscf: str | None = None

    def _use_nscf(self, source: str) -> bool:
        if source == "nscf" and self.fermi_nscf is not None:
            return True
        return self.fermi_scf is None

    def fermi(self, source: str) -> float | None:
        return self.fermi_nscf if self._use_nscf(source) else self.fermi_scf

    def fermi_kind(self, source: str) -> str | None:
        """What the number ``fermi(source)`` is, as pw.x printed it."""
        return self.kind_nscf if self._use_nscf(source) else self.kind_scf

    def fermi_level(self, source: str) -> float | None:
        """E_F as the plots use it (spec 91): the middle of the gap of an insulator, else what the
        run ``fermi(source)`` reads printed; a run with one E_F per channel keeps them."""
        printed = self.fermi(source)
        if printed is None or self.proven_midgap is None or self.fermi_channels(source) is not None:
            return printed
        return self.proven_midgap

    def fermi_channels(self, source: str) -> tuple[float, float] | None:
        """E_F of the ↑ and ↓ channels of the run ``fermi(source)`` reads, if it printed two."""
        return self.channels_nscf if self._use_nscf(source) else self.channels_scf


def _listed_states(path: Path | None) -> set[tuple[int, int]] | None:
    """The projections projwfc.x says it wrote (None: no output, or it lists none)."""
    if path is None:
        return None
    try:
        return projwfc.read_projwfc_states(path) or None
    except OSError:
        return None


def _spin_note(data: projwfc.PdosData, result: DetectionResult, sniff: SniffFn) -> list[str]:
    """Noncollinear without spin-orbit: the ``up``/``dw`` columns are the two components of the spinor
    (``QE:PP/src/partialdos.f90:513-517``), not spin channels of their own (L-12). With spin-orbit
    the files hold one column and ``_j`` in the name."""
    if not data.spin_polarized:
        return []
    for role in ("scf_out", "nscf_out"):
        path = result.file(role)
        if path is not None and (pw := sniff(path).pw) is not None and pw.noncollinear:
            return [
                _(
                    "cálculo não colinear sem spin-órbita: ↑ e ↓ são as componentes do spinor ao longo de z, não canais de spin independentes"
                )
            ]
    return []


def load_dataset(result: DetectionResult, sniff: SniffFn) -> PdosDataset:
    tot = result.file("pdos_tot")
    try:
        data = projwfc.load_pdos(result.files.get("pdos_atm", []), tot)
    except (OSError, ValueError) as exc:
        raise LoadError(_("Não foi possível ler a PDOS: {exc}").format(exc=exc)) from exc
    listed = _listed_states(result.file("projwfc_out"))
    warnings = [
        *projwfc.completeness_warnings(data.series, listed),
        *_spin_note(data, result, sniff),
    ]

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
        list(dict.fromkeys([*result.warnings, *data.warnings, *warnings])),
        channels_scf=scf.fermi_up_down if scf else None,
        channels_nscf=nscf.fermi_up_down if nscf else None,
        magnetization=magnetization,
        gap=pdos_gap(scf, nscf, data),
        homo_lumo=printed_pair(scf, nscf),
        sites=sites,
        compound=compound_of(sites),
        proven_midgap=pdos_midgap(scf, nscf, data),
        kind_scf=scf.fermi_kind if scf else None,
        kind_nscf=nscf.fermi_kind if nscf else None,
    )
    if dataset.fermi("scf") is None:
        dataset.warnings.append(_("energia de Fermi não encontrada: energias absolutas"))
    return dataset
