"""A centred message with buttons, for the areas that have nothing to show yet (spec 18 R5)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .common import set_variant

Button = tuple[str, str, Callable[[], None]]  # label, variant ("primary" or ""), slot


class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.title = set_variant(QLabel(), "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = set_variant(QLabel(), "emptyText")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setMaximumWidth(520)
        self.row = QHBoxLayout()
        self.row.setSpacing(8)
        self.buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addStretch(2)
        layout.addWidget(self.title)
        layout.addWidget(self.text, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addLayout(self.row)
        layout.addStretch(3)

    def set_content(self, title: str, text: str, buttons: list[Button]) -> None:
        """Replace the title, the text and the buttons (the previous ones are discarded)."""
        self.title.setText(title)
        self.text.setText(text)
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.buttons = {}
        self.row.addStretch(1)
        for label, variant, slot in buttons:
            button = QPushButton(label)
            if variant:
                set_variant(button, variant)
            button.clicked.connect(lambda _checked=False, fn=slot: fn())
            self.buttons[label] = button
            self.row.addWidget(button)
        self.row.addStretch(1)
