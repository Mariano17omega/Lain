"""Rename a file or folder from the context menu (spec 5 R3.4). Never overwrites."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.file_ops import rename_error
from ..widgets.common import set_variant

SYNC_NOTE = (
    "Se esta pasta também existe no cluster, a próxima sincronização trará de volta o nome "
    "original."
)


class RenameDialog(QDialog):
    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.new_name: str | None = None
        self.setWindowTitle("Renomear")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel(f"Renomear {path.name}"), "dialogTitle"))
        self.edit = QLineEdit(path.name)
        self.edit.setMinimumWidth(380)
        # Select the stem, like file managers do, so typing keeps the extension.
        stem = len(path.stem) if path.suffix and not path.is_dir() else len(path.name)
        self.edit.setSelection(0, stem)
        layout.addWidget(self.edit)
        self.error = set_variant(QLabel(), "dialogError")
        self.error.hide()
        layout.addWidget(self.error)
        note = set_variant(QLabel(SYNC_NOTE), "dialogText")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        rename = set_variant(QPushButton("Renomear"), "primary")
        rename.setDefault(True)
        rename.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(rename)
        layout.addLayout(row)
        self.edit.textChanged.connect(self.error.hide)

    def accept(self) -> None:
        name = self.edit.text()
        error = rename_error(self.path, name)
        if error is not None:
            self.error.setText(error)
            self.error.show()
            return
        self.new_name = None if name == self.path.name else name
        super().accept()


def ask_rename(parent: QWidget, path: Path) -> str | None:
    """The new name, or None if cancelled or unchanged."""
    dialog = RenameDialog(path, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    name = dialog.new_name if accepted else None
    dialog.deleteLater()
    return name
