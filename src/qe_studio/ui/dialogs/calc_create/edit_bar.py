"""The bar above the preview of a file edited by hand (spec 39 R2.4): says the fields no longer
change it and offers the way back. Shown in both modes: an edit made in "Avançado" stays marked in
"Padrão"."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ....i18n import _
from ...widgets.common import set_variant

EDITED_TEXT = _("Editado manualmente. Os campos deste arquivo não o alteram mais.")
RESTORE_TEXT = _("Restaurar do formulário")
RESTORE_TIP = _("Descarta a edição e volta ao texto que os campos geram")


class EditBar(QWidget):
    restore_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.label = set_variant(QLabel(EDITED_TEXT), "dialogWarning")
        self.label.setWordWrap(True)
        self.restore_button = QPushButton(RESTORE_TEXT)
        self.restore_button.setToolTip(RESTORE_TIP)
        self.restore_button.setAutoDefault(False)
        self.restore_button.clicked.connect(self._restore)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 4)
        row.addWidget(self.label, 1)
        row.addWidget(self.restore_button)
        self.hide()

    def _restore(self) -> None:
        self.restore_requested.emit()

    def set_edited(self, edited: bool) -> None:
        self.setVisible(edited)
