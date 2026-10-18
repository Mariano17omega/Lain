"""A molecule on a surface atom, or between two (spec 42 R3, port of ``qe_slab_adsorb``).

The site is one atom of the surface (monodentado) or two (bidentado), picked in the candidates' table
or by fractional coordinates, which choose the nearest atom within a tolerance (``site_atoms``); it must
lie in the height window of the candidates and be of their species. With ``remove_h`` the one H bonded
to each anchor atom goes first (``remove_bonded_h``: the surface O–H is deprotonated and the molecule
takes the proton's place). Then ``place`` puts the molecule's anchor above the site, as the scripts do:

- the start ``P`` is the atom, or the middle of the first atom and the image of the second nearest to it
  among the 3 × 3 in-plane images;
- for every surface atom ``j`` of those images at an in-plane distance ``r_j < d`` from ``P``, the anchor
  must be at least ``d`` from it: its height is ``t = max(h_P + d (mono) | h_P (bi), h_j + √(d² − r_j²))``
  along the normal, which for one atom is the scripts' ontop site (``AdsorbateSiteFinder``);
- the molecule (``molecule_of``: anchor at the origin, axis along +z) is turned from +z onto the normal
  and its atoms follow the surface's, in the order of its SCF, with no ``if_pos`` flags.

A contact of the anchor closer than ``MIN_CONTACT`` is an error; a small clearance or vacuum is a note
(the relax adjusts it). Atoms are numbered from 1 in messages, in the SCF's numbering. Qt-free.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ....i18n import _
from ...qe.pw_input import fortran_float
from . import SurfaceError
from .candidates import matches_species, surface_frame, top_indices
from .elements import covalent_radius, element_of
from .geometry import pair_images
from .model import Model
from .molecule import Molecule, rotation_from_z
from .report import decimal

__all__ = [
    "MIN_CONTACT",
    "REMOVE_H_LABEL",
    "Adsorbed",
    "SiteError",
    "SiteRequest",
    "adsorb",
    "parse_coords",
    "remove_bonded_h",
    "site_atoms",
]

MIN_CONTACT = 1.5  # Å: an anchor closer than this to a surface atom is refused
REMOVE_H_LABEL = _("Remover o H ligado ao átomo âncora")
SHIFTS = tuple(
    (i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)
)  # in-plane images, the scripts' order
_SEPARATORS = re.compile(r"[\s;]+")


class SiteError(SurfaceError):
    """A problem of the site; ``role`` says which input caused it: ``selection`` (the marks of the
    table), ``first`` / ``second`` (the coordinates), ``deprotonation`` or ``distance``."""

    def __init__(self, text: str, role: str):
        super().__init__(text)
        self.role = role


@dataclass(frozen=True)
class SiteRequest:
    bidentate: bool = False
    marked: tuple[int, ...] = ()  # 1-based: the atoms marked in the table
    coords: tuple[str, ...] | None = None  # "x y z" (fractional) per atom; None: from the table
    tol: float = 0.5  # Å between the coordinates and the atom they choose
    window: float = 1.5  # Å below the top: the surface
    species: tuple[str, ...] = ("O",)


@dataclass(frozen=True, eq=False)
class Adsorbed:
    model: Model = field(repr=False)  # the surface (as written) and then the molecule
    unwrapped: Model = field(repr=False)  # the same atoms, the surface contiguous along c
    n_slab: int
    numbers: tuple[int, ...]  # the SCF's number of each surface atom kept (1-based)
    sites: tuple[int, ...]  # the site atoms, SCF numbering (1-based)
    removed: tuple[int, ...]  # the H removed, SCF numbering (1-based)
    anchor: int  # 0-based in ``model``
    lift: float  # Å the anchor rose above its start (h_P + d, or h_P between two atoms)
    site_distances: tuple[float, ...]  # anchor to each site atom, Å
    anchor_h: float | None  # anchor to the nearest surface H, Å
    clearance: float | None  # the rest of the molecule to the surface, Å
    vacuum: float  # Å above the molecule, along the normal
    notes: tuple[str, ...] = ()


def parse_coords(text: str) -> np.ndarray | None:
    """``"0.23 0.67 0.58"`` (or with decimal commas, or ``;``) as three numbers; None otherwise."""
    words = [word for word in _SEPARATORS.split(text.strip()) if word]
    if len(words) != 3:
        return None
    values = [fortran_float(word.replace(",", ".")) for word in words]
    if any(value is None or not math.isfinite(value) for value in values):
        return None
    return np.array(values, dtype=float)


def _name(model: Model, index: int, numbers: Sequence[int] | None = None) -> str:
    """``O 43``: the species label and the SCF's number."""
    number = numbers[index] if numbers is not None else index + 1
    return f"{model.labels[index]} {number}"


def _number_text(values: np.ndarray) -> str:
    return " ".join(f"{value:g}".replace(".", ",") for value in values)


def _match(model: Model, text: str, tol: float, which: int) -> int:
    """The atom (0-based) nearest to the coordinates ``text``, by minimum image."""
    role = ("first", "second")[which]
    point = parse_coords(text)
    if point is None:
        raise SiteError(
            _("Coordenadas do átomo {value}: escreva três números, x y z").format(value=which + 1),
            role,
        )
    frac = np.vstack([model.frac, point])
    distances, __ = pair_images(frac, model.cell, [len(model)], range(len(model)))
    index = int(np.argmin(distances[0]))
    distance = float(distances[0, index])
    if distance > tol:
        raise SiteError(
            _(
                "As coordenadas {number_text} estão a {decimal} Å do átomo mais próximo ({name}): nenhum átomo a até {decimal_2} Å"
            ).format(
                number_text=_number_text(point),
                decimal=decimal(distance, 1),
                name=_name(model, index),
                decimal_2=decimal(tol, 1),
            ),
            role,
        )
    return index


def site_atoms(model: Model, request: SiteRequest) -> tuple[int, ...]:
    """The site atoms (1-based, in the order asked). Raises ``SiteError``."""
    need = 2 if request.bidentate else 1
    if request.coords is None:
        marked = tuple(request.marked)
        if len(marked) != need:
            ask = (
                _("Bidentado: marque dois átomos")
                if need == 2
                else _("Monodentado: marque um átomo")
            )
            raise SiteError(
                _("{ask} da lista (marcados: {count})").format(ask=ask, count=len(marked)),
                "selection",
            )
        atoms = [number - 1 for number in marked]
        roles = ["selection"] * need
    else:
        texts = (*request.coords, "", "")[:need]
        atoms = [_match(model, text, request.tol, k) for k, text in enumerate(texts)]
        roles = ["first", "second"][:need]
    top = set(top_indices(surface_frame(model).heights, request.window))
    for index, role in zip(atoms, roles, strict=True):
        if not 0 <= index < len(model):
            raise SiteError(
                _("O átomo {value} não existe (1 a {count})").format(
                    value=index + 1, count=len(model)
                ),
                role,
            )
        label = model.labels[index]
        if index not in top:
            raise SiteError(
                _("O átomo {value} ({label}) não está na superfície").format(
                    value=index + 1, label=label
                ),
                role,
            )
        if not matches_species(label, request.species):
            raise SiteError(
                _("O átomo {value} ({label}) não é de {join}").format(
                    value=index + 1, label=label, join=", ".join(request.species)
                ),
                role,
            )
    if need == 2 and atoms[0] == atoms[1]:
        raise SiteError(
            _("Bidentado: os dois átomos são o mesmo ({name})").format(name=_name(model, atoms[0])),
            roles[1],
        )
    return tuple(index + 1 for index in atoms)


def remove_bonded_h(
    model: Model, sites: Sequence[int], bond_scale: float
) -> tuple[Model, tuple[int, ...], tuple[int, ...]]:
    """``model`` without the one H bonded to each site atom (1-based ``sites``): the new model, the H
    removed (1-based, ascending) and the SCF's number of every atom kept. Raises ``SiteError``."""
    hydrogens = [i for i, label in enumerate(model.labels) if element_of(label) == "H"]
    chosen: dict[int, int] = {}  # H → the site atom it leaves
    for number in sites:
        anchor = number - 1
        bonded: list[int] = []
        if hydrogens:
            distances, __ = pair_images(model.frac, model.cell, [anchor], hydrogens)
            radius = covalent_radius(model.labels[anchor])
            bonded = [
                h
                for h, distance in zip(hydrogens, distances[0], strict=True)
                if distance < bond_scale * (radius + covalent_radius(model.labels[h]))
            ]
        if len(bonded) != 1:
            raise SiteError(
                _("{name} tem {count} H ligados: desmarque '{REMOVE_H_LABEL}'").format(
                    name=_name(model, anchor), count=len(bonded), REMOVE_H_LABEL=REMOVE_H_LABEL
                ),
                "deprotonation",
            )
        h = bonded[0]
        if h in chosen:
            raise SiteError(
                _(
                    "{name} e {name_2} estão ligados ao mesmo H ({name_3}): não dá para remover os dois"
                ).format(
                    name=_name(model, chosen[h]),
                    name_2=_name(model, anchor),
                    name_3=_name(model, h),
                ),
                "deprotonation",
            )
        chosen[h] = anchor
    keep = [i for i in range(len(model)) if i not in chosen]
    reduced = Model(
        model.cell,
        tuple(model.labels[i] for i in keep),
        model.frac[keep],
        tuple(model.flag(i) for i in keep),
    )
    return reduced, tuple(sorted(h + 1 for h in chosen)), tuple(i + 1 for i in keep)


def _start(frame_cart: np.ndarray, cell: np.ndarray, sites: Sequence[int]) -> np.ndarray:
    """``P``: the atom, or the middle of the first and the nearest in-plane image of the second."""
    first = frame_cart[sites[0]]
    if len(sites) == 1:
        return first.copy()
    images = np.array([frame_cart[sites[1]] + i * cell[0] + j * cell[1] for i, j in SHIFTS])
    second = images[int(np.argmin(np.linalg.norm(images - first, axis=1)))]
    return 0.5 * (first + second)


def _height(frame_cart: np.ndarray, cell: np.ndarray, normal: np.ndarray, point, start, d):
    """The anchor's height: ``start``, raised until every surface atom (3 × 3 in-plane images) is at
    least ``d`` away."""
    shifts = np.array([i * cell[0] + j * cell[1] for i, j in SHIFTS])
    images = (frame_cart[None, :, :] + shifts[:, None, :]).reshape(-1, 3)
    relative = images - point
    along = relative @ normal
    planar = np.einsum("ij,ij->i", relative, relative) - along**2
    near = planar < d * d
    if not near.any():
        return start
    reach = images[near] @ normal + np.sqrt(d * d - planar[near])
    return max(start, float(reach.max()))


def _place(
    model: Model, sites: Sequence[int], molecule: Molecule, distance: float
) -> tuple[Model, Model, float, int]:
    """The surface plus the molecule, its unwrapped twin, the lift and the anchor (0-based)."""
    frame = surface_frame(model)
    cell, normal = np.asarray(model.cell, float), frame.normal
    point = _start(frame.cart, cell, sites)
    h_point = float(point @ normal)
    start = h_point + distance if len(sites) == 1 else h_point
    height = _height(frame.cart, cell, normal, point, start, distance)
    anchor_pos = point + (height - h_point) * normal
    coords = molecule.coords @ rotation_from_z(normal).T + anchor_pos
    mol_frac = coords @ np.linalg.inv(cell)
    labels = model.labels + molecule.labels
    flags = tuple(model.flag(i) for i in range(len(model))) + (None,) * len(molecule.labels)
    written = Model(cell, labels, np.vstack([model.frac, mol_frac]), flags)
    unwrapped = written.replace(frac=np.vstack([frame.frac, mol_frac]))
    return written, unwrapped, height - start, len(model) + molecule.anchor


def _checks(
    placed: Model,
    unwrapped: Model,
    n_slab: int,
    anchor: int,
    numbers: Sequence[int],
    h_clearance: float,
    vacuum_min: float,
) -> tuple[float | None, float | None, float, list[str]]:
    """Raises ``SiteError`` on a contact; the clearances, the vacuum and their notes."""
    rows = list(range(n_slab, len(placed)))
    distances, __ = pair_images(placed.frac, placed.cell, rows, range(n_slab))
    by_anchor = distances[anchor - n_slab]
    nearest = int(np.argmin(by_anchor))
    if by_anchor[nearest] < MIN_CONTACT:
        raise SiteError(
            _("O âncora fica a {decimal} Å de {name}: aumente a distância de adsorção").format(
                decimal=decimal(float(by_anchor[nearest]), 1), name=_name(placed, nearest, numbers)
            ),
            "distance",
        )
    hydrogens = [j for j in range(n_slab) if element_of(placed.labels[j]) == "H"]
    anchor_h = float(by_anchor[hydrogens].min()) if hydrogens else None
    others = [k for k, row in enumerate(rows) if row != anchor]
    clearance = float(distances[others].min()) if others else None
    notes: list[str] = []
    short = [
        (text, value)
        for text, value in ((_("âncora···H"), anchor_h), (_("molécula–superfície"), clearance))
        if value is not None and value < h_clearance
    ]
    if short:
        parts = ", ".join(f"{text} {decimal(value)} Å" for text, value in short)
        notes.append(
            _("Folga abaixo de {decimal} Å: {parts}; o relax ajusta").format(
                decimal=decimal(h_clearance, 1), parts=parts
            )
        )
    normal = surface_frame(unwrapped).normal
    heights = unwrapped.cart @ normal
    vacuum = abs(float(unwrapped.cell[2] @ normal)) - float(np.ptp(heights))
    if vacuum < vacuum_min:
        notes.append(
            _("Vácuo de {decimal} Å acima da molécula, abaixo do mínimo de {decimal_2} Å").format(
                decimal=decimal(vacuum, 1), decimal_2=decimal(vacuum_min, 1)
            )
        )
    return anchor_h, clearance, vacuum, notes


def adsorb(
    model: Model,
    request: SiteRequest,
    molecule: Molecule,
    *,
    remove_h: bool = False,
    distance: float = 2.0,
    h_clearance: float = 1.9,
    vacuum_min: float = 10.5,
    bond_scale: float = 1.15,
) -> Adsorbed:
    """The molecule on the site ``request`` asks for. Raises ``SiteError``."""
    sites = site_atoms(model, request)
    removed: tuple[int, ...] = ()
    numbers = tuple(range(1, len(model) + 1))
    surface = model
    if remove_h:
        surface, removed, numbers = remove_bonded_h(model, sites, bond_scale)
    new_sites = [numbers.index(number) for number in sites]
    placed, unwrapped, lift, anchor = _place(surface, new_sites, molecule, distance)
    n_slab = len(surface)
    anchor_h, clearance, vacuum, notes = _checks(
        placed, unwrapped, n_slab, anchor, numbers, h_clearance, vacuum_min
    )
    distances, __ = pair_images(placed.frac, placed.cell, [anchor], new_sites)
    return Adsorbed(
        placed,
        unwrapped,
        n_slab,
        numbers,
        sites,
        removed,
        anchor,
        lift,
        tuple(float(d) for d in distances[0]),
        anchor_h,
        clearance,
        vacuum,
        tuple(notes),
    )
