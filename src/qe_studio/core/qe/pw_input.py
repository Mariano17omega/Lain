"""Quantum ESPRESSO input files (pw.x, bands.x, projwfc.x, dos.x).

Namelists are read with ASE's ``read_fortran_namelist``, which keeps trailing ``!`` comments
on card lines — that is where users put high-symmetry labels (``0.0 0.5 0.0 20 ! Y``).
The K_POINTS card itself is parsed here because ASE only writes ``crystal_b`` cards.
"""

from __future__ import annotations

import functools
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Namelists each program reads, in the order ``deduce_program`` tries them.
PROGRAM_NAMELISTS: dict[str, frozenset[str]] = {
    "pw": frozenset({"control", "system", "electrons", "ions", "cell", "fcp", "rism"}),
    "bands": frozenset({"bands"}),
    "projwfc": frozenset({"projwfc"}),
    "dos": frozenset({"dos"}),
    "pp": frozenset({"inputpp", "plot"}),
}
PW_NAMELISTS = PROGRAM_NAMELISTS["pw"]
# The namelists that identify a program when it reads more than it names: a bare ``&PLOT`` is also
# the header of a bands.x ``filband`` file, so only ``&INPUTPP`` says pp.x (spec 29 R5.1).
DECIDING_NAMELISTS: dict[str, frozenset[str]] = {"pp": frozenset({"inputpp"})}


def deduce_program(names: Iterable[str]) -> str | None:
    """``pw``, ``bands``, ``projwfc``, ``dos``, ``pp`` or None, from lowercase namelist names."""
    present = set(names)
    for program, known in PROGRAM_NAMELISTS.items():
        if present & DECIDING_NAMELISTS.get(program, known):
            return program
    return None


@dataclass(frozen=True)
class KPointsCard:
    mode: str
    points: np.ndarray = field(repr=False)  # (n, 3)
    weights: np.ndarray = field(repr=False)  # (n,)
    labels: tuple[str, ...] = ()

    @property
    def is_path(self) -> bool:
        return self.mode.endswith("_b")

    def vertex_indices(self) -> list[int]:
        """Index of each path vertex in the generated k-point list (``*_b`` modes).

        pw.x puts ``weights[i]`` points on segment i and the last vertex's weight is ignored,
        so the list holds ``sum(weights[:-1]) + 1`` points.
        """
        counts = [max(int(round(w)), 1) for w in self.weights[:-1]]
        return [0, *np.cumsum(counts).tolist()]

    @property
    def path_length(self) -> int:
        return self.vertex_indices()[-1] + 1 if len(self.weights) else 0


@dataclass(frozen=True)
class QEInput:
    namelists: dict[str, dict[str, Any]]
    cards: tuple[str, ...]
    kpoints: KPointsCard | None = None

    @property
    def program(self) -> str | None:
        """``pw``, ``bands``, ``projwfc``, ``dos``, ``pp`` or None."""
        return deduce_program(self.namelists)

    @property
    def calculation(self) -> str | None:
        """pw.x ``calculation`` (QE default ``scf``); None for other programs."""
        if self.program != "pw":
            return None
        value = self.namelists.get("control", {}).get("calculation", "scf")
        return str(value).strip().lower()

    def get(self, namelist: str, key: str, default: Any = None) -> Any:
        return self.namelists.get(namelist, {}).get(key.lower(), default)


NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?")


def fortran_float(text: str) -> float | None:
    """``1d-8``, ``1.E-8``, ``.5``: the float a Fortran namelist number means, else None.

    Guarded by ``NUMBER`` because Python's ``float`` also takes ``nan``, ``inf`` and ``1_0``.
    """
    token = text.strip()
    if not NUMBER.fullmatch(token):
        return None
    return float(token.replace("d", "e").replace("D", "e"))


def _floats(text: str) -> list[float]:
    return [float(tok.replace("d", "e").replace("D", "e")) for tok in NUMBER.findall(text)]


def parse_kpoints(card_lines: list[str] | tuple[str, ...]) -> KPointsCard | None:
    for i, line in enumerate(card_lines):
        head = line.split()
        if not head or head[0].upper() != "K_POINTS":
            continue
        mode = re.sub(r"[{}()]", " ", line[len(head[0]) :]).strip().lower() or "tpiba"
        mode = mode.split()[0]
        empty = np.zeros((0, 3))
        if mode == "gamma":
            return KPointsCard(mode, empty, np.zeros(0))
        if mode == "automatic":
            values = _floats(card_lines[i + 1]) if i + 1 < len(card_lines) else []
            return KPointsCard(mode, np.array([values[:3]]), np.array(values[3:6]))
        try:
            count = int(card_lines[i + 1].split()[0])
        except (IndexError, ValueError):
            return None
        points, weights, labels = [], [], []
        for row in card_lines[i + 2 : i + 2 + count]:
            marker = re.search(r"[!#]", row)
            data, comment = (row[: marker.start()], row[marker.end() :]) if marker else (row, "")
            values = _floats(data)
            if len(values) < 3:
                break
            points.append(values[:3])
            weights.append(values[3] if len(values) > 3 else 1.0)
            labels.append(comment.strip())
        return KPointsCard(mode, np.array(points), np.array(weights), tuple(labels))
    return None


def parse_input(text: str) -> QEInput:
    # ASE takes ~0.3 s to import (scipy, spacegroups): only when an input is first parsed.
    from ase.io.espresso import read_fortran_namelist

    namelists, cards = read_fortran_namelist(io.StringIO(text))
    namelists = {
        name: {str(k).lower(): v for k, v in values.items()}
        for name, values in namelists.items()
        if name != "_ignored"
    }
    return QEInput(namelists, tuple(cards), parse_kpoints(cards))


def read_input(path: Path) -> QEInput | None:
    """``parse_input`` of a file, None if it cannot be read or parsed; memoized on the file's
    (path, mtime, size), since detection asks for the same bands.x inputs on every pass.

    The result is shared between callers: treat it as read-only.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read_input(str(path), stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=256)
def _read_input(path: str, _mtime_ns: int, _size: int) -> QEInput | None:
    try:
        return parse_input(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:  # ASE's namelist reader raises assorted errors on odd inputs
        return None


def format_kpoint_label(label: str) -> str:
    """Matplotlib label for a high-symmetry point: G/Gamma → Γ, ``Y2`` → Y₂ (mathtext)."""
    label = label.strip()
    if not label:
        return ""
    if label.lower() in {"g", "gamma", "γ", r"\gamma", r"$\gamma$"}:
        return r"$\Gamma$"
    if "$" in label:
        return label
    match = re.fullmatch(r"([A-Za-z]+)[_]?(\d+)", label)
    if match:
        return rf"{match.group(1)}$_{{{match.group(2)}}}$"
    return label
