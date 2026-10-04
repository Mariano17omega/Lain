"""Questions of the first run (spec 18 R5): which folder, and whether to create the config.

Thin wrappers so the controller (and the tests that patch them) talk to one name each.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget


def choose_folder(parent: QWidget | None) -> Path | None:
    """The project folder picked in the system dialog, or None when cancelled."""
    folder = QFileDialog.getExistingDirectory(
        parent, "Escolher a pasta do projeto", str(Path.home())
    )
    return Path(folder) if folder else None


def _yes(parent: QWidget | None, title: str, text: str) -> bool:
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return answer == QMessageBox.StandardButton.Yes


def ask_create_config(parent: QWidget | None, path: Path) -> bool:
    return _yes(parent, "Criar config.yaml", f"Criar o arquivo de configuração?\n\n{path}")


def ask_create_with_folder(parent: QWidget | None, folder: Path) -> bool:
    return _yes(
        parent,
        "Criar config.yaml",
        f"Criar config.yaml com esta pasta como projeto?\n\n{folder}",
    )
