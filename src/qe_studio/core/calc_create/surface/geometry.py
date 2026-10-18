"""Distances in a periodic cell, bonds and empty gaps (spec 40 R2.3).

Minimum images search the images −1…1 of each axis, in ``itertools.product`` order, keeping the first
on a tie, as the user's scripts do: whether a bond *crosses* an axis (its image along it is not 0) is
what the slab reads, so the image is relative to the fractions as written (never wrapped).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np

from ....i18n import _
from ..scf_info import ScfInfo
from .elements import covalent_radius
from .model import Model
from .report import decimal

__all__ = [
    "IMAGES",
    "MIN_SURFACE_GAP",
    "bond_cutoff",
    "bonded",
    "interplanar",
    "min_image",
    "pair_images",
    "skewed",
    "surface_problem",
    "vacuum_gaps",
]

MIN_SURFACE_GAP = 5.0  # Å: an empty gap shorter than this is no surface's vacuum
IMAGES = np.array(list(itertools.product((-1, 0, 1), repeat=3)), dtype=int)


def min_image(delta_frac: np.ndarray, cell: np.ndarray) -> tuple[float, np.ndarray]:
    """The shortest length of ``delta_frac`` plus an image, and that image."""
    lengths = np.linalg.norm((np.asarray(delta_frac, float) + IMAGES) @ cell, axis=1)
    best = int(np.argmin(lengths))  # the first on a tie
    return float(lengths[best]), IMAGES[best].copy()


def pair_images(
    frac: np.ndarray, cell: np.ndarray, rows: Sequence[int], cols: Sequence[int]
) -> tuple[np.ndarray, np.ndarray]:
    """For every pair (``rows[i]``, ``cols[j]``): the minimum-image distance of ``frac[col] −
    frac[row]`` and its image, as ``(len(rows), len(cols))`` and ``(…, 3)`` arrays."""
    frac = np.asarray(frac, float)
    delta = frac[list(cols)][None, :, :] - frac[list(rows)][:, None, :]
    best = np.full(delta.shape[:2], np.inf)
    image = np.zeros((*delta.shape[:2], 3), dtype=int)
    for shift in IMAGES:  # one image at a time: memory stays that of one distance matrix
        lengths = np.linalg.norm((delta + shift) @ cell, axis=-1)
        better = lengths < best
        best[better] = lengths[better]
        image[better] = shift
    return best, image


def bond_cutoff(first: str, second: str, scale: float) -> float:
    """``scale`` × the sum of the covalent radii of two species labels (Å)."""
    return scale * (covalent_radius(first) + covalent_radius(second))


def bonded(model: Model, i: int, j: int, scale: float) -> bool:
    """Whether atoms ``i`` and ``j`` are bonded: distance ``<=`` ``bond_cutoff``."""
    distance, __ = min_image(model.frac[j] - model.frac[i], model.cell)
    return distance <= bond_cutoff(model.labels[i], model.labels[j], scale)


def interplanar(cell: np.ndarray) -> np.ndarray:
    """The distance between the lattice planes of each axis: ``V / |a_j × a_k|``."""
    volume = abs(float(np.linalg.det(cell)))
    return np.array(
        [volume / np.linalg.norm(np.cross(cell[(a + 1) % 3], cell[(a + 2) % 3])) for a in range(3)]
    )


def vacuum_gaps(cell: np.ndarray, frac: np.ndarray) -> tuple[float, float, float]:
    """The widest empty gap along each axis (Å, between atom centres, across the cell edge too)."""
    spacing = interplanar(cell)
    frac = np.asarray(frac, float).reshape(-1, 3)
    gaps = []
    for axis in range(3):
        if not len(frac):
            gaps.append(float(spacing[axis]))
            continue
        values = np.sort(frac[:, axis] % 1.0)
        steps = np.diff(np.append(values, values[0] + 1.0))
        gaps.append(float(steps.max() * spacing[axis]))
    return gaps[0], gaps[1], gaps[2]


def skewed(cell: np.ndarray) -> bool:
    """Whether any two cell vectors are not orthogonal."""
    unit = cell / np.linalg.norm(cell, axis=1)[:, None]
    return any(abs(float(unit[i] @ unit[j])) > 1e-6 for i, j in ((0, 1), (0, 2), (1, 2)))


def surface_problem(scf: ScfInfo, name: str) -> str | None:
    """Why ``scf`` is no surface with its vacuum along c, as the Slab makes it (None: it is one); for
    a type that puts a molecule on a surface and must refuse a bulk's SCF (spec 42 R1)."""
    crystal = scf.crystal
    if crystal is None:
        return _("Estrutura de {name} ilegível: {value}").format(
            name=name, value=scf.structure_problem or "sem estrutura"
        )
    gaps = vacuum_gaps(crystal.cell, crystal.frac)
    if gaps[2] >= MIN_SURFACE_GAP:
        return None
    open_axes = [axis for axis, gap in zip("ab", gaps[:2], strict=True) if gap >= MIN_SURFACE_GAP]
    other = open_axes[0] if open_axes else None
    if other is not None:
        return _(
            "O vácuo de {name} está ao longo de {other}; o Lain espera a superfície com o vácuo ao longo de c, como o Slab gera."
        ).format(name=name, other=other)
    return _(
        "{name} parece o SCF de um bulk: não há vácuo ao longo de c (maior intervalo vazio: {decimal} Å). Escolha o SCF de uma superfície relaxada (Slab ou Supercélula)."
    ).format(name=name, decimal=decimal(gaps[2]))
