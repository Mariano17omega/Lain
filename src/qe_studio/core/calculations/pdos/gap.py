"""The energy gap of a PDOS (spec 20): the HOMO / LUMO pw.x printed, else the one in the DOS curve;
or the one of the method the user picked (spec 34)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ...qe import projwfc
from ...qe.pw_output import PwOutput
from ..bands.gap import WINDOW_GAP_MIN_EV, method_note, printed_gap
from ..params import gap_method_in_force
from .params import reference

if TYPE_CHECKING:
    from .data import PdosDataset
    from .params import PdosParams

# What it takes to move E_F to the middle of a gap read off the DOS (spec 91), on top of the
# relative threshold of ``projwfc.empty_regions``, which a sharp semicore peak can fool:
# how far (eV) above a level the empty region may start (the broadened edge of the valence), and
# the DOS (states/eV) its deepest point must reach, where the tails of a real gap have died out.
TAIL_EV = 0.25
EMPTY_DOS = 1e-2
WHOLE_COUNT_TOL = 1e-6  # a count of electrons this close to a whole number is one


@dataclass(frozen=True)
class GapInfo:
    """``homo_lumo``: exact, printed by pw.x (fixed occupations). ``dos``: read off the curve."""

    value: float
    source: Literal["homo_lumo", "dos"]


@dataclass(frozen=True)
class ProvenGap:
    """The gap of a proven insulator: printed by pw.x (``homo_lumo``) or read off the DOS (``dos``)."""

    low: float
    high: float
    source: Literal["homo_lumo", "dos"]

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def middle(self) -> float:
        return (self.low + self.high) / 2


def printed_pair(scf: PwOutput | None, nscf: PwOutput | None) -> tuple[float, float] | None:
    """The HOMO / LUMO pair of the NSCF run, else of the SCF one (the NSCF grid is the one projwfc.x
    projected)."""
    return next((pw.homo_lumo for pw in (nscf, scf) if pw is not None and pw.homo_lumo), None)


def _fills_whole_bands(pw: PwOutput) -> bool:
    """Can the electron count of ``pw`` fill whole bands? No count has no objection to make."""
    if pw.n_electrons is None:
        return True
    per_band = pw.n_electrons if pw.spin_polarized or pw.noncollinear else pw.n_electrons / 2
    return abs(per_band - round(per_band)) <= WHOLE_COUNT_TOL


def _regions(data: projwfc.PdosData) -> list[projwfc.EmptyRegion]:
    """The empty regions of the total DOS that are empty in absolute terms too."""
    if data.total is None:
        return []
    regions = projwfc.empty_regions(data.energy, data.total)
    return [region for region in regions if region.floor <= EMPTY_DOS]


def _within_tail(region: projwfc.EmptyRegion | None, level: float) -> bool:
    """Does ``region`` start at most a broadened band edge above ``level`` (or hold it)?"""
    return region is not None and region.first - level <= TAIL_EV


def _from_pair(
    pair: tuple[float, float], nscf: PwOutput | None, data: projwfc.PdosData
) -> ProvenGap | None:
    """The gap a printed pair proves. A pair of the SCF while an NSCF was projected comes from
    another grid (a coarse one can miss the CBM), so the curve drawn has the last word."""
    if printed_gap(pair) is None:
        return None
    printed = ProvenGap(pair[0], pair[1], "homo_lumo")
    if nscf is None or nscf.homo_lumo is not None or data.total is None:
        return printed
    regions = _regions(data)
    if any(region.low <= printed.middle <= region.high for region in regions):
        return printed
    above = projwfc.region_above(regions, pair[0])
    if above is None or not _within_tail(above, pair[0]):
        return None
    return ProvenGap(above.low, above.high, "dos")


def proven_gap(
    scf: PwOutput | None, nscf: PwOutput | None, data: projwfc.PdosData
) -> ProvenGap | None:
    """The gap of an insulator, the one E_F sits in the middle of (spec 91), or None.

    A printed pair that opens proves it (``_from_pair``). Without one, each run is read by itself,
    the NSCF first (its grid is the one projwfc.x projected). Fixed occupations without a LUMO prove
    the empty region just above the HOMO; smearing, an E_F inside an empty region when the electron
    count can fill whole bands. An NSCF E_F inside a band, further from the region than a broadened
    edge explains, says the system is a metal, and the SCF is not asked. A run with one E_F per
    channel says nothing.

    Stricter than the reading of the legend when there is no verdict (``pdos_gap``), which takes a
    region up to ``GAP_SEARCH_EV`` from E_F: that only labels a gap, and this moves E_F.
    """
    if (pair := printed_pair(scf, nscf)) is not None:
        return _from_pair(pair, nscf, data)
    regions = _regions(data)
    for pw in (nscf, scf):
        if pw is None or pw.fermi is None or pw.fermi_up_down is not None:
            continue
        above = projwfc.region_above(regions, pw.fermi)
        reach = _within_tail(above, pw.fermi)
        if pw.fermi_kind == "homo":
            proof = reach
        else:
            inside = above is not None and above.low <= pw.fermi
            proof = inside and _fills_whole_bands(pw)
        if proof and above is not None:
            return ProvenGap(above.low, above.high, "dos")
        if pw is nscf and not reach:
            return None
    return None


def pdos_midgap(
    scf: PwOutput | None, nscf: PwOutput | None, data: projwfc.PdosData
) -> float | None:
    """The middle of the gap of an insulator, where the plot puts E_F (spec 91), or None."""
    proven = proven_gap(scf, nscf, data)
    return None if proven is None else proven.middle


def pdos_gap(scf: PwOutput | None, nscf: PwOutput | None, data: projwfc.PdosData) -> GapInfo | None:
    """The gap of the system, never of a selection of atoms (``data.total`` has all of them).

    The gap E_F was placed in, when the system is a proven insulator (``proven_gap``), so that the
    legend and the Fermi line speak of one gap. Otherwise pw.x's single HOMO / LUMO pair (the NSCF
    comes first, its grid is the one projwfc.x projected); a printed pair that does not open a gap
    says the system is a metal, and the curve is not asked.
    """
    if (proven := proven_gap(scf, nscf, data)) is not None:
        return GapInfo(proven.width, proven.source)
    if (pair := printed_pair(scf, nscf)) is not None:
        value = printed_gap(pair)
        return None if value is None else GapInfo(value, "homo_lumo")
    fermi = next((pw.fermi for pw in (nscf, scf) if pw is not None and pw.fermi is not None), None)
    if data.total is None:
        return None
    value = projwfc.dos_gap(data.energy, data.total, fermi)
    return None if value is None else GapInfo(value, "dos")


def gap_for(dataset: PdosDataset, params: PdosParams) -> GapInfo | None:
    """The gap by the method in force: ``auto`` is ``dataset.gap`` (found by the loader),
    ``homo_lumo`` the printed pair, ``janela`` the widest empty region of the total DOS inside the
    plot's energy window. Always the system's total, never the atoms chosen (spec 21)."""
    method = gap_method_in_force(params)
    if method == "homo_lumo":
        value = printed_gap(dataset.homo_lumo)
        return None if value is None else GapInfo(value, "homo_lumo")
    if method == "janela":
        total = dataset.data.total
        if total is None:
            return None
        ref = reference(dataset, params)
        low, high = ref + params.emin, ref + params.emax
        value = projwfc.dos_gap_window(dataset.data.energy, total, low, high, WINDOW_GAP_MIN_EV)
        return None if value is None else GapInfo(value, "dos")
    return dataset.gap


def gap_notes(dataset: PdosDataset, params: PdosParams) -> tuple[str, ...]:
    """Why the gap of ``homo_lumo`` or ``janela`` is missing from a visible legend (``auto`` keeps
    saying nothing, as before spec 34)."""
    if not (params.legend_gap and params.show_legend) or gap_for(dataset, params) is not None:
        return ()
    return method_note(gap_method_in_force(params), dataset.homo_lumo)
