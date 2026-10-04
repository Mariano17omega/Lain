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

_NUMBER = r"-?\d+\.\d+"
# The four ways pw.x prints the reference energy, as one pattern: one pass over the text, the
# last match wins. The named group that matched tells which kind it is. The phrases are matched
# as pw.x writes them (as the summary scanner does): re.I made this pass 6x slower.
_FERMI = re.compile(
    rf"the Fermi energy is\s+(?P<fermi>{_NUMBER})\s*[eE][vV]"
    rf"|the spin up/dw Fermi energies are\s+(?P<spin_up>{_NUMBER})\s+(?P<spin_dw>{_NUMBER})"
    r"\s*[eE][vV]"
    rf"|highest occupied, lowest unoccupied level \(ev\):\s+(?P<homo>{_NUMBER})"
    rf"\s+(?P<lumo>{_NUMBER})"
    rf"|highest occupied level \(ev\):\s+(?P<homo_only>{_NUMBER})"
)
_VERSION = re.compile(r"Program PWSCF\s+v\.?\s*(\S+)")
_NKS = re.compile(r"number of k points=\s*(\d+)")
_NELEC = re.compile(r"number of electrons\s*=\s*(-?\d+\.?\d*)")
# Printed with tot_magnetization (always the case for fixed occupations with nspin = 2).
_NELEC_SPIN = re.compile(
    r"number of electrons\s*=\s*\S+\s*\(up:\s*(-?\d+\.\d+),\s*down:\s*(-?\d+\.\d+)\)"
)
_NBND = re.compile(r"number of Kohn-Sham states=\s*(\d+)")
_ALAT = re.compile(r"lattice parameter \(alat\)\s*=\s*(-?\d+\.\d+)")
# One component when collinear, three (a vector) when noncollinear.
_TOTAL_MAG = re.compile(r"total magnetization\s*=\s*((?:-?\d+\.\d+\s+){1,3})Bohr mag/cell")
_ABS_MAG = re.compile(r"absolute magnetization\s*=\s*(-?\d+\.\d+)\s*Bohr mag/cell")


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
    n_electrons_up_down: tuple[float, float] | None = None  # set when tot_magnetization fixes them
    n_bands: int | None = None
    alat_bohr: float | None = None
    spin_polarized: bool = False
    noncollinear: bool = False
    # μB/cell, last SCF iteration; the total is the vector's norm when noncollinear.
    total_magnetization: float | None = None
    absolute_magnetization: float | None = None
    job_done: bool = False
    converged: bool | None = None  # of the (last) SCF
    # Of the BFGS geometry optimization (relax / vc-relax): None when no marker was read.
    geometry_converged: bool | None = None

    @property
    def warnings(self) -> list[str]:
        out = []
        if not self.job_done:
            out.append("execução incompleta (sem JOB DONE)")
        if self.converged is False:
            out.append("SCF não convergiu")
        if self.fermi_kind == "spin_fermi":
            out.append(
                "duas energias de Fermi (↑/↓): referência na média, linhas separadas no gráfico"
            )
        return out


def _last(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    match = None
    for match in pattern.finditer(text):  # noqa: B007 - keep the last one
        pass
    return match


def _has(texts: tuple[str, ...], marker: str) -> bool:
    return any(marker in text for text in texts)


def _calculation(texts: tuple[str, ...], has_fermi: bool) -> str | None:
    if _has(texts, "Final enthalpy") or _has(texts, "new unit-cell volume"):
        return "vc-relax"
    if _has(texts, "number of bfgs steps") or _has(texts, "Begin final coordinates"):
        return "relax"
    non_scf = _has(texts, "End of band structure calculation") or _has(
        texts, "Band Structure Calculation"
    )
    if non_scf:
        return "nscf" if has_fermi else "bands"
    if _has(texts, "End of self-consistent calculation") or _has(
        texts, "Self-consistent Calculation"
    ):
        return "scf"
    return None


def _magnetization(text: str) -> tuple[float | None, float | None]:
    """(total, absolute) magnetization of the last SCF iteration, in Bohr magnetons per cell."""
    total = absolute = None
    if match := _last(_TOTAL_MAG, text):
        components = [float(v) for v in match.group(1).split()]
        total = sum(v * v for v in components) ** 0.5 if len(components) == 3 else components[0]
    if match := _last(_ABS_MAG, text):
        absolute = float(match.group(1))
    return total, absolute


def _spin_polarized(texts: tuple[str, ...]) -> bool:
    if _has(texts, "Noncollinear calculation"):
        return False
    markers = ("Starting magnetic structure", "SPIN UP", "total magnetization")
    return any(_has(texts, marker) for marker in markers)


def _fermi(text: str) -> tuple[FermiKind, float, float | None, tuple[float, float] | None] | None:
    """(kind, reference energy, LUMO, (E_F↑, E_F↓)) of the last reference energy printed."""
    match = _last(_FERMI, text)
    if match is None:
        return None
    if (value := match.group("fermi")) is not None:
        return "fermi", float(value), None, None
    if (up := match.group("spin_up")) is not None:
        values = (float(up), float(match.group("spin_dw")))
        return "spin_fermi", sum(values) / 2, None, values
    if (homo := match.group("homo")) is not None:
        return "homo_lumo", float(homo), float(match.group("lumo")), None
    return "homo", float(match.group("homo_only")), None, None


def _geometry_converged(tail: str) -> bool | None:
    """Whether BFGS converged, from the last marker in ``tail`` (spec 24 R3.2). ``End of BFGS
    Geometry Optimization`` is no proof: pw.x also prints it after running out of ``nstep``."""
    converged = tail.rfind("bfgs converged")
    failed = max(
        tail.rfind("bfgs failed"),
        tail.rfind("The maximum number of steps has been reached"),
    )
    if converged < 0 and failed < 0:
        return False if "End of BFGS Geometry Optimization" in tail else None
    return converged > failed


def parse_pw_output(head: str, tail: str | None = None) -> PwOutput:
    """Facts of a pw.x output from its ``head`` and ``tail`` (spec 14 R5.2).

    What pw.x prints once at the start (version, k points, electrons, bands, alat) is read from
    the head; what it prints again as the run goes (Fermi energy, magnetization, convergence,
    ``JOB DONE``) is the last occurrence, read from the tail; markers may be in either. With
    ``tail`` None (a file read whole) both are ``head``, and each text is scanned once.
    """
    tail = head if tail is None else tail
    texts = (head,) if tail is head else (head, tail)
    fermi = _fermi(tail)

    def first_int(pattern: re.Pattern[str]) -> int | None:
        match = pattern.search(head)
        return int(match.group(1)) if match else None

    nelec = _NELEC.search(head)
    nelec_spin = _NELEC_SPIN.search(head)
    alat = _ALAT.search(head)
    version = _VERSION.search(head)
    converged = None
    if "convergence NOT achieved" in tail:
        converged = False
    elif "convergence has been achieved" in tail:
        converged = True

    total_mag, abs_mag = _magnetization(tail)
    return PwOutput(
        version=version.group(1) if version else None,
        calculation=_calculation(texts, fermi is not None),
        fermi=fermi[1] if fermi else None,
        fermi_kind=fermi[0] if fermi else None,
        lumo=fermi[2] if fermi else None,
        fermi_up_down=fermi[3] if fermi else None,
        n_kpoints=first_int(_NKS),
        n_electrons=float(nelec.group(1)) if nelec else None,
        n_electrons_up_down=(
            (float(nelec_spin.group(1)), float(nelec_spin.group(2))) if nelec_spin else None
        ),
        n_bands=first_int(_NBND),
        alat_bohr=float(alat.group(1)) if alat else None,
        spin_polarized=_spin_polarized(texts),
        noncollinear="Noncollinear calculation" in head,
        total_magnetization=total_mag,
        absolute_magnetization=abs_mag,
        job_done="JOB DONE" in tail,
        converged=converged,
        geometry_converged=_geometry_converged(tail),
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
