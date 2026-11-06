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


@dataclass(frozen=True)
class GapInfo:
    """``homo_lumo``: exact, printed by pw.x (fixed occupations). ``dos``: read off the curve."""

    value: float
    source: Literal["homo_lumo", "dos"]


def printed_pair(scf: PwOutput | None, nscf: PwOutput | None) -> tuple[float, float] | None:
    """The HOMO / LUMO pair of the NSCF run, else of the SCF one (the NSCF grid is the one projwfc.x
    projected)."""
    return next((pw.homo_lumo for pw in (nscf, scf) if pw is not None and pw.homo_lumo), None)


def pdos_gap(scf: PwOutput | None, nscf: PwOutput | None, data: projwfc.PdosData) -> GapInfo | None:
    """The gap of the system, never of a selection of atoms (``data.total`` has all of them).

    pw.x prints one HOMO / LUMO pair for both spin channels, so there is a single gap. The NSCF run
    comes first (its grid is the one projwfc.x projected); a printed pair that does not open a gap
    says the system is a metal, and the curve is not asked.
    """
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
