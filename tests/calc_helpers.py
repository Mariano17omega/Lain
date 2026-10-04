"""Shared pieces of the "Criar cálculo" backend tests (spec 25)."""

from __future__ import annotations

import re
from pathlib import Path

from qe_studio.core.calc_create.kpath import KPath, KPoint
from qe_studio.core.calc_create.scf_info import ScfInfo, read_scf, scf_info
from qe_studio.core.config import JobsConfig

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


def al() -> ScfInfo:
    return read_scf(AL_SCF)


def ni() -> ScfInfo:
    return read_scf(NI_SCF)


def from_text(text: str, name: str = "scf.in") -> ScfInfo:
    return scf_info(text, Path(name))


def runs(script: str) -> list[str]:
    """The inputs a script runs, in order."""
    return [match.group(1) for match in RUN.finditer(script)]
