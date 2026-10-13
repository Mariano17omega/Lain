"""Click selection on the projected scene."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from viewer3d.core.structure import AtomRef

TOLERANCE_PX = 3.0


def hit_test(
    click_xy: tuple[float, float],
    xy: np.ndarray,
    radii_px: np.ndarray,
    order: np.ndarray,
    tol_px: float = TOLERANCE_PX,
) -> int | None:
    """Index of the nearest-to-camera primitive whose disc (radius + tol) holds the click.

    ``order`` lists primitive indices from the camera outwards (front to back).
    """
    if len(order) == 0:
        return None
    delta = xy[order] - np.asarray(click_xy, dtype=float)
    inside = (delta * delta).sum(axis=1) <= (radii_px[order] + tol_px) ** 2
    hits = np.nonzero(inside)[0]
    return int(order[hits[0]]) if len(hits) else None


def pick(
    click_xy: tuple[float, float],
    xy: np.ndarray,
    radii_px: np.ndarray,
    order: np.ndarray,
    refs: Sequence[AtomRef],
    tol_px: float = TOLERANCE_PX,
) -> AtomRef | None:
    """``AtomRef`` under the click, or ``None``. ``refs[i]`` identifies primitive ``i``."""
    index = hit_test(click_xy, xy, radii_px, order, tol_px)
    return None if index is None else refs[index]
