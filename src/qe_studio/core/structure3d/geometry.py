"""What is drawn, in Å: the radius of each atom by style and the bond halves (spec 43 R2.1).

The renderer and the picking read these, so they agree. A bond is two halves, each in the color of its own
atom; a half starts where the stick (radius ``ρ``) meets its atom's sphere (radius ``r``, as drawn),
``√(r² − ρ²)`` from the center along the bond, and ends at the middle. Spheres that overlap past the middle
leave nothing of that half to draw. The ``fio`` style has no stick radius and does not cut.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .replicate import Scene

__all__ = [
    "BALL_FACTOR",
    "BOND_RADIUS",
    "STICK_RADIUS",
    "HalfBonds",
    "bond_radius",
    "half_bonds",
    "max_world_radius",
    "species_radii",
]

BALL_FACTOR = 0.45  # sphere radius as a fraction of the covalent radius ("bola-vareta")
BOND_RADIUS = {"bola-vareta": 0.10, "vareta": 0.20, "fio": 0.0, "espaco-cheio": 0.0}  # Å
STICK_RADIUS = 1.3 * BOND_RADIUS["vareta"]  # Å, the small ball of every atom in "vareta"
FRAME_PAD = 0.3  # Å, framing margin of the styles without real spheres


def bond_radius(style: str) -> float:
    """The stick radius of a style, Å (0 for ``fio`` and ``espaco-cheio``)."""
    return BOND_RADIUS.get(style, 0.0)


def species_radii(
    style: str, r_cov: np.ndarray, r_vdw: np.ndarray, radius_scale: float
) -> np.ndarray:
    """The drawn radius of each species, Å; 0 in ``fio`` (its atoms are dots of a fixed pixel size)."""
    r_cov = np.asarray(r_cov, dtype=float)
    if style == "espaco-cheio":
        return np.asarray(r_vdw, dtype=float) * radius_scale
    if style == "bola-vareta":
        return r_cov * BALL_FACTOR * radius_scale
    if style == "vareta":
        return np.full(len(r_cov), STICK_RADIUS)
    return np.zeros(len(r_cov))


def max_world_radius(
    style: str, r_cov: np.ndarray, r_vdw: np.ndarray, radius_scale: float
) -> float:
    """The largest drawn radius (Å), to pad the framing."""
    radii = species_radii(style, r_cov, r_vdw, radius_scale)
    largest = float(radii.max()) if len(radii) else 0.0
    return largest if style in ("bola-vareta", "espaco-cheio") else max(largest, FRAME_PAD)


@dataclass(frozen=True, eq=False)
class HalfBonds:
    """The halves to draw: ``owner`` is the scene atom whose color a half takes."""

    owner: np.ndarray  # (k,) int, index into ``Scene.positions``
    start: np.ndarray  # (k, 3) Å, on the owner's sphere
    end: np.ndarray  # (k, 3) Å, the middle of the bond

    def __len__(self) -> int:
        return len(self.owner)

    @property
    def middle(self) -> np.ndarray:
        """(k, 3) the middle of each half: its depth orders it among the spheres."""
        return (self.start + self.end) / 2


def half_bonds(
    scene: Scene, radii: np.ndarray, bond_radius: float, keep: np.ndarray | None = None
) -> HalfBonds:
    """The bond halves of ``scene`` (``keep``: a mask over its bonds) with ``radii`` the drawn radius of
    each scene atom (Å) and ``bond_radius`` the stick's (0: no cut)."""
    a, b = scene.bond_a, scene.bond_b
    if keep is not None:
        a, b = a[keep], b[keep]
    pa, pb = scene.positions[a], scene.positions[b]
    delta = pb - pa
    length = np.linalg.norm(delta, axis=1)
    unit = delta / np.maximum(length, 1e-12)[:, None]
    middle = (pa + pb) / 2
    radii = np.asarray(radii, dtype=float)
    if bond_radius > 0:
        cut_a = np.sqrt(np.maximum(radii[a] ** 2 - bond_radius**2, 0.0))
        cut_b = np.sqrt(np.maximum(radii[b] ** 2 - bond_radius**2, 0.0))
    else:
        cut_a = cut_b = np.zeros(len(a))
    half = length / 2
    ok_a, ok_b = cut_a < half, cut_b < half
    return HalfBonds(
        owner=np.concatenate([a[ok_a], b[ok_b]]).astype(int),
        start=np.vstack(
            [
                (pa + unit * cut_a[:, None])[ok_a],
                (pb - unit * cut_b[:, None])[ok_b],
            ]
        ).reshape(-1, 3),
        end=np.vstack([middle[ok_a], middle[ok_b]]).reshape(-1, 3),
    )
