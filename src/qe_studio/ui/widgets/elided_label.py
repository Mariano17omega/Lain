"""A label that shows as much of its text as the width it is given (spec 18 R4)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget


class ElidedLabel(QLabel):
    """Keeps the full text and shows it elided in the middle to fit ``set_budget``.

    The budget is the widest the label may be (QSS padding included); the owner sets it from the
    space it has, so the text shrinks before the layout squeezes the neighbours. ``text()`` is
    what is shown, ``full_text()`` what was set; the tooltip carries the full text while elided.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self._budget: int | None = None

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._apply()

    def set_budget(self, budget: int | None) -> None:
        """The widest this label may be, or None for no limit."""
        if budget != self._budget:
            self._budget = budget
            self._apply()

    def natural_width(self) -> int:
        """Width the full text needs, padding included."""
        return self.fontMetrics().horizontalAdvance(self._full) + self._padding()

    def _padding(self) -> int:
        # QSS padding is not in contentsMargins: it is whatever the size hint adds to the text.
        shown = self.text()
        return max(0, self.sizeHint().width() - self.fontMetrics().horizontalAdvance(shown))

    def _apply(self) -> None:
        # Show the full text first so the padding is measured on it, then elide to the budget.
        self.setText(self._full)
        shown = self._full
        if self._budget is not None and self.natural_width() > self._budget:
            room = max(0, self._budget - self._padding())
            shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, room)
            self.setText(shown)
        self.setToolTip(self._full if shown != self._full else "")
