"""A diagonal supercell of a structure (spec 41 R1, ``make_supercell([n, 1, 1])`` of the scripts).

The cell rows become ``n_i × a_i``; each atom, in the SCF's order, is followed by its replicas ``(i, j, k)``
with ``i`` slowest, at ``(frac + (i, j, k)) / n`` (never wrapped), and every replica keeps the atom's
``if_pos`` flags. ``plan`` runs on the GUI thread at every edit, so the size is capped: each ``n_i`` from 1
to ``MAX_REPEAT`` and at most ``MAX_ATOMS`` atoms.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np

from . import SurfaceError
from .model import Model

__all__ = [
    "AXIS_NAMES",
    "MAX_ATOMS",
    "MAX_REPEAT",
    "make_supercell",
    "repeat_problem",
    "size_problem",
]

MAX_REPEAT = 8
MAX_ATOMS = 2000
AXIS_NAMES = ("a", "b", "c")


def repeat_problem(axis: int, n: int) -> str | None:
    """Why ``n`` repetitions along ``axis`` (0-based) are refused (None: they are fine)."""
    if not 1 <= n <= MAX_REPEAT:
        return f"Repetições ao longo de {AXIS_NAMES[axis]}: de 1 a {MAX_REPEAT}"
    return None


def size_problem(atoms: int, n: Sequence[int]) -> str | None:
    """Why a supercell of ``atoms`` atoms repeated ``n`` times is too big (None: it is not)."""
    total = atoms * int(np.prod(n))
    if total > MAX_ATOMS:
        return f"Supercélula grande demais para o Lain: {total} átomos (máximo {MAX_ATOMS})"
    return None


def make_supercell(model: Model, n: Sequence[int]) -> Model:
    """``model`` repeated ``n = (n1, n2, n3)`` times. Raises ``SurfaceError`` past the limits."""
    for axis, value in enumerate(n):
        problem = repeat_problem(axis, value)
        if problem is not None:
            raise SurfaceError(problem)
    problem = size_problem(len(model), n)
    if problem is not None:
        raise SurfaceError(problem)
    scale = np.array(n, dtype=float)
    shifts = np.array(list(itertools.product(*(range(value) for value in n))), dtype=float)
    frac = ((model.frac[:, None, :] + shifts[None, :, :]) / scale).reshape(-1, 3)
    copies = len(shifts)
    labels = tuple(label for label in model.labels for _ in range(copies))
    flags = tuple(model.flag(i) for i in range(len(model)) for _ in range(copies))
    return Model(model.cell * scale[:, None], labels, frac, flags)
