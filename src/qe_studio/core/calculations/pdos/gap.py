"""The energy gap of a PDOS (spec 20): the HOMO / LUMO pw.x printed, else the one in the DOS curve."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...qe import projwfc
from ...qe.pw_output import PwOutput
from ..bands.data import EDGE_TOL


@dataclass(frozen=True)
class GapInfo:
    """``homo_lumo``: exact, printed by pw.x (fixed occupations). ``dos``: read off the curve."""

    value: float
    source: Literal["homo_lumo", "dos"]


def pdos_gap(scf: PwOutput | None, nscf: PwOutput | None, data: projwfc.PdosData) -> GapInfo | None:
    """The gap of the system, never of a selection of atoms (``data.total`` has all of them).

    pw.x prints one HOMO / LUMO pair for both spin channels, so there is a single gap. The NSCF run
    comes first (its grid is the one projwfc.x projected); a printed pair that does not open a gap
    says the system is a metal, and the curve is not asked.
    """
    runs = [pw for pw in (nscf, scf) if pw is not None]
    for pw in runs:
        if pw.fermi_kind == "homo_lumo" and pw.fermi is not None and pw.lumo is not None:
            gap = pw.lumo - pw.fermi
            return GapInfo(gap, "homo_lumo") if gap > EDGE_TOL else None
    fermi = next((pw.fermi for pw in runs if pw.fermi is not None), None)
    if data.total is None:
        return None
    value = projwfc.dos_gap(data.energy, data.total, fermi)
    return None if value is None else GapInfo(value, "dos")
