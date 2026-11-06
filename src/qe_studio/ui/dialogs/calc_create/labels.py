"""Message lines of the "Criar cálculo" window: hint, warning (amber) and error (red)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget

from ...widgets.common import set_variant

VARIANTS = {"hint": "dialogText", "warning": "dialogWarning", "error": "dialogError"}


def message_label(level: str = "hint") -> QLabel:
    """A word-wrapped line, hidden while it has no text."""
    label = set_variant(QLabel(), VARIANTS[level])
    label.setWordWrap(True)
    label.hide()
    return label


def show_message(label: QLabel, text: str, level: str | None = None) -> None:
    """Set the text (an empty one hides the line) and, if given, the level's color."""
    if level is not None and label.property("variant") != VARIANTS[level]:
        set_variant(label, VARIANTS[level])
        repolish(label)
    label.setText(text)
    label.setVisible(bool(text))


def repolish(widget: QWidget) -> None:
    """Apply the style again after a dynamic property changed."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
