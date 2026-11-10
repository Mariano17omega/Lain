"""projwfc.x projected DOS files.

``<filpdos>.pdos_atm#N(El)_wfc#k(l)`` hold, after the energy column, the ``ldos`` (sum over m)
followed by one ``pdos`` column per m; only ``ldos`` is used. ``<filpdos>.pdos_tot`` holds
``dos`` then ``pdos``. Spin-polarized runs split every column into ``up``/``dw``.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ...i18n import _
from .. import cancel

ATM_PATTERN = re.compile(
    r"^(?P<prefix>.*?)\.?pdos_atm#(?P<atom>\d+)\((?P<species>[^)]+)\)"
    r"_wfc#(?P<wfc>\d+)\((?P<l>[spdf])(?:_j(?P<j>\d+(?:\.\d+)?))?\)$"
)
TOT_PATTERN = re.compile(r"^(?P<prefix>.*?)\.?pdos_tot$")
ORBITAL_ORDER = "spdf"
# The gap read off a total DOS curve (``dos_gap``). Energies below this fraction of the curve's
# maximum count as "no states": a smeared band edge has a long, faint tail that would otherwise
# close the gap. Raising it widens the tail that is ignored and shrinks the gap found.
GAP_DOS_REL_TOL = 1e-3
# How far (eV) from E_F the empty region may lie. With smearing, E_F often lands in the top of the
# valence band, a few tenths of eV below the gap; but a region further away says nothing about the
# Fermi level (a metal with a pseudogap or a semicore gap elsewhere).
GAP_SEARCH_EV = 1.0


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
        raise PdosFormatError(_("cabeçalho '#' ausente"))
    if re.search(r"\bik\b", header):
        raise PdosFormatError(_("PDOS resolvida em k (kresolveddos) não é suportada"))
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
        raise PdosFormatError(_("colunas não reconhecidas em {name}").format(name=path.name))
    data = np.loadtxt(path, skiprows=1, usecols=(0, *cols), ndmin=2)
    if data.shape[0] == 0:
        raise PdosFormatError(_("{name} sem dados").format(name=path.name))
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
    raise ValueError(_("agrupamento desconhecido: {grouping}").format(grouping=grouping))


def aggregate(
    data: PdosData, grouping: str = "species_orbital", atoms: Collection[int] | None = None
) -> dict[tuple[str, str], Channel]:
    """Sum series into (species, orbital) groups; empty string = summed over that axis.

    Order: species by first atom index, then s, p, d, f. ``atoms`` (1-based atom numbers) keeps
    only the series of those atoms; None keeps all. The order ranks species over all atoms, so a
    filter never changes it.
    """
    species_rank = {name: i for i, name in enumerate(data.species)}
    groups: dict[tuple[str, str], Channel] = {}
    for series in data.series:
        if atoms is not None and series.atom not in atoms:
            continue
        key = _group_key(series, grouping)
        groups[key] = groups[key] + series.channel if key in groups else series.channel
    return dict(
        sorted(
            groups.items(),
            key=lambda item: (species_rank.get(item[0][0], -1), ORBITAL_ORDER.find(item[0][1])),
        )
    )


def selected_total(data: PdosData, atoms: Collection[int]) -> Channel | None:
    """Sum of every projection of ``atoms``; None when none of them has a file."""
    total: Channel | None = None
    for series in data.series:
        if series.atom in atoms:
            total = series.channel if total is None else total + series.channel
    return total


def load_pdos(atm_files: Iterable[Path], tot_file: Path | None = None) -> PdosData:
    """The projections of ``atm_files`` (and the total of ``tot_file``). A file that cannot be read
    (cut short, a number the Fortran format overflowed into ``****``) is left out with a warning, so
    that one bad file does not take the others down (L-11); none readable raises."""
    warnings: list[str] = []
    energy: np.ndarray | None = None
    series = []
    unreadable = 0
    for path in sorted(atm_files, key=lambda p: p.name):
        cancel.check()  # one file is short, a hundred of them are not
        meta = parse_atm_name(path.name)
        if meta is None:
            continue
        try:
            grid, channel = read_pdos_file(path)
        except (ValueError, OSError) as exc:  # PdosFormatError is a ValueError
            warnings.append(_("{name}: ilegível, ignorado ({exc})").format(name=path.name, exc=exc))
            unreadable += 1
            continue
        if energy is None:
            energy = grid
        elif len(grid) != len(energy) or not np.allclose(grid, energy):
            warnings.append(
                _("{name}: grade de energia diferente, interpolada").format(name=path.name)
            )
            channel = Channel(
                np.interp(energy, grid, channel.up),
                None if channel.down is None else np.interp(energy, grid, channel.down),
            )
        series.append(PdosSeries(meta.atom, meta.species, meta.wfc, meta.l, meta.j, channel))
    if energy is None:
        if unreadable:
            raise PdosFormatError(_("nenhum arquivo pdos_atm# legível: {w}").format(w=warnings[0]))
        raise PdosFormatError(_("nenhum arquivo pdos_atm# encontrado"))

    total = None
    total_is_sum = False
    if tot_file is not None:
        try:
            grid, total = read_pdos_file(tot_file, total=True)
        except (ValueError, OSError) as exc:
            warnings.append(
                _("{name}: ilegível ({exc}): total = soma das projeções").format(
                    name=tot_file.name, exc=exc
                )
            )
        else:
            if len(grid) != len(energy) or not np.allclose(grid, energy):
                total = Channel(
                    np.interp(energy, grid, total.up),
                    None if total.down is None else np.interp(energy, grid, total.down),
                )
    if total is None:
        total_is_sum = True
        for s in series:
            total = s.channel if total is None else total + s.channel
        if tot_file is None:
            warnings.append(_("pdos_tot ausente: total = soma das projeções"))
    return PdosData(energy, tuple(series), total, total_is_sum, tuple(warnings))


# -- is the set of projections whole? (L-11) ----------------------------------------------------------
# One line per atomic state in the output of projwfc.x (``QE:PP/src/projwfc.f90:433``); a projection
# file is written for each (atom, wfc) pair, whatever its ``m`` (``partialdos.f90``: ``nlmchi%m == 1``).
_STATE = re.compile(r"^\s*state #\s*\d+: atom\s+(\d+) \(.*?\), wfc\s+(\d+) \(l=")
_LISTED = 5  # pairs a warning names


def read_projwfc_states(path: Path) -> set[tuple[int, int]]:
    """The ``(atom, wfc)`` pairs projwfc.x listed in its output (the block near the top, read only up
    to its end: the rest of the file can be huge); empty when there is none."""
    found: set[tuple[int, int]] = set()
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = _STATE.match(line)
            if match:
                found.add((int(match.group(1)), int(match.group(2))))
            elif found and line.strip():
                break  # the block is contiguous: the first other line ends it
    return found


def _pairs(pairs: list[tuple[int, int]]) -> str:
    text = ", ".join(_("átomo {atom} wfc {wfc}").format(atom=a, wfc=w) for a, w in pairs[:_LISTED])
    return text + ("…" if len(pairs) > _LISTED else "")


def completeness_warnings(
    series: Iterable[PdosSeries], listed: set[tuple[int, int]] | None = None
) -> list[str]:
    """Warnings for a set of projections that looks incomplete or mixed: against ``listed`` (the states
    projwfc.x printed) when there are some, else the holes in the wfc numbers of each atom. Nothing is
    left out: the plot shows what there is, and the user is told."""
    have = {(s.atom, s.wfc) for s in series}
    if listed:
        missing = sorted(listed - have)
        extra = sorted(have - listed)
    else:
        top: dict[int, int] = {}
        for atom, wfc in have:
            top[atom] = max(top.get(atom, 0), wfc)
        missing = sorted(
            (a, w) for a, n in top.items() for w in range(1, n + 1) if (a, w) not in have
        )
        extra = []
    out = []
    if missing:
        out.append(
            _(
                "PDOS incompleta: faltam {n} projeções ({pairs}); arquivo apagado ou execução interrompida?"
            ).format(n=len(missing), pairs=_pairs(missing))
        )
    if extra:
        out.append(
            _(
                "{n} projeções não constam na saída do projwfc.x ({pairs}): de outra execução com o mesmo filpdos?"
            ).format(n=len(extra), pairs=_pairs(extra))
        )
    return out


@dataclass(frozen=True)
class EmptyRegion:
    """A stretch of the total DOS with no states, bounded by states on both sides."""

    low: float  # the last point with states below it
    first: float  # its first empty point
    last: float  # its last empty point
    high: float  # the first point with states above it
    floor: float  # the lowest DOS inside it, states/eV

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def middle(self) -> float:
        return (self.low + self.high) / 2


def empty_regions(energy: np.ndarray, total: Channel) -> list[EmptyRegion]:
    """The regions of empty points (``GAP_DOS_REL_TOL`` of the maximum or less) of the total DOS
    (both spin channels summed), in energy order: one that reaches the edge of the grid has nothing
    to bound it and is left out."""
    if len(energy) < 3:
        return []
    dos = total.up if total.down is None else total.up + total.down
    peak = float(dos.max())
    if peak <= 0:
        return []
    padded = np.concatenate(([False], dos <= GAP_DOS_REL_TOL * peak, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return [
        EmptyRegion(
            float(energy[start - 1]),
            float(energy[start]),
            float(energy[stop - 1]),
            float(energy[stop]),
            float(dos[start:stop].min()),
        )
        for start, stop in zip(changes[::2], changes[1::2], strict=True)
        if start != 0 and stop != len(energy)
    ]


def region_above(regions: Iterable[EmptyRegion], level: float) -> EmptyRegion | None:
    """The first of ``regions`` (in energy order) that ends above ``level``: it holds ``level`` or
    is the next one up."""
    return next((region for region in regions if region.high > level), None)


def dos_gap(energy: np.ndarray, total: Channel, fermi: float | None) -> float | None:
    """The energy gap around ``fermi`` read off the total DOS (both spin channels summed), or None.

    The gap is the widest empty region at most ``GAP_SEARCH_EV`` from E_F (nearest on a tie),
    measured from the last point above the threshold below it to the first above it: the error is
    about the grid step plus the broadening. There is none without E_F or when no such region lies
    near it (a metal, or E_F deep in a band).
    """
    if fermi is None:
        return None
    best: tuple[float, float] | None = None  # (width, -away)
    for region in empty_regions(energy, total):
        away = max(region.first - fermi, fermi - region.last, 0.0)
        if away > GAP_SEARCH_EV:
            continue
        candidate = (region.width, -away)
        if best is None or candidate > best:
            best = candidate
    return None if best is None else best[0]


def dos_gap_window(
    energy: np.ndarray, total: Channel, low: float, high: float, min_width: float
) -> float | None:
    """The widest empty region of the total DOS whose two bounding points (the last one with
    states below it, the first one above) lie in ``[low, high]`` (absolute energies: the plot's
    window), measured as ``dos_gap`` measures; None when none is ``min_width`` wide."""
    low, high = sorted((low, high))
    widths = [
        region.width
        for region in empty_regions(energy, total)
        if low <= region.low and region.high <= high
    ]
    best = max(widths, default=None)
    return best if best is not None and best >= min_width else None
