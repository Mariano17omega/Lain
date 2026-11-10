"""Click selection on the projected scene."""

from __future__ import annotations

import numpy as np

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
