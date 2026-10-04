"""Confirmation before opening many files at once (spec 16 R5.4)."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget

MANY_FILES = 10  # opening up to this many files needs no question


def ask_open_many(parent: QWidget, count: int) -> bool:
    answer = QMessageBox.question(
        parent,
        "Abrir arquivos",
        f"Abrir {count} arquivos?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
