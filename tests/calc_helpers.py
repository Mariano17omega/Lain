"""Shared pieces of the "Criar cálculo" backend tests (spec 25)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from qe_studio.core.calc_create.kpath import KPath, KPoint
from qe_studio.core.calc_create.scf_info import ScfInfo, read_scf, scf_info
from qe_studio.core.config import JobsConfig
from qe_studio.core.qe.lattice import BOHR_ANGSTROM

from conftest import FIXTURES

JOBS = JobsConfig()
AL_SCF = FIXTURES / "al_bands" / "al.scf.in"
NI_SCF = FIXTURES / "qe731_ni_spin_bands" / "ni.scf.in"
SI_SCF = FIXTURES / "si_bands" / "si.scf.in"
RUN = re.compile(r'-i "([^"]+)" > "([^"]+)"')

# The path of tests/fixtures/al_bands/al.band.in (L G X U G, weights 20 30 10 30 20).
AL_PATH = KPath(
    (
        KPoint("L", (0.0, 0.5, 0.0), 20),
        KPoint("Gamma", (0.0, 0.0, 0.0), 30),
        KPoint("X", (-0.5, 0.0, -0.5), 10),
        KPoint("U", (-0.375, 0.25, -0.375), 30),
        KPoint("Gamma", (0.0, 0.0, 0.0), 20),
    )
)


def hex_cell(a: float = 3.16, c_over_a: float = 6.33) -> np.ndarray:
    """A 2D-like hexagonal cell (rows in Å): the A–L segment is 7× the Γ–A one."""
    return np.array([[a, 0, 0], [-a / 2, a * 3**0.5 / 2, 0], [0, 0, a * c_over_a]])


def hex_path(npts: int = 20) -> KPath:
    """Γ-M-K-Γ-A-L-H-A in the reciprocal vectors of ``hex_cell``, ``npts`` to every next point."""
    points = [
        ("Gamma", (0, 0, 0)),
        ("M", (0.5, 0, 0)),
        ("K", (1 / 3, 1 / 3, 0)),
        ("Gamma", (0, 0, 0)),
        ("A", (0, 0, 0.5)),
        ("L", (0.5, 0, 0.5)),
        ("H", (1 / 3, 1 / 3, 0.5)),
        ("A", (0, 0, 0.5)),
    ]
    return KPath(tuple(KPoint(label, frac, npts) for label, frac in points))


def hex_scf_text(a: float = 3.16, c_over_a: float = 6.33) -> str:
    """The Al SCF with ibrav = 4: its cell is ``hex_cell(a, c_over_a)``."""
    return (
        AL_SCF.read_text()
        .replace("ibrav=  2,", "ibrav=  4,")
        .replace(
            "celldm(1)=  7.630781648,",
            f"celldm(1)= {a / BOHR_ANGSTROM:.9f},\n    celldm(3)= {c_over_a},",
        )
    )


def hex_scf() -> ScfInfo:
    return scf_info(hex_scf_text(), Path("scf.in"))


def al() -> ScfInfo:
    return read_scf(AL_SCF)


def ni() -> ScfInfo:
    return read_scf(NI_SCF)


def from_text(text: str, name: str = "scf.in") -> ScfInfo:
    return scf_info(text, Path(name))


def runs(script: str) -> list[str]:
    """The inputs a script runs, in order."""
    return [match.group(1) for match in RUN.finditer(script)]
