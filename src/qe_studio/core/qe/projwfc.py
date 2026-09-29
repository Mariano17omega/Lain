"""projwfc.x projected DOS files.

``<filpdos>.pdos_atm#N(El)_wfc#k(l)`` hold, after the energy column, the ``ldos`` (sum over m)
followed by one ``pdos`` column per m; only ``ldos`` is used. ``<filpdos>.pdos_tot`` holds
``dos`` then ``pdos``. Spin-polarized runs split every column into ``up``/``dw``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ATM_PATTERN = re.compile(
    r"^(?P<prefix>.*?)\.?pdos_atm#(?P<atom>\d+)\((?P<species>[^)]+)\)"
    r"_wfc#(?P<wfc>\d+)\((?P<l>[spdf])(?:_j(?P<j>\d+(?:\.\d+)?))?\)$"
)
TOT_PATTERN = re.compile(r"^(?P<prefix>.*?)\.?pdos_tot$")
ORBITAL_ORDER = "spdf"


class PdosFormatError(ValueError):
    pass


@dataclass(frozen=True)
class AtmFileName:
    prefix: str
    atom: int
    species: str
    wfc: int
    l: str  # noqa: E741 - physics notation
    j: float | None


def parse_atm_name(name: str) -> AtmFileName | None:
    match = ATM_PATTERN.match(name)
    if not match:
        return None
    j = match.group("j")
    return AtmFileName(
        match.group("prefix"),
        int(match.group("atom")),
        match.group("species").strip(),
        int(match.group("wfc")),
        match.group("l"),
        float(j) if j else None,
    )


def is_pdos_tot_name(name: str) -> bool:
    return TOT_PATTERN.match(name) is not None


def header_columns(header: str) -> list[str]:
    """Column names after the energy column, e.g. ``['ldos', 'pdos', 'pdos']``.

    Raises for k-resolved files (``# ik E (eV) ...``), which the MVP does not plot.
    """
    if not header.lstrip().startswith("#"):
        raise PdosFormatError("cabeçalho '#' ausente")
    if re.search(r"\bik\b", header):
        raise PdosFormatError("PDOS resolvida em k (kresolveddos) não é suportada")
    return re.findall(r"(\w+)\(E\)", header)


@dataclass(frozen=True)
class Channel:
    up: np.ndarray = field(repr=False)
    down: np.ndarray | None = field(default=None, repr=False)

    def __add__(self, other: Channel) -> Channel:
        down = None
        if self.down is not None or other.down is not None:
            down = _zero_if_none(self.down, self.up) + _zero_if_none(other.down, other.up)
        return Channel(self.up + other.up, down)


def _zero_if_none(values: np.ndarray | None, like: np.ndarray) -> np.ndarray:
    return np.zeros_like(like) if values is None else values


def read_pdos_file(path: Path, total: bool = False) -> tuple[np.ndarray, Channel]:
    """Energy grid and the summed channel (``ldos`` / ``dos`` or their up/dw pair)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        header = handle.readline()
    names = header_columns(header)
    base = "dos" if total else "ldos"
    if f"{base}up" in names and f"{base}dw" in names:
        cols = (names.index(f"{base}up") + 1, names.index(f"{base}dw") + 1)
    elif base in names:
        cols = (names.index(base) + 1,)
    elif names:
        cols = (1,)
    else:
        raise PdosFormatError(f"colunas não reconhecidas em {path.name}")
    data = np.loadtxt(path, skiprows=1, usecols=(0, *cols), ndmin=2)
    if data.shape[0] == 0:
        raise PdosFormatError(f"{path.name} sem dados")
    energy = data[:, 0]
    channel = Channel(data[:, 1], data[:, 2] if len(cols) == 2 else None)
    return energy, channel


@dataclass(frozen=True)
class PdosSeries:
    atom: int
    species: str
    wfc: int
    l: str  # noqa: E741
    j: float | None
    channel: Channel


@dataclass(frozen=True)
class PdosData:
    energy: np.ndarray = field(repr=False)
    series: tuple[PdosSeries, ...]
    total: Channel | None
    total_is_sum: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def spin_polarized(self) -> bool:
        return any(s.channel.down is not None for s in self.series)

    @property
    def species(self) -> list[str]:
        return list(dict.fromkeys(s.species for s in sorted(self.series, key=lambda s: s.atom)))


GROUPINGS = ("species_orbital", "species", "orbital")


def _group_key(series: PdosSeries, grouping: str) -> tuple[str, str]:
    if grouping == "species_orbital":
        return series.species, series.l
    if grouping == "species":
        return series.species, ""
    if grouping == "orbital":
        return "", series.l
    raise ValueError(f"agrupamento desconhecido: {grouping}")


def aggregate(data: PdosData, grouping: str = "species_orbital") -> dict[tuple[str, str], Channel]:
    """Sum series into (species, orbital) groups; empty string = summed over that axis.

    Order: species by first atom index, then s, p, d, f.
    """
    species_rank = {name: i for i, name in enumerate(data.species)}
    groups: dict[tuple[str, str], Channel] = {}
    for series in data.series:
        key = _group_key(series, grouping)
        groups[key] = groups[key] + series.channel if key in groups else series.channel
    return dict(
        sorted(
            groups.items(),
            key=lambda item: (species_rank.get(item[0][0], -1), ORBITAL_ORDER.find(item[0][1])),
        )
    )


def load_pdos(atm_files: Iterable[Path], tot_file: Path | None = None) -> PdosData:
    warnings: list[str] = []
    energy: np.ndarray | None = None
    series = []
    for path in sorted(atm_files, key=lambda p: p.name):
        meta = parse_atm_name(path.name)
        if meta is None:
            continue
        grid, channel = read_pdos_file(path)
        if energy is None:
            energy = grid
        elif len(grid) != len(energy) or not np.allclose(grid, energy):
            warnings.append(f"{path.name}: grade de energia diferente, interpolada")
            channel = Channel(
                np.interp(energy, grid, channel.up),
                None if channel.down is None else np.interp(energy, grid, channel.down),
            )
        series.append(PdosSeries(meta.atom, meta.species, meta.wfc, meta.l, meta.j, channel))
    if energy is None:
        raise PdosFormatError("nenhum arquivo pdos_atm# encontrado")

    total = None
    total_is_sum = False
    if tot_file is not None:
        grid, total = read_pdos_file(tot_file, total=True)
        if len(grid) != len(energy) or not np.allclose(grid, energy):
            total = Channel(
                np.interp(energy, grid, total.up),
                None if total.down is None else np.interp(energy, grid, total.down),
            )
    else:
        total_is_sum = True
        for s in series:
            total = s.channel if total is None else total + s.channel
        warnings.append("pdos_tot ausente: total = soma das projeções")
    return PdosData(energy, tuple(series), total, total_is_sum, tuple(warnings))
