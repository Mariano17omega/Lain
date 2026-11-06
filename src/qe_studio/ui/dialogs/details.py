"""A long text to read beside the window (spec 17 R3: the full sync report): non-modal."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout, QWidget


class DetailsDialog(QDialog):
    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(560, 380)
        self.text = QPlainTextEdit(text)
        self.text.setObjectName("detailsText")
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text, 1)
        layout.addWidget(buttons)


def show_details(parent: QWidget | None, title: str, text: str) -> DetailsDialog:
    """Open ``text`` in a dialog that does not block the window; it deletes itself on close."""
    dialog = DetailsDialog(title, text, parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    return dialog
