"""Visual repetition n1 x n2 x n3 of the cell, with ghost atoms at the block border."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from viewer3d.core.bonds import Bonds
from viewer3d.core.structure import AtomRef, Structure


def shifts(n1: int, n2: int, n3: int) -> np.ndarray:
    """(m, 3) int translations of the copies, ``n3`` varying fastest; (0,0,0) comes first."""
    return np.array(list(itertools.product(range(n1), range(n2), range(n3))), dtype=int).reshape(
        -1, 3
    )


def original_mask(copies: np.ndarray) -> np.ndarray:
    """True for the copy that is the original cell, (0, 0, 0)."""
    return ~np.any(copies, axis=1)


@dataclass(frozen=True, eq=False)
class Scene:
    """Everything the renderer draws; the ``Structure`` itself never changes."""

    positions: np.ndarray  # (A, 3) Å; the n_real atoms first, then the ghosts
    species: np.ndarray  # (A,) int, index into ``Structure.species``
    refs: tuple[AtomRef, ...]  # identity of each real atom
    n_real: int
    original: np.ndarray  # (n_real,) bool, atom belongs to the original (0, 0, 0) copy
    bond_a: np.ndarray  # (K,) int index into ``positions``
    bond_b: np.ndarray  # (K,) int index into ``positions``
    cell: np.ndarray  # (3, 3) Å, original cell
    frac: np.ndarray  # (n, 3) fractional coordinates of the original atoms
    reps: tuple[int, int, int]

    def position(self, ref: AtomRef) -> np.ndarray:
        """Cartesian position (Å) of any atom copy, drawn or not."""
        return (self.frac[ref.index] + np.asarray(ref.shift, dtype=float)) @ self.cell

    @property
    def n_ghost(self) -> int:
        return len(self.positions) - self.n_real

    @property
    def block(self) -> np.ndarray:
        """(3, 3) Å, vectors of the repeated block."""
        return self.cell * np.asarray(self.reps, dtype=float)[:, None]

    def box_corners(self, vectors: np.ndarray | None = None) -> np.ndarray:
        """(8, 3) corners of the cell (or of the given vectors) from the origin."""
        v = self.cell if vectors is None else vectors
        bits = np.array(list(itertools.product((0, 1), repeat=3)), dtype=float)
        return bits @ v

    def bounds_points(self) -> np.ndarray:
        """Points the camera should frame: block corners and every atom, ghosts included."""
        return np.vstack([self.box_corners(self.block), self.positions])


def build_scene(
    structure: Structure, bonds: Bonds, reps: tuple[int, int, int] = (1, 1, 1)
) -> Scene:
    """Replicate atoms by translation and place the bonds, with ghosts for outside partners.

    Bonds are computed once on the original cell and only translated here.
    """
    n = len(structure)
    reps_arr = np.asarray(reps, dtype=int)
    copies = shifts(*reps)
    n_copies = len(copies)
    frac = structure.frac
    cell = structure.cell

    positions = ((frac[None, :, :] + copies[:, None, :]) @ cell).reshape(-1, 3)
    species = np.tile(structure.species_index, n_copies)
    refs = tuple(AtomRef(i, tuple(int(x) for x in c)) for c in copies for i in range(n))
    n_real = n * n_copies
    original = np.repeat(original_mask(copies), n)

    bond_a = np.zeros(0, dtype=int)
    bond_b = np.zeros(0, dtype=int)
    ghost_pos = np.zeros((0, 3))
    ghost_species = np.zeros(0, dtype=int)
    if len(bonds):
        pad = np.abs(bonds.shift).max(axis=0)
        ranges = [range(-int(p), int(r) + int(p)) for p, r in zip(pad, reps_arr, strict=True)]
        t = np.array(list(itertools.product(*ranges)), dtype=int)  # candidate translations
        s = bonds.shift
        in_a = np.all((t >= 0) & (t < reps_arr), axis=1)  # (t,)
        end_b = t[:, None, :] + s[None, :, :]  # (t, m, 3)
        in_b = np.all((end_b >= 0) & (end_b < reps_arr), axis=2)  # (t, m)
        keep = in_a[:, None] | in_b
        ti, bi = np.nonzero(keep)
        a_cell, b_cell = t[ti], end_b[ti, bi]
        a_in, b_in = in_a[ti], in_b[ti, bi]
        atom_a, atom_b = bonds.i[bi], bonds.j[bi]

        def real_index(cell_t: np.ndarray, atom: np.ndarray) -> np.ndarray:
            linear = (cell_t[:, 0] * reps_arr[1] + cell_t[:, 1]) * reps_arr[2] + cell_t[:, 2]
            return linear * n + atom

        index_a = np.full(len(ti), -1, dtype=int)
        index_b = np.full(len(ti), -1, dtype=int)
        index_a[a_in] = real_index(a_cell[a_in], atom_a[a_in])
        index_b[b_in] = real_index(b_cell[b_in], atom_b[b_in])

        # Ghosts: one per distinct (atom, absolute translation) outside the block.
        gone_a, gone_b = ~a_in, ~b_in
        keys = np.vstack(
            [
                np.column_stack([atom_a[gone_a], a_cell[gone_a]]),
                np.column_stack([atom_b[gone_b], b_cell[gone_b]]),
            ]
        )
        if len(keys):
            unique, inverse = np.unique(keys, axis=0, return_inverse=True)
            inverse = inverse.reshape(-1)
            k_a = int(gone_a.sum())
            index_a[gone_a] = n_real + inverse[:k_a]
            index_b[gone_b] = n_real + inverse[k_a:]
            ghost_pos = (frac[unique[:, 0]] + unique[:, 1:]) @ cell
            ghost_species = structure.species_index[unique[:, 0]]
        bond_a, bond_b = index_a, index_b

    return Scene(
        positions=np.vstack([positions, ghost_pos]),
        species=np.concatenate([species, ghost_species]),
        refs=refs,
        n_real=n_real,
        original=original,
        bond_a=bond_a,
        bond_b=bond_b,
        cell=cell,
        frac=frac,
        reps=(int(reps_arr[0]), int(reps_arr[1]), int(reps_arr[2])),
    )
