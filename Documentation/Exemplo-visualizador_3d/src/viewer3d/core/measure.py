"""Distances, angles and dihedrals on exact atom copies (``AtomRef``)."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from viewer3d.core.structure import AtomRef, Structure


@dataclass(frozen=True, eq=False)
class Distance:
    value: float  # Å
    delta: np.ndarray  # (3,) Å, position of b minus position of a


def distance(structure: Structure, a: AtomRef, b: AtomRef) -> Distance:
    """Distance between the exact copies ``a`` and ``b`` (no implicit minimum image)."""
    delta = structure.position(b) - structure.position(a)
    return Distance(float(np.linalg.norm(delta)), delta)


def angle(structure: Structure, a: AtomRef, b: AtomRef, c: AtomRef) -> float:
    """Angle a-b-c in degrees, vertex at ``b``; NaN when an arm has zero length."""
    u = structure.position(a) - structure.position(b)
    v = structure.position(c) - structure.position(b)
    norm = np.linalg.norm(u) * np.linalg.norm(v)
    if norm == 0:
        return float("nan")
    cosine = float(np.clip(u @ v / norm, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def dihedral(structure: Structure, a: AtomRef, b: AtomRef, c: AtomRef, d: AtomRef) -> float:
    """Signed dihedral a-b-c-d in degrees (IUPAC: clockwise a->d seen from b to c is positive)."""
    pa, pb, pc, pd = (structure.position(r) for r in (a, b, c, d))
    b0, b1, b2 = pa - pb, pc - pb, pd - pc
    axis = np.linalg.norm(b1)
    if axis == 0:
        return float("nan")
    b1 = b1 / axis
    v = b0 - (b0 @ b1) * b1
    w = b2 - (b2 @ b1) * b1
    if not np.any(v) or not np.any(w):
        return float("nan")
    return math.degrees(math.atan2(float((np.cross(b1, v)) @ w), float(v @ w)))


def nearest_image(structure: Structure, a: AtomRef, b: AtomRef) -> AtomRef:
    """Copy of atom ``b.index`` closest to the exact copy ``a``.

    The search is a 5x5x5 window centred on the rounded fractional difference, which stays
    correct for strongly oblique cells.
    """
    pos_a = structure.frac[a.index] + np.asarray(a.shift, dtype=float)
    centre = np.round(pos_a - structure.frac[b.index]).astype(int)
    window = np.array(list(itertools.product(range(-2, 3), repeat=3)), dtype=int)
    candidates = centre + window
    diff = (structure.frac[b.index] + candidates - pos_a) @ structure.cell
    best = candidates[int(np.argmin(np.einsum("ij,ij->i", diff, diff)))]
    return AtomRef(b.index, tuple(int(x) for x in best))
