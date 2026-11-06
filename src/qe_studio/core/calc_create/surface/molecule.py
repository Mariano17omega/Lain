"""A molecule from its own SCF (spec 40 R2.6): the anchor at the origin and the axis along +z.

As ``build_molecule`` of the user's scripts: the anchor is the heaviest atom (the first on a tie) or
the one given, by its number or its label (``anchor_index``, spec 75 R3), and the axis goes from it to
the first atom that is neither H nor the anchor (else to the centroid of the others). The positions are
unwrapped around the anchor first (a molecule cut by the edge of its box comes out whole). An axis
already within ``ALIGNED`` of +z is kept as written; any other is rotated onto +z (the script stops
there). ``extent`` is the height along z. ``anchor_choices`` is the window's list of them (spec 87 R1).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ....i18n import _
from ..scf_info import ScfInfo
from . import SurfaceError
from .elements import atomic_number, element_of
from .geometry import pair_images
from .model import model_of

__all__ = [
    "ALIGNED",
    "AnchorChoice",
    "Molecule",
    "anchor_choices",
    "anchor_index",
    "molecule_of",
    "rotation_from_z",
]

ALIGNED = 0.98  # the z component of the unit axis above which it is left alone (the script's limit)
_NUMBER = re.compile(r"[0-9]+")
_LABEL_NUMBER = re.compile(r"(.*?)([0-9]+)")


@dataclass(frozen=True, eq=False)
class Molecule:
    labels: tuple[str, ...]
    coords: np.ndarray = field(repr=False)  # (n, 3) Å, the anchor at the origin
    anchor: int  # 0-based
    extent: float  # Å along z
    rotated: bool = False


@dataclass(frozen=True)
class AnchorChoice:
    text: str  # as the list shows it
    value: str  # what ``anchor_index`` reads; "": the heaviest


def _rotation_onto_z(axis: np.ndarray) -> np.ndarray:
    """The smallest rotation (Rodrigues) taking the unit vector ``axis`` onto +z."""
    z = np.array([0.0, 0.0, 1.0])
    cross, cos = np.cross(axis, z), float(np.dot(axis, z))
    sin = float(np.linalg.norm(cross))
    if sin < 1e-12:
        return np.eye(3) if cos > 0 else np.diag([1.0, -1.0, -1.0])
    k = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    return np.eye(3) + k + k @ k * ((1 - cos) / sin**2)


def rotation_from_z(normal: np.ndarray) -> np.ndarray:
    """The smallest rotation taking +z onto the unit vector ``normal`` (a molecule along +z stands
    on a surface whose normal is ``normal``); the identity for +z."""
    return _rotation_onto_z(np.asarray(normal, float)).T


def _axis(labels: tuple[str, ...], coords: np.ndarray, anchor: int) -> np.ndarray | None:
    heavy = [k for k, label in enumerate(labels) if k != anchor and element_of(label) != "H"]
    if heavy:
        vector = coords[heavy[0]]
    elif len(labels) > 1:
        vector = np.delete(coords, anchor, axis=0).mean(axis=0)
    else:
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-8 else None


def _numbered(number: int, count: int) -> int:
    """The atom ``number`` (1-based) as an index, or ``SurfaceError`` outside 1 to ``count``."""
    if not 1 <= number <= count:
        raise SurfaceError(
            _("Átomo âncora {anchor} fora da molécula (1 a {count})").format(
                anchor=number, count=count
            )
        )
    return number - 1


def anchor_index(labels: Sequence[str], text: str) -> int | None:
    """The anchor typed (0-based), None when empty (the heaviest): a number in the order of the SCF's
    ``ATOMIC_POSITIONS``, a label that appears once (any case) or a label and a number (``H4``: atom
    4, which must be an H). The whole label is tried first: ``Fe1`` is a label before it is atom 1 of
    ``Fe``. Raises ``SurfaceError``."""
    typed = text.strip()
    if not typed:
        return None
    if _NUMBER.fullmatch(typed):
        return _numbered(int(typed), len(labels))
    same = [i for i, label in enumerate(labels) if label.lower() == typed.lower()]
    if len(same) == 1:
        return same[0]
    if same:
        label, first = labels[same[0]], same[0] + 1
        raise SurfaceError(
            _(
                "O rótulo {label} aparece em {count} átomos ({numbers}): use o número ou {label}{first}"
            ).format(
                label=label,
                count=len(same),
                numbers=", ".join(str(i + 1) for i in same),
                first=first,
            )
        )
    split = _LABEL_NUMBER.fullmatch(typed)
    if split is not None:
        asked = split.group(1).strip().lower()
        kind = next((label for label in labels if label.lower() == asked), None)
        if kind is not None:
            index = _numbered(int(split.group(2)), len(labels))
            if labels[index].lower() != asked:
                raise SurfaceError(
                    _("O átomo {number} é {label}, não {asked}").format(
                        number=index + 1, label=labels[index], asked=kind
                    )
                )
            return index
    raise SurfaceError(
        _("Nenhum átomo {text} na molécula (rótulos: {labels})").format(
            text=typed, labels=", ".join(dict.fromkeys(labels))
        )
    )


def _heaviest(labels: Sequence[str]) -> int:
    """The anchor when none is given (0-based): the heaviest, the first on a tie. Raises
    ``SurfaceError`` for a label of no known element."""
    return int(np.argmax([atomic_number(label) for label in labels]))


def anchor_choices(scf: ScfInfo | None) -> tuple[AnchorChoice, ...]:
    """The list of the anchor for the molecule's SCF: the automatic one first (it names the atom when
    it can), then one per atom in the SCF's order, by number since a label may repeat (``H 3``, ``H 4``).
    Only the automatic one without a molecule or with a structure that cannot be read. Never raises."""
    automatic = AnchorChoice(_("Automático: o mais pesado"), "")
    if scf is None:
        return (automatic,)
    try:
        labels = model_of(scf).labels
        heaviest = _heaviest(labels)
    except SurfaceError:
        return (automatic,)
    name = f"{labels[heaviest]} {heaviest + 1}"
    return (
        AnchorChoice(_("Automático: o mais pesado ({name})").format(name=name), ""),
        *(AnchorChoice(f"{label} {n}", str(n)) for n, label in enumerate(labels, 1)),
    )


def molecule_of(scf: ScfInfo, anchor: int | str | None = None) -> Molecule:
    """The molecule of ``scf``; ``anchor`` is 1-based, or the text typed (``anchor_index``). Raises
    ``SurfaceError``."""
    model = model_of(scf)
    count = len(model)
    if isinstance(anchor, str):
        index = anchor_index(model.labels, anchor)
    else:
        index = _numbered(anchor, count) if anchor is not None else None
    if index is None:
        index = _heaviest(model.labels)
    __, images = pair_images(model.frac, model.cell, [index], range(count))
    delta = model.frac - model.frac[index] + images[0]
    coords = delta @ model.cell
    axis = _axis(model.labels, coords, index)
    rotated = axis is not None and axis[2] < ALIGNED
    if rotated and axis is not None:
        coords = coords @ _rotation_onto_z(axis).T
    extent = float(coords[:, 2].max() - coords[:, 2].min())
    return Molecule(model.labels, coords, index, extent, rotated)
