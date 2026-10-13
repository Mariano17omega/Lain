"""What is drawn over the sorted primitives and never hidden by an atom: labels, the rings of the hovered
and the current atom, the a, b, c names and the x, y, z triad.

The colors are the scene's (dark or light background), not theme tokens: like the figures, the scene does
not follow the app theme (spec 43 R4.5).
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from ....core.structure3d.camera import Camera
from ....core.structure3d.options import DisplayOptions
from ....core.structure3d.replicate import Scene

MIN_PICK_RADIUS = 5.0  # px
HIGHLIGHT = (255, 196, 40)
ABC_COLORS = ((235, 90, 90), (90, 205, 100), (110, 140, 255))
TEXT = {True: (225, 228, 235), False: (30, 30, 36)}  # by dark background
HOVER = {True: (255, 255, 255, 210), False: (20, 20, 24, 200)}

Spot = tuple[float, float, float]  # x, y, radius in px


def arrow_head(painter: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 14:
        return
    ux, uy = dx / length, dy / length
    c, s = 0.9, 0.43  # ~25 degrees
    for sign in (1, -1):
        hx = -(ux * c - uy * s * sign) * 8.0
        hy = -(ux * s * sign + uy * c) * 8.0
        painter.drawLine(QLineF(x2, y2, x2 + hx, y2 + hy))


def ring(painter: QPainter, spot: Spot, color: QColor, width: float) -> None:
    x, y, r = spot
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, width))
    r = max(r, MIN_PICK_RADIUS) + 3.0
    painter.drawEllipse(QPointF(x, y), r, r)


def _triad(painter: QPainter, camera: Camera, height: float, text: QColor) -> None:
    """x, y, z axes in the lower left corner, turning with the camera."""
    ox, oy = 46.0, height - 46.0
    screen = camera.axes_screen()  # x right, y down, per world axis
    for k in np.argsort(camera.rotation[2]).tolist():  # far axes first
        tx, ty = ox + 30.0 * screen[k, 0], oy + 30.0 * screen[k, 1]
        pen = QPen(QColor(*ABC_COLORS[k]).darker(115), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QLineF(ox, oy, tx, ty))
        painter.setPen(QPen(text))
        painter.drawText(QPointF(tx + 3, ty - 3), "xyz"[k])


def draw_overlays(
    painter: QPainter,
    font: QFont,
    size: tuple[float, float],
    camera: Camera,
    scene: Scene,
    options: DisplayOptions,
    labels: list[tuple[float, float, str]],
    hover_spot: Spot | None,
    current_spot: Spot | None,
) -> None:
    text = QColor(*TEXT[options.dark])
    painter.setFont(font)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if labels:
        painter.setPen(QPen(text))
        for x, y, label in labels:
            painter.drawText(QPointF(x, y), label)
    if hover_spot is not None:
        ring(painter, hover_spot, QColor(*HOVER[options.dark]), 1.5)
    if current_spot is not None:
        ring(painter, current_spot, QColor(*HIGHLIGHT), 2.4)
    if options.show_axes:
        tips, _, _ = camera.project(np.vstack([np.zeros((1, 3)), scene.cell]), size)
        for k, name in enumerate("abc"):
            if np.isfinite(tips[k + 1]).all():
                painter.setPen(QPen(QColor(*ABC_COLORS[k])))
                painter.drawText(QPointF(tips[k + 1, 0] + 6, tips[k + 1, 1] - 6), name)
        _triad(painter, camera, size[1], text)
