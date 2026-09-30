"""Abrir com → Outro programa…: a program chosen or typed by the user (spec 5 R3.2)."""

from __future__ import annotations

import shlex

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets.common import set_variant


class OpenWithDialog(QDialog):
    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.argv: list[str] | None = None
        self.setWindowTitle("Abrir com")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel(f"Abrir {name} com"), "dialogTitle"))
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(380)
        self.edit.setPlaceholderText("Comando, ex.: gedit ou /opt/app/bin/app --flag")
        browse = QPushButton("Procurar…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.error = set_variant(QLabel(), "dialogError")
        self.error.hide()
        layout.addWidget(self.error)
        note = set_variant(
            QLabel("O arquivo é passado como último argumento; nenhum shell é usado."),
            "dialogText",
        )
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.ok = set_variant(QPushButton("Abrir"), "primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.ok)
        layout.addLayout(buttons)
        self.edit.textChanged.connect(self._on_text)
        self._on_text(self.edit.text())

    def _on_text(self, text: str) -> None:
        self.error.hide()
        self.ok.setEnabled(bool(text.strip()))

    def _browse(self) -> None:
        program, _ = QFileDialog.getOpenFileName(self, "Escolher programa")
        if program:
            self.edit.setText(shlex.quote(program))

    def accept(self) -> None:
        try:
            argv = shlex.split(self.edit.text())
        except ValueError:
            argv = []
        if not argv:
            self.error.setText("Comando inválido (confira as aspas).")
            self.error.show()
            return
        self.argv = argv
        super().accept()


def ask_command(parent: QWidget, name: str) -> list[str] | None:
    """The program and its arguments (without the file), or None if cancelled."""
    dialog = OpenWithDialog(name, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    argv = dialog.argv if accepted else None
    dialog.deleteLater()
    return argv
