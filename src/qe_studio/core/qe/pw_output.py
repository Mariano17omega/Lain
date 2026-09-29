"""pw.x standard output.

Scalars are read with regexes (last match wins) instead of ASE: ASE's ``espresso-out``
reader crashes on QE ≥ 7 outputs whose input had no ATOMIC_POSITIONS units (it mistakes the
``ATOMIC_POSITIONS: units set to alat`` notice for a positions block) and returns no k-points
when pw.x did not print eigenvalues. ASE is still used for the crystal structure, on text with
those notice lines removed.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Literal

FermiKind = Literal["fermi", "spin_fermi", "homo_lumo", "homo"]

_FLOAT = r"(-?\d+\.\d+)"
_FERMI_PATTERNS: list[tuple[FermiKind, re.Pattern[str]]] = [
    ("fermi", re.compile(rf"the Fermi energy is\s+{_FLOAT}\s*ev", re.I)),
    (
        "spin_fermi",
        re.compile(rf"the spin up/dw Fermi energies are\s+{_FLOAT}\s+{_FLOAT}\s*ev", re.I),
    ),
    (
        "homo_lumo",
        re.compile(
            rf"highest occupied, lowest unoccupied level \(ev\):\s+{_FLOAT}\s+{_FLOAT}", re.I
        ),
    ),
    ("homo", re.compile(rf"highest occupied level \(ev\):\s+{_FLOAT}", re.I)),
]
_VERSION = re.compile(r"Program PWSCF\s+v\.?\s*(\S+)")
_NKS = re.compile(r"number of k points=\s*(\d+)")
_NELEC = re.compile(r"number of electrons\s*=\s*(-?\d+\.?\d*)")
_NBND = re.compile(r"number of Kohn-Sham states=\s*(\d+)")
_ALAT = re.compile(r"lattice parameter \(alat\)\s*=\s*(-?\d+\.\d+)")


@dataclass(frozen=True)
class PwOutput:
    version: str | None = None
    calculation: str | None = None  # scf | nscf | bands | relax | vc-relax | None
    fermi: float | None = None  # reference energy in eV (E_F, or HOMO for fixed occupations)
    fermi_kind: FermiKind | None = None
    lumo: float | None = None
    fermi_up_down: tuple[float, float] | None = None
    n_kpoints: int | None = None
    n_electrons: float | None = None
    n_bands: int | None = None
    alat_bohr: float | None = None
    spin_polarized: bool = False
    noncollinear: bool = False
    job_done: bool = False
    converged: bool | None = None

    @property
    def warnings(self) -> list[str]:
        out = []
        if not self.job_done:
            out.append("execução incompleta (sem JOB DONE)")
        if self.converged is False:
            out.append("SCF não convergiu")
        if self.fermi_kind == "spin_fermi":
            out.append("duas energias de Fermi (up/dw); usando a média")
        return out


def _last(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    match = None
    for match in pattern.finditer(text):  # noqa: B007 - keep the last one
        pass
    return match


def _calculation(text: str, has_fermi: bool) -> str | None:
    if "Final enthalpy" in text or "new unit-cell volume" in text:
        return "vc-relax"
    if "number of bfgs steps" in text or "Begin final coordinates" in text:
        return "relax"
    non_scf = "End of band structure calculation" in text or "Band Structure Calculation" in text
    if non_scf:
        return "nscf" if has_fermi else "bands"
    if "End of self-consistent calculation" in text or "Self-consistent Calculation" in text:
        return "scf"
    return None


def _spin_polarized(text: str) -> bool:
    if "Noncollinear calculation" in text:
        return False
    markers = ("Starting magnetic structure", "SPIN UP", "total magnetization")
    return any(marker in text for marker in markers)


def parse_pw_output(text: str) -> PwOutput:
    best: tuple[int, FermiKind, re.Match[str]] | None = None
    for kind, pattern in _FERMI_PATTERNS:
        match = _last(pattern, text)
        if match and (best is None or match.start() > best[0]):
            best = (match.start(), kind, match)

    fermi = lumo = None
    fermi_kind: FermiKind | None = None
    up_down = None
    if best:
        _, fermi_kind, match = best
        values = [float(v) for v in match.groups()]
        if fermi_kind == "spin_fermi":
            up_down = (values[0], values[1])
            fermi = sum(values) / 2
        else:
            fermi = values[0]
            if fermi_kind == "homo_lumo":
                lumo = values[1]

    def first_int(pattern: re.Pattern[str]) -> int | None:
        match = pattern.search(text)
        return int(match.group(1)) if match else None

    nelec = _NELEC.search(text)
    alat = _ALAT.search(text)
    version = _VERSION.search(text)
    converged = None
    if "convergence NOT achieved" in text:
        converged = False
    elif "convergence has been achieved" in text:
        converged = True

    return PwOutput(
        version=version.group(1) if version else None,
        calculation=_calculation(text, best is not None),
        fermi=fermi,
        fermi_kind=fermi_kind,
        lumo=lumo,
        fermi_up_down=up_down,
        n_kpoints=first_int(_NKS),
        n_electrons=float(nelec.group(1)) if nelec else None,
        n_bands=first_int(_NBND),
        alat_bohr=float(alat.group(1)) if alat else None,
        spin_polarized=_spin_polarized(text),
        noncollinear="Noncollinear calculation" in text,
        job_done="JOB DONE" in text,
        converged=converged,
    )


def read_structure(text: str):
    """Final structure as ``ase.Atoms`` or None if ASE cannot parse the output."""
    from ase.io.espresso import read_espresso_out

    # Real cards start at column 0; indented mentions are notices ASE would misread.
    lines = [
        line
        for line in text.splitlines(keepends=True)
        if "ATOMIC_POSITIONS" not in line or line.startswith("ATOMIC_POSITIONS")
    ]
    try:
        return next(read_espresso_out(io.StringIO("".join(lines)), index=slice(-1, None)))
    except Exception:  # ASE raises many exception types on partial/odd outputs
        return None
