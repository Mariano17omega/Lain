"""The "Rotação" section of the structure panel (spec 46 R3): six buttons that turn the structure 45°
about the Cartesian x, y and z axes (the ones of the triad), right-hand rule.

A click calls ``StructureCanvas.rotate_structure``: no framing, no selection or measure is touched.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGridLayout, QPushButton, QWidget

from ....core.structure3d.camera import ROTATION_STEP_DEG
from ....i18n import _
from ..param_widgets import Section
from .canvas import StructureCanvas

AXES = ("x", "y", "z")
SIGNS = {"+": 1.0, "-": -1.0}  # top row: positive, bottom row: negative
TIPS = {
    "+": _("Girar a estrutura 45° em torno de {axis} (regra da mão direita)"),
    "-": _("Girar a estrutura 45° em torno de {axis}, no sentido contrário"),
}


class RotationSection(QObject):
    """Fills ``section`` with the buttons ``buttons["x+"]`` … ``buttons["z-"]``."""

    def __init__(self, section: Section, canvas: StructureCanvas):
        super().__init__(section)
        self.canvas = canvas
        self.buttons: dict[str, QPushButton] = {}
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for row, sign in enumerate(SIGNS):
            for column, axis in enumerate(AXES):
                name = f"{axis}{sign}"
                button = QPushButton(name)
                tip = TIPS[sign].format(axis=axis)
                button.setToolTip(tip)
                button.setAccessibleName(tip)
                button.clicked.connect(lambda _=False, a=axis, s=sign: self._turn(a, s))
                grid.addWidget(button, row, column)
                self.buttons[name] = button
        section.add_full(grid_host)

    def _turn(self, axis: str, sign: str) -> None:
        self.canvas.rotate_structure(axis, SIGNS[sign] * ROTATION_STEP_DEG)
