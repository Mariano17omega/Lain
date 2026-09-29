"""Quantum ESPRESSO input files (pw.x, bands.x, projwfc.x, dos.x).

Namelists are read with ASE's ``read_fortran_namelist``, which keeps trailing ``!`` comments
on card lines — that is where users put high-symmetry labels (``0.0 0.5 0.0 20 ! Y``).
The K_POINTS card itself is parsed here because ASE only writes ``crystal_b`` cards.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from ase.io.espresso import read_fortran_namelist

PW_NAMELISTS = {"control", "system", "electrons", "ions", "cell"}


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
        """``pw``, ``bands``, ``projwfc``, ``dos`` or None."""
        names = set(self.namelists)
        if names & PW_NAMELISTS:
            return "pw"
        for program in ("bands", "projwfc", "dos"):
            if program in names:
                return program
        return None

    @property
    def calculation(self) -> str | None:
        """pw.x ``calculation`` (QE default ``scf``); None for other programs."""
        if self.program != "pw":
            return None
        value = self.namelists.get("control", {}).get("calculation", "scf")
        return str(value).strip().lower()

    def get(self, namelist: str, key: str, default: Any = None) -> Any:
        return self.namelists.get(namelist, {}).get(key.lower(), default)


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?")


def _floats(text: str) -> list[float]:
    return [float(tok.replace("d", "e").replace("D", "e")) for tok in _NUMBER.findall(text)]


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
    namelists, cards = read_fortran_namelist(io.StringIO(text))
    namelists = {
        name: {str(k).lower(): v for k, v in values.items()}
        for name, values in namelists.items()
        if name != "_ignored"
    }
    return QEInput(namelists, tuple(cards), parse_kpoints(cards))


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
