"""The surface atoms a molecule can sit on (spec 42 R2, port of ``qe_slab_candidates``).

The top of a slab is a height window along the surface normal (``top_atoms``): the atoms at most
``window`` Å below the highest one, the rule the scripts use instead of ``Slab.get_surface_sites``
(by coordination, which finds no site on these slabs). The normal is the unit vector of a1 × a2 on the side of a3, and the heights
are measured with the slab made contiguous along c (``surface_frame``: the fractions are unwrapped in
the middle of the widest empty gap), so a slab written across the edge of the cell has the same top.

``candidates`` lists the window's atoms of the species asked for, each with the group of atoms that
spglib finds equivalent by symmetry over the whole structure (types by species *label*, as pw.x tells
species apart), how many of that group are in the window and its bonded neighbours. spglib is imported
on first use only. Qt-free.
"""

from __future__ import annotations

import functools
import string
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ....i18n import _
from ..scf_info import ScfInfo, scf_info
from .elements import covalent_radius, element_of
from .geometry import pair_images
from .model import Model, model_of
from .report import decimal

__all__ = [
    "Candidate",
    "Frame",
    "candidate_note",
    "candidates",
    "candidates_for",
    "matches_species",
    "no_candidates_text",
    "surface_frame",
    "top_atoms",
    "top_indices",
]


@dataclass(frozen=True, eq=False)
class Frame:
    """The structure seen from its surface: the slab contiguous along c."""

    normal: np.ndarray = field(repr=False)  # unit, a1 × a2 with n · a3 > 0
    frac: np.ndarray = field(repr=False)  # (n, 3): c unwrapped in the middle of the widest gap
    cart: np.ndarray = field(repr=False)  # (n, 3) Å
    heights: np.ndarray = field(repr=False)  # cart · normal


@dataclass(frozen=True)
class Candidate:
    index: int  # 1-based, the SCF's numbering
    label: str
    frac: tuple[float, float, float]  # as written in the SCF
    group: str  # A, B, C…: same letter, equivalent by symmetry
    multiplicity: int  # atoms of the group inside the window
    neighbors: tuple[tuple[str, float], ...] = ()  # (label, Å) bonded, nearest first


def surface_frame(model: Model) -> Frame:
    cell = np.asarray(model.cell, float)
    normal = np.cross(cell[0], cell[1])
    normal = normal / np.linalg.norm(normal)
    if float(normal @ cell[2]) < 0:
        normal = -normal
    frac = np.array(model.frac, float).reshape(-1, 3)
    if len(frac):
        values = frac[:, 2] % 1.0
        ordered = np.sort(values)
        steps = np.diff(np.append(ordered, ordered[0] + 1.0))
        widest = int(np.argmax(steps))
        cut = (ordered[widest] + steps[widest] / 2) % 1.0
        unwrapped = (values - cut) % 1.0 + cut  # from the cut up: contiguous
        frac[:, 2] = unwrapped - np.floor(unwrapped.min())  # the bottom in [0, 1)
    cart = frac @ cell
    return Frame(normal, frac, cart, cart @ normal)


def top_indices(heights: np.ndarray, window: float) -> list[int]:
    """The atoms (0-based, ascending) at most ``window`` Å below the highest."""
    if not len(heights):
        return []
    return np.flatnonzero(heights >= heights.max() - window).tolist()


def top_atoms(model: Model, window: float) -> list[int]:
    """``top_indices`` of ``model``'s surface frame."""
    return top_indices(surface_frame(model).heights, window)


def matches_species(label: str, species: Sequence[str]) -> bool:
    """Whether the species label, or its element, is one of ``species``."""
    return label in species or element_of(label) in species


def _equivalent(model: Model, symprec: float) -> np.ndarray:
    """For each atom, the first atom of its symmetry group (each its own when spglib finds nothing)."""
    import spglib

    kinds = {label: number for number, label in enumerate(dict.fromkeys(model.labels), 1)}
    cell = (model.cell.tolist(), model.frac.tolist(), [kinds[label] for label in model.labels])
    try:
        with warnings.catch_warnings():  # 2.x warns about its error handling at every call
            warnings.simplefilter("ignore", DeprecationWarning)
            dataset = spglib.get_symmetry_dataset(cell, symprec=symprec)
    except spglib.SpglibError:
        dataset = None
    if dataset is None:
        return np.arange(len(model))
    return np.asarray(dataset.equivalent_atoms)


def _letter(number: int) -> str:
    """0 → A, 25 → Z, 26 → AA: the name of a group."""
    name = ""
    number += 1
    while number:
        number, rest = divmod(number - 1, 26)
        name = string.ascii_uppercase[rest] + name
    return name


def _neighbors(model: Model, rows: list[int], scale: float) -> list[tuple[tuple[str, float], ...]]:
    count = len(model)
    distances, __ = pair_images(model.frac, model.cell, rows, range(count))
    radii = np.array([covalent_radius(label) for label in model.labels])
    out = []
    for k, i in enumerate(rows):
        cut = scale * (radii[i] + radii)
        bonded = [j for j in np.argsort(distances[k], kind="stable") if j != i]
        out.append(
            tuple(
                (model.labels[j], float(distances[k, j]))
                for j in bonded
                if distances[k, j] < cut[j]
            )
        )
    return out


def candidates(
    model: Model,
    species: Sequence[str],
    window: float,
    symprec: float,
    bond_scale: float,
) -> tuple[Candidate, ...]:
    """The window's atoms whose label or element is in ``species``, in the SCF's order. Raises
    ``SurfaceError`` for a label of no known element."""
    top = top_atoms(model, window)
    chosen = [i for i in top if matches_species(model.labels[i], species)]
    if not chosen:
        return ()
    equivalent = _equivalent(model, symprec)
    members: dict[int, list[int]] = {}
    for i in top:
        members.setdefault(int(equivalent[i]), []).append(i)
    keys = sorted({int(equivalent[i]) for i in chosen}, key=lambda key: members[key][0])
    letter = {key: _letter(k) for k, key in enumerate(keys)}
    neighbors = _neighbors(model, chosen, bond_scale)
    return tuple(
        Candidate(
            i + 1,
            model.labels[i],
            (float(model.frac[i, 0]), float(model.frac[i, 1]), float(model.frac[i, 2])),
            letter[int(equivalent[i])],
            len(members[int(equivalent[i])]),
            near,
        )
        for i, near in zip(chosen, neighbors, strict=True)
    )


@functools.lru_cache(maxsize=16)
def _cached(
    text: str, species: tuple[str, ...], window: float, symprec: float, scale: float
) -> tuple[Candidate, ...]:
    return candidates(model_of(scf_info(text)), species, window, symprec, scale)


def candidates_for(
    scf: ScfInfo, species: Sequence[str], window: float, symprec: float, bond_scale: float
) -> tuple[Candidate, ...]:
    """``candidates`` of the SCF's structure, cached by its text and the parameters: the window plans
    at every edit. Raises ``SurfaceError`` (an unreadable structure, a label of no element)."""
    if scf.crystal is None:
        model_of(scf)  # raises with the structure's problem
    return _cached(scf.text, tuple(species), float(window), float(symprec), float(bond_scale))


def candidate_note(candidate: Candidate) -> str:
    """``A (4) · H 0.97 · Al 1.91``: the group, how many in the window and the bonded neighbours."""
    near = "".join(f" · {label} {decimal(distance)}" for label, distance in candidate.neighbors)
    return f"{candidate.group} ({candidate.multiplicity}){near}"


def no_candidates_text(species: Sequence[str], window: float) -> str:
    return _("Nenhum átomo de {join} a até {decimal} Å do topo").format(
        join=", ".join(species), decimal=decimal(window, 1)
    )
