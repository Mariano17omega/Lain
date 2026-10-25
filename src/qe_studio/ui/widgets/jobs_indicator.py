"""The jobs of the cluster left of the LED (spec 64 R4): "Executando: <nome>" and the like.

A flat button with text only, elided on the right past ``MAX_WIDTH``; a click opens the queue. What
it says comes from ``ui/jobs_controller.py``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QWidget

from ...i18n import _
from ..theme.manager import ThemeManager
from ..theme.scale import scaled

MAX_WIDTH = 240  # px at scale 1, padding included


class JobsIndicator(QPushButton):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("jobsIndicator")
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._full = ""
        self.setAccessibleName(_("Jobs do cluster"))  # until the first text
        self.setMaximumWidth(scaled(MAX_WIDTH))
        theme.scale_changed.connect(self._on_scale_changed)

    def full_text(self) -> str:
        """What the button says, before eliding."""
        return self._full

    def set_text(self, text: str, tip: str) -> None:
        self._full = text
        self.setToolTip(tip)
        self.setAccessibleName(text)  # the whole of it, not the elided text
        self._elide()

    def _on_scale_changed(self, _scale: float) -> None:
        self.setMaximumWidth(scaled(MAX_WIDTH))
        self._elide()

    def _elide(self) -> None:
        # The full text first, so the padding (QSS, not in the margins) is measured on it.
        # A "&" of a job's name is a "&&" for the button (else it would be a mnemonic).
        self.ensurePolished()
        self.setText(self._full.replace("&", "&&"))
        metrics = self.fontMetrics()
        limit = scaled(MAX_WIDTH)
        width = self.sizeHint().width()
        if width > limit:
            room = max(0, limit - (width - metrics.horizontalAdvance(self._full)))
            shown = metrics.elidedText(self._full, Qt.TextElideMode.ElideRight, room)
            self.setText(shown.replace("&", "&&"))
