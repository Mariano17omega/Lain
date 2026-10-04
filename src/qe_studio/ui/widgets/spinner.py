"""Circular progress indicator (PRD §5.5): spinning arc, or a filling arc when % is known.

Also the small busy indicator of the status bar and of a plot tab (spec 15 R2).
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..painting import mono_font
from ..theme.manager import ThemeManager


class CircularProgress(QWidget):
    def __init__(self, theme: ThemeManager, size: int = 56, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedSize(size, size)
        self.percent = -1  # < 0: indeterminate
        self.angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._stopped = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._stopped:
            self._timer.start()  # animates only while shown: hidden spinners cost nothing

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def set_percent(self, percent: int) -> None:
        self.percent = max(-1, min(percent, 100))
        self.update()

    def stop(self) -> None:
        self._stopped = True
        self._timer.stop()

    def _tick(self) -> None:
        self.angle = (self.angle + 6) % 360
        if self.percent < 0:
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(1.5, self.width() / 14)  # 4 px at the dialog's 56 px
        rect = QRectF(self.rect()).adjusted(width, width, -width, -width)
        painter.setPen(QPen(self.theme.color("border_strong"), width))
        painter.drawEllipse(rect)
        pen = QPen(self.theme.color("accent"), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        if self.percent < 0:
            painter.drawArc(rect, int(-self.angle * 16), int(100 * 16))
        else:
            painter.drawArc(rect, 90 * 16, int(-self.percent * 3.6 * 16))
            painter.setPen(self.theme.color("text"))
            painter.setFont(mono_font(11, QFont.Weight.Medium))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.percent}%")
        painter.end()
