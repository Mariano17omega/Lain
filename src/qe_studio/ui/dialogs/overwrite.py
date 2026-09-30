"""Confirmation before replacing figures in plots/ (NFR: no silent overwrite)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets.common import set_variant


class OverwriteChoice(StrEnum):
    OVERWRITE = "overwrite"
    NEW_VERSION = "new_version"
    CANCEL = "cancel"


class OverwriteDialog(QDialog):
    def __init__(self, existing: list[Path], new_stem: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Arquivos já existem")
        self.setModal(True)
        self.choice = OverwriteChoice.CANCEL
        layout = QVBoxLayout(self)
        layout.addWidget(
            set_variant(QLabel("Figuras com este nome já existem em plots/"), "dialogTitle")
        )
        names = "\n".join(p.name for p in existing)
        layout.addWidget(set_variant(QLabel(names), "mono"))
        layout.addWidget(
            set_variant(
                QLabel(f"Sobrescrever ou salvar como nova versão ({new_stem})?"), "dialogText"
            )
        )
        self.remember = QCheckBox("Não perguntar novamente nesta sessão (sobrescrever)")
        layout.addWidget(self.remember)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, choice, variant in (
            ("Cancelar", OverwriteChoice.CANCEL, None),
            ("Nova versão", OverwriteChoice.NEW_VERSION, None),
            ("Sobrescrever", OverwriteChoice.OVERWRITE, "primary"),
        ):
            button = QPushButton(text)
            if variant:
                set_variant(button, variant)
            button.clicked.connect(lambda _c=False, ch=choice: self._choose(ch))
            row.addWidget(button)
        layout.addLayout(row)

    def _choose(self, choice: OverwriteChoice) -> None:
        self.choice = choice
        self.accept() if choice is not OverwriteChoice.CANCEL else self.reject()


def ask_overwrite(
    parent: QWidget, existing: list[Path], new_stem: str
) -> tuple[OverwriteChoice, bool]:
    """(choice, remember-for-session)."""
    dialog = OverwriteDialog(existing, new_stem, parent)
    dialog.exec()
    remember = dialog.remember.isChecked() and dialog.choice is OverwriteChoice.OVERWRITE
    choice = dialog.choice
    dialog.deleteLater()
    return choice, remember
