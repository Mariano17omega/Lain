"""Structure data model: the shape of data that is ported to the host application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np

from viewer3d.core.elements import element_for_label


class AtomRef(NamedTuple):
    """Identity of an atom in the scene: input index plus lattice translation.

    The Cartesian position is ``(frac[index] + shift) @ cell``. Every selection and every
    measurement uses an ``AtomRef``, never the bare index.
    """

    index: int
    shift: tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True)
class StructureError:
    """Reading failed; ``message`` is a Portuguese sentence ready for the user."""

    message: str
    line: int | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class SpeciesInfo:
    label: str
    mass: float | None
    pseudo: str | None
    number: int  # 1-based, order in ATOMIC_SPECIES (QE ``ityp``)


@dataclass(frozen=True)
class SourceInfo:
    path: str | None = None
    ibrav: int = 0
    nat: int = 0
    ntyp: int | None = None
    prefix: str = "pwscf"
    calculation: str = "scf"
    nspin: int = 1
    alat_bohr: float | None = None
    celldm: tuple[float, ...] = (0.0,) * 6
    starting_magnetization: dict[int, float] = field(default_factory=dict)  # by species number
    hubbard_u: dict[int, float] = field(default_factory=dict)  # eV, by species number
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, eq=False)
class Structure:
    cell: np.ndarray  # (3, 3) Å, rows a1, a2, a3
    labels: tuple[str, ...]  # species label of each atom, input order
    frac: np.ndarray  # (n, 3) fractional coordinates, as given (not wrapped)
    flags: tuple[tuple[int, int, int] | None, ...]  # if_pos of each atom (None: not written)
    species: tuple[SpeciesInfo, ...]
    source: SourceInfo
    species_index: np.ndarray = field(init=False, repr=False)  # (n,) 0-based into ``species``

    def __post_init__(self) -> None:
        cell = np.array(self.cell, dtype=float).reshape(3, 3)
        frac = np.array(self.frac, dtype=float).reshape(-1, 3)
        cell.setflags(write=False)
        frac.setflags(write=False)
        if not (len(self.labels) == len(self.flags) == len(frac)):
            raise ValueError("labels, flags and frac must have the same length")
        by_label = {s.label: i for i, s in enumerate(self.species)}
        index = np.array([by_label[label] for label in self.labels], dtype=int)
        index.setflags(write=False)
        object.__setattr__(self, "cell", cell)
        object.__setattr__(self, "frac", frac)
        object.__setattr__(self, "species_index", index)

    def __len__(self) -> int:
        return len(self.labels)

    @property
    def cart(self) -> np.ndarray:
        """(n, 3) Cartesian positions in Å."""
        return self.frac @ self.cell

    def position(self, ref: AtomRef) -> np.ndarray:
        """Cartesian position (Å) of an atom copy."""
        return (self.frac[ref.index] + np.asarray(ref.shift, dtype=float)) @ self.cell

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(element_for_label(label).symbol for label in self.labels)

    @property
    def formula(self) -> str:
        """Hill-system formula, e.g. ``CH18Al8HgO36Si8``."""
        counts: dict[str, int] = {}
        for symbol in self.symbols:
            counts[symbol] = counts.get(symbol, 0) + 1
        if "C" in counts:
            order = ["C"] + (["H"] if "H" in counts else [])
            order += sorted(s for s in counts if s not in ("C", "H"))
        else:
            order = sorted(counts)
        return "".join(f"{s}{counts[s] if counts[s] > 1 else ''}" for s in order)

    @property
    def volume(self) -> float:
        return float(abs(np.linalg.det(self.cell)))

    @property
    def lattice_parameters(self) -> tuple[float, float, float, float, float, float]:
        """(a, b, c) in Å and (alpha, beta, gamma) in degrees."""
        lengths = np.linalg.norm(self.cell, axis=1)

        def angle(i: int, j: int) -> float:
            cosine = self.cell[i] @ self.cell[j] / (lengths[i] * lengths[j])
            return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))

        a, b, c = (float(x) for x in lengths)
        return a, b, c, angle(1, 2), angle(0, 2), angle(0, 1)
