"""Bond detection with periodic images, and neighbour lookup."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from .elements import element_for_label
from .model import AtomRef, Structure, as_shift

DEFAULT_FACTOR = 1.15
MIN_DISTANCE = 0.1  # Å, anything closer is the same atom
KDTREE_THRESHOLD = 1000  # atoms; below it the dense numpy search is faster
MAX_REACH = 3  # cells searched per direction, whatever the geometry


@dataclass(frozen=True, eq=False)
class Bonds:
    """Bond table: atom ``i`` is bonded to the copy ``j + shift`` of atom ``j``.

    Each physical bond appears once; ``(i, j, s)`` and ``(j, i, -s)`` are the same bond.
    """

    i: np.ndarray  # (m,) int
    j: np.ndarray  # (m,) int
    shift: np.ndarray  # (m, 3) int, lattice translation applied to atom j
    dist: np.ndarray  # (m,) Å

    def __len__(self) -> int:
        return len(self.i)


def covalent_radii(structure: Structure) -> np.ndarray:
    """(n,) covalent radius of each atom, Å."""
    per_species = np.array([element_for_label(s.label).r_cov for s in structure.species])
    return per_species[structure.species_index]


def bonds_for(structure: Structure, factor: float = DEFAULT_FACTOR) -> Bonds:
    return compute_bonds(structure.cell, structure.frac, covalent_radii(structure), factor)


def _cell_heights(cell: np.ndarray) -> np.ndarray:
    volume = abs(float(np.linalg.det(cell)))
    areas = np.array(
        [np.linalg.norm(np.cross(cell[(k + 1) % 3], cell[(k + 2) % 3])) for k in range(3)]
    )
    return volume / np.maximum(areas, 1e-12)


def _lex_positive(shift: np.ndarray) -> bool:
    for value in shift:
        if value != 0:
            return value > 0
    return False


def compute_bonds(
    cell: np.ndarray, frac: np.ndarray, r_cov: np.ndarray, factor: float = DEFAULT_FACTOR
) -> Bonds:
    """Find bonds ``d < factor * (r_i + r_j)`` and ``d > 0.1 Å``, over periodic images."""
    cell = np.asarray(cell, dtype=float)
    frac = np.asarray(frac, dtype=float).reshape(-1, 3)
    r = np.asarray(r_cov, dtype=float)
    n = len(frac)
    empty = Bonds(np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3), int), np.zeros(0))
    if n == 0:
        return empty

    # Search on positions wrapped into [0, 1) so that the translation range is bounded; the
    # result is converted back to the frame of the input coordinates at the end.
    offsets = np.floor(frac).astype(int)
    wrapped = frac - offsets
    points = wrapped @ cell
    r_max = 2.0 * float(r.max()) * factor
    rho = r_max / _cell_heights(cell)  # reach of a bond along each lattice direction, in cells
    reach = np.clip(np.ceil(rho), 1, MAX_REACH).astype(int)
    use_tree = n >= KDTREE_THRESHOLD
    if use_tree:
        from scipy.spatial import KDTree  # lazy: only for big structures

        tree = KDTree(points)

    found_i, found_j, found_s = [], [], []
    for s in itertools.product(*(range(-int(k), int(k) + 1) for k in reach)):
        s_arr = np.array(s)
        moved = wrapped + s_arr
        subset = np.nonzero(np.all((moved >= -rho) & (moved <= 1.0 + rho), axis=1))[0]
        if len(subset) == 0:
            continue
        shifted = points[subset] + s_arr @ cell
        if use_tree:
            pairs = tree.sparse_distance_matrix(KDTree(shifted), r_max, output_type="ndarray")
            ii, jj, dd = pairs["i"], pairs["j"], pairs["v"]
            keep = (dd < factor * (r[ii] + r[subset[jj]])) & (dd > MIN_DISTANCE)
            ii, jj = ii[keep], jj[keep]
        else:
            d2 = ((points[:, None, :] - shifted[None, :, :]) ** 2).sum(axis=-1)
            limit = (factor * (r[:, None] + r[subset][None, :])) ** 2
            ii, jj = np.nonzero((d2 < limit) & (d2 > MIN_DISTANCE**2))
        jj = subset[jj]
        keep = ii < jj
        if _lex_positive(s_arr):
            keep |= ii == jj
        if keep.any():
            found_i.append(ii[keep])
            found_j.append(jj[keep])
            found_s.append(np.tile(s_arr, (int(keep.sum()), 1)))
    if not found_i:
        return empty

    i = np.concatenate(found_i)
    j = np.concatenate(found_j)
    shift = np.concatenate(found_s) - offsets[j] + offsets[i]  # back to the input frame
    dist = np.linalg.norm((frac[j] + shift - frac[i]) @ cell, axis=1)
    order = np.lexsort((shift[:, 2], shift[:, 1], shift[:, 0], j, i))
    return Bonds(i[order], j[order], shift[order], dist[order])


class BondGraph:
    """Adjacency of a bond table, answering ``neighbors(ref)`` for any atom copy."""

    def __init__(self, bonds: Bonds, n_atoms: int):
        both_a = np.concatenate([bonds.i, bonds.j])
        both_b = np.concatenate([bonds.j, bonds.i])
        both_s = np.concatenate([bonds.shift, -bonds.shift])
        both_d = np.concatenate([bonds.dist, bonds.dist])
        order = np.argsort(both_a, kind="stable")
        self._partner = both_b[order]
        self._shift = both_s[order]
        self._dist = both_d[order]
        self._start = np.searchsorted(both_a[order], np.arange(n_atoms + 1))

    def neighbors(self, ref: AtomRef) -> list[tuple[AtomRef, float]]:
        """Bonded neighbours of an atom copy, nearest first."""
        lo, hi = self._start[ref.index], self._start[ref.index + 1]
        base = np.asarray(ref.shift, dtype=int)
        out = [
            (
                AtomRef(int(self._partner[k]), as_shift(base + self._shift[k])),
                float(self._dist[k]),
            )
            for k in range(lo, hi)
        ]
        out.sort(key=lambda item: item[1])
        return out

    def coordination(self, ref: AtomRef) -> int:
        return int(self._start[ref.index + 1] - self._start[ref.index])


__all__ = ["DEFAULT_FACTOR", "BondGraph", "Bonds", "bonds_for", "compute_bonds", "covalent_radii"]
