"""Distance and angle between exact atom copies (``AtomRef``), as the user clicked them (spec 44 R1.1).

No minimum image is implied: in a repeated cell the copies measured are the ones on screen; for the nearest
image the user repeats the cell and clicks the neighbouring copy.
"""

from __future__ import annotations

import math

import numpy as np

from .model import AtomRef, Structure

__all__ = ["angle", "distance"]


def distance(structure: Structure, a: AtomRef, b: AtomRef) -> float:
    """Distance (Å) between the copies ``a`` and ``b``."""
    return float(np.linalg.norm(structure.position(b) - structure.position(a)))


def angle(structure: Structure, a: AtomRef, b: AtomRef, c: AtomRef) -> float:
    """Angle a–b–c in degrees, the vertex at ``b``; NaN when an arm has zero length."""
    u = structure.position(a) - structure.position(b)
    v = structure.position(c) - structure.position(b)
    norm = float(np.linalg.norm(u) * np.linalg.norm(v))
    if norm == 0:
        return float("nan")
    cosine = float(np.clip(u @ v / norm, -1.0, 1.0))
    return math.degrees(math.acos(cosine))
