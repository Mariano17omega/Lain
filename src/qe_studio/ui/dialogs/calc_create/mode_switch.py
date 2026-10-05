"""The "Padrão / Avançado" switch of step 2 (spec 28 R5.1): two exclusive toggle buttons.

The modes are the core's (``types.MODES``); what each one shows is ``visible_fields``, never decided
here.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

from ....core.calc_create.types import DEFAULT_MODE, MODES, Mode
from ...widgets.common import set_variant

LABELS: dict[Mode, str] = {"padrao": "Padrão", "avancado": "Avançado"}
TIPS: dict[Mode, str] = {
    "padrao": "Só os campos do padrão do tipo; o resto segue o SCF e o config.yaml",
    "avancado": "Todos os campos, inclusive os nomes dos arquivos",
}


class ModeSwitch(QWidget):
    mode_changed = pyqtSignal(str)  # Mode, when the user picks the other one

    def __init__(self, mode: Mode = DEFAULT_MODE, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAccessibleName("Modo dos campos")
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[Mode, QToolButton] = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for value in MODES:
            button = set_variant(QToolButton(), "toggle")
            button.setText(LABELS[value])
            button.setToolTip(TIPS[value])
            button.setCheckable(True)
            button.clicked.connect(self._clicked)
            self.group.addButton(button)
            self.buttons[value] = button
            row.addWidget(button)
        self.set_mode(mode)

    @property
    def mode(self) -> Mode:
        for value, button in self.buttons.items():
            if button.isChecked():
                return value
        return DEFAULT_MODE

    def set_mode(self, mode: Mode) -> None:
        """Check ``mode``'s button without emitting ``mode_changed``."""
        self.buttons[mode].setChecked(True)

    def _clicked(self) -> None:
        self.mode_changed.emit(self.mode)
