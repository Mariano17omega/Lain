"""Bond halves drawn as shaded cylinders (spec 43 R2.2).

A half is a filled quadrilateral: its two projected ends widened by ``±ρ · zoom · scale`` (each end its
own perspective scale, so the nearer end is wider) across the projected axis, with a linear gradient
through the width lit from the same side as the spheres (up and left): dark edge, highlight at 30 % of the
width on the light side, base color at 55 %, dark edge on the other side. No caps: each end lies in a
sphere or in the other half. The geometry is numpy (``half_quads``, testable without a painter); the loop
only issues the draw calls.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtGui import QBrush, QColor, QLinearGradient

from ....core.structure3d.camera import Camera
from ....core.structure3d.geometry import half_bonds
from ....core.structure3d.replicate import Scene
from .render_types import Prims

__all__ = ["MIN_HALF_PX", "BondShader", "Quads", "add_halves", "half_quads"]

MIN_HALF_PX = 0.5  # a shorter projected half is hidden by its sphere (a view along the bond)
LIGHT = np.array([-1.0, -1.0]) / np.sqrt(2.0)  # screen direction of the light (y grows down)
EDGE = 0.4  # the edges: color × 0.4
HIGHLIGHT = 0.45  # 45 % of white
HIGHLIGHT_AT, BASE_AT = 0.30, 0.55  # fractions of the width from the light side


@dataclass(frozen=True, eq=False)
class Quads:
    corners: np.ndarray  # (k, 4, 2) start + n·w, end + n·w, end − n·w, start − n·w
    light: np.ndarray  # (k, 2) the gradient's start: the edge on the light side, at the middle
    shade: np.ndarray  # (k, 2) the gradient's end: the opposite edge
    width: np.ndarray  # (k, 2) half width (px) at the start and at the end
    drawn: np.ndarray  # (k,) bool: finite and at least MIN_HALF_PX long on screen

    def __len__(self) -> int:
        return len(self.corners)


def half_quads(
    xy_start: np.ndarray,
    xy_end: np.ndarray,
    scale_start: np.ndarray,
    scale_end: np.ndarray,
    rho: float,
    zoom: float,
) -> Quads:
    """The screen quadrilaterals of bond halves of radius ``rho`` (Å) between projected points."""
    xy_start = np.asarray(xy_start, dtype=float).reshape(-1, 2)
    xy_end = np.asarray(xy_end, dtype=float).reshape(-1, 2)
    delta = xy_end - xy_start
    length = np.hypot(delta[:, 0], delta[:, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = delta / np.maximum(length, 1e-12)[:, None]
    normal = np.column_stack([-unit[:, 1], unit[:, 0]])
    normal[normal @ LIGHT < 0] *= -1  # toward the light
    w_start = rho * zoom * np.asarray(scale_start, dtype=float)
    w_end = rho * zoom * np.asarray(scale_end, dtype=float)
    corners = np.stack(
        [
            xy_start + normal * w_start[:, None],
            xy_end + normal * w_end[:, None],
            xy_end - normal * w_end[:, None],
            xy_start - normal * w_start[:, None],
        ],
        axis=1,
    )
    middle = (xy_start + xy_end) / 2
    w_middle = ((w_start + w_end) / 2)[:, None]
    finite = np.isfinite(corners).all(axis=(1, 2))
    return Quads(
        corners=corners,
        light=middle + normal * w_middle,
        shade=middle - normal * w_middle,
        width=np.column_stack([w_start, w_end]),
        drawn=finite & (length >= MIN_HALF_PX),
    )


def add_halves(
    prims: Prims,
    kind: int,
    scene: Scene,
    camera: Camera,
    size: tuple[float, float],
    radii: np.ndarray,
    rho: float,
    keep: np.ndarray | None,
    min_width: float = 0.0,
) -> list[list[float]]:
    """Add the bond halves of ``scene`` to ``prims`` (``radii``: the drawn radius of each scene atom,
    Å; ``keep``: the bonds drawn; ``min_width``: px, thinner halves skipped in draft mode). Each
    half's ``aux`` indexes the returned rows: 4 corners (x, y), the light edge and the shade edge."""
    halves = half_bonds(scene, radii, rho, keep)
    start_xy, _depth, start_scale = camera.project(halves.start, size)
    end_xy, _depth, end_scale = camera.project(halves.end, size)
    _xy, middle_depth, _scale = camera.project(halves.middle, size)
    quads = half_quads(start_xy, end_xy, start_scale, end_scale, rho, camera.zoom)
    drawn = quads.drawn & (2 * quads.width.max(axis=1, initial=0.0) >= min_width)
    ids = np.nonzero(drawn)[0]
    owner = halves.owner[ids]
    prims.add(
        kind,
        start_xy[ids],
        end_xy[ids],
        middle_depth[ids],
        quads.width[ids, 0],
        scene.species[owner],
        owner >= scene.n_real,
        aux=np.arange(len(ids)),
    )
    rows = np.hstack([quads.corners[ids].reshape(-1, 8), quads.light[ids], quads.shade[ids]])
    return rows.tolist()


def _mix(rgb: np.ndarray, other: float, amount: float) -> QColor:
    out = rgb * (1 - amount) + other * amount
    return QColor(int(out[0]), int(out[1]), int(out[2]))


class BondShader:
    """The brushes of the halves by species: one ``QLinearGradient`` per species (its stops set once),
    moved to each half's edges before ``setBrush`` copies it; a flat brush in draft mode."""

    def __init__(self) -> None:
        self._gradients: dict[int, QLinearGradient] = {}
        self._flat: dict[int, QBrush] = {}
        self._rgb = np.zeros((0, 3))

    def set_colors(self, rgb: np.ndarray) -> None:
        """``rgb``: (species, 3) on 0..255."""
        self._rgb = rgb
        self._gradients.clear()
        self._flat.clear()

    def gradient(self, species: int) -> QLinearGradient:
        """The species' gradient; the caller sets its start (light edge) and final stop (shade edge)."""
        gradient = self._gradients.get(species)
        if gradient is None:
            rgb = self._rgb[species]
            edge = _mix(rgb, 0, 1 - EDGE)
            gradient = QLinearGradient()
            gradient.setStops(
                [
                    (0.0, edge),
                    (HIGHLIGHT_AT, _mix(rgb, 255, HIGHLIGHT)),
                    (BASE_AT, _mix(rgb, 0, 0.0)),
                    (1.0, edge),
                ]
            )
            self._gradients[species] = gradient
        return gradient

    def flat(self, species: int) -> QBrush:
        brush = self._flat.get(species)
        if brush is None:
            brush = self._flat[species] = QBrush(_mix(self._rgb[species], 0, 0.0))
        return brush
