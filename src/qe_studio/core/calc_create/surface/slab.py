"""A slab from the bulk: one axis stretched to open vacuum (spec 40 R3, port of ``make_surface``).

The plane is two axes of the bulk cell, ``(a, b)``, ``(a, c)`` or ``(b, c)``; the third (the *stacked*
axis ``s``) is multiplied by ``f`` so that the vacuum above the layer is the one asked for, and the
layer keeps the bulk's geometry. ``flip`` takes the second axis of the plane with a minus sign (the
script's ``t1_sign = -1``), which turns the surface upside down. Before stretching:

- ``heal``: an H whose bond to its nearest bonded neighbour crosses the stacked axis is moved next
  to it (the script only knew O–H);
- ``complete``: each bond of a ``metals`` atom to an O that crosses the stacked axis gets a new O at
  the missing vertex and an H at the bulk's mean O–H length, along metal → O.

Then the cell ``{t0, t1, f·s}`` is turned rigidly so that ``t0`` lies along +x and the normal along +z,
and the fractions along the vacuum axis are centred on 0.5. Atoms keep the bulk's order; the added
ones go last, in O, H pairs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ....i18n import _
from . import SurfaceError
from .elements import covalent_radius, element_of
from .geometry import pair_images
from .model import Model

__all__ = ["AXES", "HKL", "Added", "Healed", "SlabOptions", "SlabResult", "make_slab"]

AXES: dict[str, tuple[tuple[int, int], int]] = {
    "c": ((0, 1), 2),
    "b": ((0, 2), 1),
    "a": ((1, 2), 0),
}
HKL = {"c": "001", "b": "010", "a": "100"}
NEED_O_H = _("Completar poliedros precisa de O e H no SCF")
NO_BULK_H = _("Completar poliedros: sem H no bulk para medir o O–H")


@dataclass(frozen=True)
class SlabOptions:
    axis: str = "c"  # the stacked axis of the bulk: "a", "b" or "c"
    flip: bool = False
    vacuum: float = 10.5  # Å, perpendicular, above the layer
    heal: bool = True
    complete: bool = False
    metals: tuple[str, ...] = ("Al", "Si")  # labels
    bond_scale: float = 1.15


@dataclass(frozen=True)
class Healed:
    h: int  # 0-based
    partner: int
    distance: float  # Å


@dataclass(frozen=True)
class Added:
    metal: int  # 0-based, in the bulk
    partner: int  # the bulk O whose image is the missing vertex
    distance: float  # Å, metal–O
    oxygen: int  # 0-based in the slab
    hydrogen: int


@dataclass(frozen=True, eq=False)
class SlabResult:
    model: Model
    f: float  # the stacked axis of the bulk times f is the slab's third axis
    axis_map: dict[int, int]  # slab axis (0, 1) → the bulk axis it comes from
    stack: int  # the bulk axis that was stretched
    thickness: float  # Å along the normal
    healed: tuple[Healed, ...] = ()
    added: tuple[Added, ...] = ()
    cut_bonds: dict[str, int] = field(default_factory=dict)  # label → bonds to O the cut breaks
    notes: tuple[str, ...] = ()


def _elements(labels: Sequence[str]) -> list[str]:
    return [element_of(label) for label in labels]


def _heal(
    bulk: Model, elements: list[str], radii: np.ndarray, stack: int, scale: float, cart: np.ndarray
) -> tuple[list[Healed], list[str]]:
    """Move each H whose bond crosses the stacked axis next to its partner (in ``cart``)."""
    hydrogens = [i for i, element in enumerate(elements) if element == "H"]
    if not hydrogens:
        return [], []
    everyone = list(range(len(bulk)))
    # rows: the partners, cols: the H, so the image is that of frac[h] − frac[partner], as the script
    distances, images = pair_images(bulk.frac, bulk.cell, everyone, hydrogens)
    healed, notes = [], []
    for col, h in enumerate(hydrogens):
        cutoffs = scale * (radii[h] + radii)
        column = distances[:, col].copy()
        column[h] = np.inf
        column[column > cutoffs] = np.inf
        partner = int(np.argmin(column))
        if not np.isfinite(column[partner]):
            notes.append(_("H {value} sem vizinho ligado: não reconectado").format(value=h + 1))
            continue
        image = images[partner, col]
        if image[stack] != 0:
            delta = bulk.frac[h] - bulk.frac[partner] + image
            cart[h] = cart[partner] + delta @ bulk.cell
            healed.append(Healed(h, partner, float(column[partner])))
    return healed, notes


def _crossing(
    bulk: Model, elements: list[str], radii: np.ndarray, stack: int, scale: float
) -> list[tuple[int, int, float, np.ndarray]]:
    """The bonds X–O (X neither O nor H, ``<=``) whose minimum image crosses the stacked axis: (X, O,
    length, image of frac[O] − frac[X]), X then O ascending."""
    oxygens = [i for i, element in enumerate(elements) if element == "O"]
    others = [i for i, element in enumerate(elements) if element not in ("O", "H")]
    if not oxygens or not others:
        return []
    distances, images = pair_images(bulk.frac, bulk.cell, others, oxygens)
    found = []
    for row, atom in enumerate(others):
        for col, oxygen in enumerate(oxygens):
            cutoff = scale * (radii[atom] + radii[oxygen])
            image = images[row, col]
            if distances[row, col] <= cutoff and image[stack] != 0:
                found.append((atom, oxygen, float(distances[row, col]), image))
    return found


def _bulk_oh_length(bulk: Model, elements: list[str]) -> float:
    """The mean O–H length of the bulk (each H to its nearest O, minimum image)."""
    oxygens = [i for i, element in enumerate(elements) if element == "O"]
    hydrogens = [i for i, element in enumerate(elements) if element == "H"]
    distances, __ = pair_images(bulk.frac, bulk.cell, oxygens, hydrogens)
    return float(np.mean(distances.min(axis=0)))


def _complete(
    bulk: Model,
    elements: list[str],
    crossing: list[tuple[int, int, float, np.ndarray]],
    options: SlabOptions,
    species: Sequence[str],
    cart: np.ndarray,
) -> tuple[np.ndarray, list[str], list[Added]]:
    species_elements = {element_of(label) for label in species}
    if not {"O", "H"} <= species_elements or "O" not in elements:
        raise SurfaceError(NEED_O_H)
    if "H" not in elements:
        raise SurfaceError(NO_BULK_H)
    oh_length = _bulk_oh_length(bulk, elements)
    h_label = bulk.labels[elements.index("H")]
    points, labels, added = [], [], []
    count = len(bulk)
    for metal in options.metals:
        for atom, oxygen, length, image in crossing:
            if bulk.labels[atom] != metal:
                continue
            new_o = cart[atom] + (bulk.frac[oxygen] - bulk.frac[atom] + image) @ bulk.cell
            out = new_o - cart[atom]
            points += [new_o, new_o + oh_length * out / np.linalg.norm(out)]
            labels += [bulk.labels[oxygen], h_label]
            added.append(Added(atom, oxygen, length, count, count + 1))
            count += 2
    if not points:
        return cart, list(bulk.labels), []
    return np.vstack([cart, np.array(points)]), [*bulk.labels, *labels], added


def _frame(v0: np.ndarray, v1: np.ndarray) -> np.ndarray:
    """Right-handed orthonormal columns: e0 along v0, e2 along v0 × v1."""
    e0 = v0 / np.linalg.norm(v0)
    e2 = np.cross(v0, v1)
    e2 /= np.linalg.norm(e2)
    return np.column_stack([e0, np.cross(e2, e0), e2])


def make_slab(
    bulk: Model, options: SlabOptions, species: Sequence[str] | None = None
) -> SlabResult:
    """The slab of ``bulk``; ``species`` are the labels of ``ATOMIC_SPECIES`` (None: the bulk's).
    Raises ``SurfaceError``."""
    if options.axis not in AXES:
        raise SurfaceError(_("Eixo de superfície desconhecido: {axis}").format(axis=options.axis))
    if options.vacuum <= 0:
        raise SurfaceError(_("O vácuo deve ser maior que zero"))
    (first, second), stack = AXES[options.axis]
    lattice = bulk.cell
    t0 = lattice[first]
    t1 = (-1.0 if options.flip else 1.0) * lattice[second]
    s = lattice[stack]
    elements = _elements(bulk.labels)
    radii = np.array([covalent_radius(label) for label in bulk.labels])
    cart = bulk.cart.copy()
    healed: list[Healed] = []
    notes: list[str] = []
    if options.heal:
        healed, notes = _heal(bulk, elements, radii, stack, options.bond_scale, cart)
    crossing = _crossing(bulk, elements, radii, stack, options.bond_scale)
    cut_bonds: dict[str, int] = {}
    for atom, *_rest in crossing:
        cut_bonds[bulk.labels[atom]] = cut_bonds.get(bulk.labels[atom], 0) + 1
    labels, added = list(bulk.labels), []
    if options.complete:
        cart, labels, added = _complete(
            bulk, elements, crossing, options, species or bulk.labels, cart
        )

    frame = _frame(t0, t1)
    normal = frame[:, 2]
    heights = cart @ normal
    thickness = float(heights.max() - heights.min())
    along = float(np.dot(s, normal))
    if abs(along) < 1e-9:
        raise SurfaceError(_("O eixo empilhado está no plano da superfície"))
    f = (thickness + options.vacuum) / abs(along)
    third = f * s
    if np.dot(normal, third) < 0.0:  # keep the cell right-handed: the vacuum side is +third
        third = -third
    cell = np.array([t0, t1, third]) @ frame
    if np.linalg.det(cell) <= 0:
        raise SurfaceError(_("A célula do slab ficou com volume ≤ 0"))
    frac = (cart @ frame) @ np.linalg.inv(cell)
    frac[:, 2] = (frac[:, 2] - frac[:, 2].mean() + 0.5) % 1.0  # the slab in the middle of the box
    flags = tuple(bulk.flag(i) if i < len(bulk) else None for i in range(len(labels)))
    model = Model(cell, tuple(labels), frac, flags)
    return SlabResult(
        model,
        float(f),
        {0: first, 1: second},
        stack,
        thickness,
        tuple(healed),
        tuple(added),
        cut_bonds,
        tuple(notes),
    )
