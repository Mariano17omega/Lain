"""A molecule from its own SCF (spec 40 R2.6): the anchor at the origin and the axis along +z.

As ``build_molecule`` of the user's scripts: the anchor is the heaviest atom (the first on a tie) or
the one given, and the axis goes from it to the first atom that is neither H nor the anchor (else to
the centroid of the others). The positions are unwrapped around the anchor first (a molecule cut by
the edge of its box comes out whole). An axis already within ``ALIGNED`` of +z is kept as written;
any other is rotated onto +z (the script stops there). ``extent`` is the height along z.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..scf_info import ScfInfo
from . import SurfaceError
from .elements import atomic_number, element_of
from .geometry import pair_images
from .model import model_of

__all__ = ["ALIGNED", "Molecule", "molecule_of"]

ALIGNED = 0.98  # the z component of the unit axis above which it is left alone (the script's limit)


@dataclass(frozen=True, eq=False)
class Molecule:
    labels: tuple[str, ...]
    coords: np.ndarray = field(repr=False)  # (n, 3) Å, the anchor at the origin
    anchor: int  # 0-based
    extent: float  # Å along z
    rotated: bool = False


def _rotation_onto_z(axis: np.ndarray) -> np.ndarray:
    """The smallest rotation (Rodrigues) taking the unit vector ``axis`` onto +z."""
    z = np.array([0.0, 0.0, 1.0])
    cross, cos = np.cross(axis, z), float(np.dot(axis, z))
    sin = float(np.linalg.norm(cross))
    if sin < 1e-12:
        return np.eye(3) if cos > 0 else np.diag([1.0, -1.0, -1.0])
    k = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    return np.eye(3) + k + k @ k * ((1 - cos) / sin**2)


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


def molecule_of(scf: ScfInfo, anchor: int | None = None) -> Molecule:
    """The molecule of ``scf``; ``anchor`` is 1-based. Raises ``SurfaceError``."""
    model = model_of(scf)
    count = len(model)
    if anchor is None:
        numbers = [atomic_number(label) for label in model.labels]
        index = int(np.argmax(numbers))
    elif 1 <= anchor <= count:
        index = anchor - 1
    else:
        raise SurfaceError(f"Átomo âncora {anchor} fora da molécula (1 a {count})")
    _, images = pair_images(model.frac, model.cell, [index], range(count))
    delta = model.frac - model.frac[index] + images[0]
    coords = delta @ model.cell
    axis = _axis(model.labels, coords, index)
    rotated = axis is not None and axis[2] < ALIGNED
    if rotated and axis is not None:
        coords = coords @ _rotation_onto_z(axis).T
    extent = float(coords[:, 2].max() - coords[:, 2].min())
    return Molecule(model.labels, coords, index, extent, rotated)
