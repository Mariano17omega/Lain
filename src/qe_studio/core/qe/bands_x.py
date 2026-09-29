"""bands.x products: ``<filband>.gnu``, the ``<filband>`` data file and bands.x stdout."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np


class BandsFormatError(ValueError):
    pass


@dataclass(frozen=True)
class BandData:
    """Eigenvalues along a path: ``energies[band, k]`` in eV (absolute), ``x[k]`` path length."""

    x: np.ndarray = field(repr=False)
    energies: np.ndarray = field(repr=False)

    @property
    def n_bands(self) -> int:
        return self.energies.shape[0]

    @property
    def n_kpoints(self) -> int:
        return self.energies.shape[1]


def read_gnu(text: str) -> BandData:
    """Parse ``<filband>.gnu``: one (x, E) block per band, x restarting at 0 for each band.

    Block separators differ between QE versions (empty line in 7.3, a single space in 7.1),
    so bands are split where x decreases instead of on blank lines.
    """
    try:
        data = np.loadtxt(io.StringIO(text), ndmin=2)
    except ValueError as exc:
        raise BandsFormatError(f"não é um arquivo de bandas numérico: {exc}") from exc
    if data.size == 0 or data.shape[1] != 2:
        raise BandsFormatError("esperadas 2 colunas (x, E)")
    starts = np.flatnonzero(np.diff(data[:, 0]) < 0) + 1
    blocks = np.split(data, starts)
    nks = len(blocks[0])
    if any(len(block) != nks for block in blocks):
        raise BandsFormatError("bandas com números diferentes de pontos k")
    x = blocks[0][:, 0]
    if not all(np.allclose(block[:, 0], x, atol=1e-3) for block in blocks[1:]):
        raise BandsFormatError("eixo x difere entre bandas")
    return BandData(x, np.array([block[:, 1] for block in blocks]))


_FLOATS = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")
_PLOT_HEADER = re.compile(r"&plot\s+nbnd=\s*(\d+)\s*,\s*nks=\s*(\d+)\s*/", re.I)


@dataclass(frozen=True)
class FilbandData:
    kpoints: np.ndarray = field(repr=False)  # (nks, 3) Cartesian, units 2π/alat
    energies: np.ndarray = field(repr=False)  # (nbnd, nks) eV

    def to_band_data(self) -> BandData:
        return BandData(path_coordinates(self.kpoints), self.energies)


def read_filband_header(text: str) -> tuple[int, int] | None:
    match = _PLOT_HEADER.search(text[:200])
    return (int(match.group(1)), int(match.group(2))) if match else None


def read_filband(text: str) -> FilbandData:
    """Parse the raw ``filband`` file: header, then per k-point 3 coordinates + nbnd energies.

    Fields are fixed-width Fortran and may touch (``-116.798-116.798``), so floats are taken
    by regex rather than whitespace splitting.
    """
    header = read_filband_header(text)
    if header is None:
        raise BandsFormatError("cabeçalho &plot ausente")
    nbnd, nks = header
    values = np.array([float(v) for v in _FLOATS.findall(text[text.index("/") + 1 :])])
    if values.size < nks * (3 + nbnd):
        raise BandsFormatError(f"esperados {nks} pontos k com {nbnd} bandas")
    rows = values[: nks * (3 + nbnd)].reshape(nks, 3 + nbnd)
    return FilbandData(rows[:, :3], rows[:, 3:].T.copy())


def path_coordinates(kpoints: np.ndarray) -> np.ndarray:
    """Cumulative path length exactly as bands.x computes it (PP/src/bands.f90).

    A step more than 5× the previous regular step is a jump between disconnected segments
    and does not advance x.
    """
    nks = len(kpoints)
    x = np.zeros(nks)
    if nks < 2:
        return x
    steps = np.linalg.norm(np.diff(kpoints, axis=0), axis=1)
    typical = steps[0]
    for n in range(1, nks):
        step = steps[n - 1]
        if step > 5 * typical:
            x[n] = x[n - 1]
        else:
            x[n] = x[n - 1] + step
            if step > 1e-4:
                typical = step
    return x


_HS_LINE = re.compile(r"high-symmetry point:(.*?)x coordinate\s+(-?\d+\.\d+)")
_GNU_FILE = re.compile(r"Plottable bands \(eV\) written to file\s+(\S+)")
_FILBAND_FILE = re.compile(r"Bands written to file\s+(\S+)")


@dataclass(frozen=True)
class BandsXOutput:
    hs_x: tuple[float, ...] = ()
    hs_kpoints: tuple[tuple[float, ...], ...] = ()
    gnu_name: str | None = None
    filband_name: str | None = None
    job_done: bool = False


def _clean_name(name: str) -> str:
    return name.removeprefix("./")


def parse_bandsx_output(text: str) -> BandsXOutput:
    """bands.x stdout. Coordinates are ``3f7.4`` and may run together (``-0.5002-0.2867``)."""
    hs_x, hs_k = [], []
    for match in _HS_LINE.finditer(text):
        hs_x.append(float(match.group(2)))
        hs_k.append(tuple(float(v) for v in _FLOATS.findall(match.group(1))))
    gnu = _GNU_FILE.search(text)
    filband = _FILBAND_FILE.search(text)
    return BandsXOutput(
        tuple(hs_x),
        tuple(hs_k),
        _clean_name(gnu.group(1)) if gnu else None,
        _clean_name(filband.group(1)) if filband else None,
        "JOB DONE" in text,
    )
