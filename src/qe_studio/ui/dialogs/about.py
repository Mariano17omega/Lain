""" "Sobre o Lain": version, the stack's versions and the paths, with a copy button for bug
reports (spec 18 R1.4)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.about import report_text
from ..app_identity import app_icon
from ..widgets.common import set_variant

REPOSITORY = "https://github.com/Mariano17omega/Lain"


class AboutDialog(QDialog):
    def __init__(self, title: str, rows: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle("Sobre o Lain")
        self.setModal(True)
        layout = QVBoxLayout(self)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(64, 64))
        head.addWidget(logo)
        self.title = set_variant(QLabel(title), "dialogTitle")
        head.addWidget(self.title, 1)
        layout.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        for r, (label, value) in enumerate(rows):
            grid.addWidget(set_variant(QLabel(label), "dialogText"), r, 0)
            cell = set_variant(QLabel(value), "mono")
            cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(cell, r, 1)
        layout.addLayout(grid)
        link = QLabel(f'<a href="{REPOSITORY}">{REPOSITORY}</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton("Copiar informações")
        self.copy_button.clicked.connect(self.copy_info)
        close = set_variant(QPushButton("Fechar"), "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addWidget(close)
        layout.addLayout(row)

    def info_text(self) -> str:
        return report_text(self.rows)

    def copy_info(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.info_text())
