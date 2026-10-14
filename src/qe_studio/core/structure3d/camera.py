"""Arcball camera with perspective and orthographic projection (pure numpy)."""

from __future__ import annotations

import math

import numpy as np

PERSPECTIVE_RATIO = 4.0  # focal distance as a multiple of the framed radius
ROTATION_STEP_DEG = 45.0  # one click of the "Rotação" buttons (spec 46 R3)
_EPS = 1e-6
_WORLD_AXES = {"x": 0, "y": 1, "z": 2}


def _rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues rotation matrix."""
    n = np.linalg.norm(axis)
    if n < 1e-12 or angle == 0.0:
        return np.eye(3)
    x, y, z = axis / n
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


def frame_from(direction: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Rotation whose rows are (right, up, toward-viewer) for a view with the given axes.

    ``direction`` points towards the viewer; ``up`` is orthogonalised against it.
    """
    z = np.asarray(direction, dtype=float)
    z = z / np.linalg.norm(z)
    u = np.asarray(up, dtype=float)
    y = u - (u @ z) * z
    if np.linalg.norm(y) < 1e-9:  # up parallel to the view direction: pick any other
        y = np.eye(3)[int(np.argmin(np.abs(z)))]
        y = y - (y @ z) * z
    y = y / np.linalg.norm(y)
    x = np.cross(y, z)
    return np.vstack([x, y, z])


class Camera:
    """View state. Camera frame: x right, y up, z towards the viewer (right-handed).

    A world point ``p`` maps to ``v = R (p - center)``; ``depth = -v_z`` grows away from the
    viewer. Screen position is ``(w/2 + pan_x + v_x*zoom*s, h/2 + pan_y - v_y*zoom*s)`` with
    ``s = f / (f + depth)`` in perspective and ``s = 1`` in orthographic mode.
    """

    def __init__(self) -> None:
        self.rotation = np.eye(3)
        self.center = np.zeros(3)
        self.zoom = 10.0  # px per Å on the focal plane
        self.pan = np.zeros(2)  # px
        self.focal = 50.0  # Å, eye to focal plane
        self.perspective = True
        self._ball_start: np.ndarray | None = None
        self._rot_start = np.eye(3)

    # --- projection ---------------------------------------------------------------------
    def camera_coords(self, points: np.ndarray) -> np.ndarray:
        return (np.asarray(points, dtype=float) - self.center) @ self.rotation.T

    def project(
        self, points: np.ndarray, viewport: tuple[float, float]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(xy, depth, scale)`` for (n, 3) points; points behind the eye get NaN xy."""
        v = self.camera_coords(points)
        depth = -v[:, 2]
        if self.perspective:
            denom = self.focal + depth
            with np.errstate(divide="ignore", invalid="ignore"):
                scale = np.where(denom > _EPS, self.focal / denom, np.nan)
        else:
            scale = np.ones(len(v))
        w, h = viewport
        xy = np.column_stack(
            [
                w / 2 + self.pan[0] + v[:, 0] * self.zoom * scale,
                h / 2 + self.pan[1] - v[:, 1] * self.zoom * scale,
            ]
        )
        return xy, depth, scale

    # --- orientation --------------------------------------------------------------------
    def arcball_begin(self, x: float, y: float, viewport: tuple[float, float]) -> None:
        self._ball_start = self._ball_vector(x, y, viewport)
        self._rot_start = self.rotation.copy()

    def arcball_drag(self, x: float, y: float, viewport: tuple[float, float]) -> None:
        if self._ball_start is None:
            return
        end = self._ball_vector(x, y, viewport)
        axis = np.cross(self._ball_start, end)
        angle = math.acos(float(np.clip(self._ball_start @ end, -1.0, 1.0)))
        self.rotation = _rotation(axis, angle) @ self._rot_start

    def rotate_world(self, axis: str, degrees: float) -> None:
        """Turn the structure about the Cartesian ``axis`` ("x", "y" or "z") through the view's
        center, right-hand rule (``x+`` takes +y to +z). Zoom, pan, center and focal stay."""
        index = _WORLD_AXES.get(axis)
        if index is None:
            raise ValueError(f"unknown axis {axis!r}: expected x, y or z")
        self.rotation = self.rotation @ _rotation(np.eye(3)[index], math.radians(degrees))

    @staticmethod
    def _ball_vector(x: float, y: float, viewport: tuple[float, float]) -> np.ndarray:
        w, h = viewport
        radius = 0.5 * min(w, h)
        px, py = (x - w / 2) / radius, -(y - h / 2) / radius
        d2 = px * px + py * py
        if d2 <= 1.0:
            return np.array([px, py, math.sqrt(1.0 - d2)])
        d = math.sqrt(d2)
        return np.array([px / d, py / d, 0.0])

    def set_isometric(self) -> None:
        """View down (1, 1, 1) with z up on the screen."""
        self.rotation = frame_from(np.array([1.0, 1.0, 1.0]), np.array([0.0, 0.0, 1.0]))

    def look_along(self, direction: np.ndarray, up: np.ndarray) -> None:
        """Put the viewer on the ``direction`` side, with ``up`` roughly up on the screen."""
        self.rotation = frame_from(direction, up)

    def view_axis(self, name: str, cell: np.ndarray) -> None:
        """Views along the lattice vectors a, b, c or the Cartesian axes x, y, z."""
        e = np.eye(3)
        table = {
            "a": (cell[0], cell[2]),
            "b": (cell[1], cell[0]),
            "c": (cell[2], cell[1]),
            "x": (e[0], e[2]),
            "y": (e[1], e[2]),
            "z": (e[2], e[1]),
        }
        direction, up = table[name]
        self.look_along(direction, up)

    # --- framing and navigation ---------------------------------------------------------
    def fit(
        self,
        points: np.ndarray,
        viewport: tuple[float, float],
        margin: float = 0.9,
        pad: float = 0.0,
    ) -> None:
        """Choose zoom and pan so that ``points`` fill the viewport with the current rotation.

        ``pad`` (Å) grows the framed region on every side, e.g. by the largest atom radius.
        """
        points = np.asarray(points, dtype=float)
        v = self.camera_coords(points)
        lo, hi = v[:, :2].min(axis=0) - pad, v[:, :2].max(axis=0) + pad
        extent = np.maximum(hi - lo, 1e-6)
        w, h = viewport
        self.zoom = margin * min(w / extent[0], h / extent[1])
        mid = (lo + hi) / 2
        self.pan = np.array([-mid[0] * self.zoom, mid[1] * self.zoom])
        radius = float(np.linalg.norm(points - self.center, axis=1).max())
        self.focal = max(PERSPECTIVE_RATIO * radius, 1.0)

    def reset(
        self,
        points: np.ndarray,
        viewport: tuple[float, float],
        center: np.ndarray,
        pad: float = 0.0,
    ) -> None:
        """Isometric view of everything, centred on ``center``."""
        self.center = np.asarray(center, dtype=float)
        self.set_isometric()
        self.fit(points, viewport, pad=pad)

    def zoom_at(
        self, factor: float, cursor: tuple[float, float], viewport: tuple[float, float]
    ) -> None:
        """Scale by ``factor`` keeping the point under ``cursor`` fixed."""
        w, h = viewport
        offset = np.array([cursor[0] - w / 2, cursor[1] - h / 2])
        self.pan = offset - (offset - self.pan) * factor
        self.zoom *= factor

    def pan_by(self, dx: float, dy: float) -> None:
        self.pan = self.pan + np.array([dx, dy])

    def axes_screen(self) -> np.ndarray:
        """(3, 2) screen direction (x right, y down) of the world x, y, z axes, unit scale."""
        cols = self.rotation.T[:, :2]  # world axis k -> camera (x, y)
        return np.column_stack([cols[:, 0], -cols[:, 1]])
