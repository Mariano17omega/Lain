"""What every QE parser shares: the Bohr radius and Fortran's way of writing a number."""

from __future__ import annotations

BOHR_TO_ANGSTROM = 0.529177210903  # QE's bohr_radius_angs (CODATA 2018)


def number(text: str) -> float:
    """``1.5D-3`` as a float; ``ValueError`` when it is not a number."""
    return float(text.replace("D", "E").replace("d", "e"))
