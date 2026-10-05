"""K-points of the generated inputs (spec 25 R5): a band path as ``K_POINTS crystal_b`` and a manual
mesh as ``K_POINTS automatic``.

The band path is typed by the user (spec 27-2). Two checks use the SCF's cell: ``collapsed_segments``
finds the segments bands.x would draw with no extent on its x axis (it takes a step more than 5× the
previous one for a jump between disconnected segments) and ``distribute`` sets the points of each
segment from its length, which keeps the steps even.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..qe.bands_x import path_coordinates

__all__ = [
    "DEFAULT_NPTS",
    "MAX_NPTS",
    "CollapsedSegment",
    "KMesh",
    "KPath",
    "KPoint",
    "SegmentProgress",
    "collapse_note",
    "collapsed_segments",
    "distribute",
    "segment_progress",
    "to_card",
]

DEFAULT_NPTS = 20
MAX_NPTS = 1000  # per point: a stray zero would make a huge card
COLLAPSE_LIMIT = 0.5  # a segment that advances less than this share of its length is collapsed


@dataclass(frozen=True)
class KMesh:
    """A Monkhorst–Pack mesh: ``n1 n2 n3`` and the shifts ``s1 s2 s3`` (0 or 1)."""

    n: tuple[int, int, int]
    shift: tuple[int, int, int] = (0, 0, 0)

    @property
    def count(self) -> int:
        return self.n[0] * self.n[1] * self.n[2]

    def problems(self) -> list[str]:
        out = []
        if min(self.n) < 1:
            out.append("a rede de k-points precisa de n1, n2, n3 ≥ 1")
        if any(s not in (0, 1) for s in self.shift):
            out.append("os deslocamentos da rede são 0 ou 1")
        return out

    def card(self) -> tuple[str, list[str]]:
        """Option and body of ``K_POINTS automatic``."""
        return "automatic", [" ".join(str(v) for v in (*self.n, *self.shift))]

    @classmethod
    def parse(cls, text: str) -> KMesh | None:
        """``8 8 8`` or ``8 8 8 0 0 0`` (the body line of an automatic card); None otherwise."""
        try:
            values = [int(token) for token in text.split()]
        except ValueError:
            return None
        if len(values) not in (3, 6):
            return None
        n = (values[0], values[1], values[2])
        shift = (values[3], values[4], values[5]) if len(values) == 6 else (0, 0, 0)
        return cls(n, shift)


@dataclass(frozen=True)
class KPoint:
    label: str  # as it goes in the card's comment ("Gamma", "X"); may be empty
    frac: tuple[float, float, float]  # in units of the input's reciprocal vectors
    npts: int = DEFAULT_NPTS  # points to the next one


@dataclass(frozen=True)
class KPath:
    points: tuple[KPoint, ...]
    # Index i: the path jumps from point i to i + 1 (``X|U``), so point i weighs 1.
    breaks: frozenset[int] = frozenset()
    warnings: tuple[str, ...] = ()

    def weights(self) -> list[int]:
        last = len(self.points) - 1
        return [
            1 if i == last or i in self.breaks else max(int(point.npts), 1)
            for i, point in enumerate(self.points)
        ]

    def problems(self) -> list[str]:
        if len(self.points) < 2:
            return ["Defina ao menos 2 pontos do caminho"]
        return []


def _coordinate(value: float) -> str:
    return f"{value + 0.0: .8f}"  # + 0.0: no "-0.00000000"


def to_card(path: KPath) -> tuple[str, list[str]]:
    """Option and body of ``K_POINTS crystal_b``: the count, then ``f1 f2 f3 weight ! label``."""
    rows = [str(len(path.points))]
    for point, weight in zip(path.points, path.weights(), strict=True):
        row = " ".join(_coordinate(v) for v in point.frac) + f" {weight:4d}"
        rows.append(f"{row}  ! {point.label}" if point.label.strip() else row)
    return "crystal_b", rows


# -- the x axis of bands.x ----------------------------------------------------------------------------
@dataclass(frozen=True)
class SegmentProgress:
    """What bands.x does with the segment from vertex ``a`` to ``b``: its real length and how far
    the x axis advances over it (both in Å⁻¹)."""

    a: int
    b: int
    real: float
    advance: float


@dataclass(frozen=True)
class CollapsedSegment:
    a: int  # vertex the segment starts at (the editor marks its row)
    b: int
    lost: float  # share of its length that does not reach the x axis (0–1)


def _reciprocal(cell) -> np.ndarray | None:
    """Rows b1 b2 b3 in Å⁻¹ (with 2π) of ``cell`` (rows a1 a2 a3 in Å); None for a singular cell."""
    try:
        rec = 2 * np.pi * np.linalg.inv(np.asarray(cell, dtype=float)).T
    except (np.linalg.LinAlgError, ValueError, TypeError):
        return None
    return rec if rec.shape == (3, 3) and np.all(np.isfinite(rec)) else None


def _expand(path: KPath, rec: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """The k points pw.x makes of the card (Cartesian, Å⁻¹) and where each vertex lands in them:
    ``weight`` steps from a vertex to the next, none after a break, the last vertex once."""
    frac = np.array([point.frac for point in path.points], dtype=float)
    weights = path.weights()
    pieces, index, count = [], [], 0
    for i, weight in enumerate(weights):
        index.append(count)
        if i == len(weights) - 1:
            pieces.append(frac[i : i + 1])
            count += 1
        else:
            t = (np.arange(weight) / weight)[:, None]
            pieces.append(frac[i] + t * (frac[i + 1] - frac[i]))
            count += weight
    return np.concatenate(pieces) @ rec, index


def segment_progress(path: KPath, cell) -> list[SegmentProgress]:
    """Real length and x advance of every segment bands.x sees (``bands_x.path_coordinates`` over the
    points pw.x makes). Never raises: fewer than 2 points, a singular cell or no steps give ``[]``."""
    rec = _reciprocal(cell)
    if rec is None or len(path.points) < 2:
        return []
    kcart, index = _expand(path, rec)
    if not np.all(np.isfinite(kcart)):
        return []
    steps = np.linalg.norm(np.diff(kcart, axis=0), axis=1)
    x = path_coordinates(kcart)
    weights = path.weights()
    out = []
    for a in range(len(path.points) - 1):
        if a in path.breaks or weights[a] < 2:  # a jump: not a segment
            continue
        real = float(steps[index[a] : index[a + 1]].sum())
        if real > 0:
            out.append(SegmentProgress(a, a + 1, real, float(x[index[a + 1]] - x[index[a]])))
    return out


def collapsed_segments(path: KPath, cell) -> list[CollapsedSegment]:
    """The segments that bands.x draws with less than half of their length on the x axis: a step
    more than 5× the previous one is taken for a jump and does not advance it."""
    return [
        CollapsedSegment(seg.a, seg.b, 1 - seg.advance / seg.real)
        for seg in segment_progress(path, cell)
        if seg.advance < COLLAPSE_LIMIT * seg.real
    ]


def _name(path: KPath, index: int) -> str:
    label = path.points[index].label.strip()
    if not label:
        return f"ponto {index + 1}"
    return "Γ" if label.lower() == "gamma" else label


def collapse_note(path: KPath, segment: CollapsedSegment) -> str:
    """The warning of a collapsed segment (plan note and row tooltip)."""
    return (
        f"Segmento {_name(path, segment.a)}→{_name(path, segment.b)} colapsa no eixo x do bands.x "
        "(passo maior que 5× o anterior): aumente os pontos do segmento anterior, reduza os "
        "deste ou use ‘Distribuir pelo comprimento’"
    )


def distribute(path: KPath, cell, density: float, min_pts: int = 2) -> KPath:
    """``path`` with the points of each segment set from its length: ``round(Å⁻¹ · density)``, at
    least ``min_pts``, at most ``MAX_NPTS``. The last point and the ones before a break do not count
    (weight 1 in the card) and keep their value; the rest of the path is untouched. A singular cell or
    a density that is not positive gives ``path`` back."""
    rec = _reciprocal(cell)
    if rec is None or not density > 0 or not np.isfinite(density):
        return path
    points = list(path.points)
    for i in range(len(points) - 1):
        if i in path.breaks:
            continue
        delta = (np.asarray(points[i + 1].frac) - np.asarray(points[i].frac)) @ rec
        length = float(np.linalg.norm(delta))
        if np.isfinite(length):
            npts = min(max(min_pts, 1, round(length * density)), MAX_NPTS)
            points[i] = replace(points[i], npts=npts)
    return replace(path, points=tuple(points))
