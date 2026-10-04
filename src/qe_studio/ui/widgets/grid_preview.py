"""Thumbnail of a grid of plots (spec 23 R3.3 "Pré-visualizar"): the positions and what each holds,
without drawing any plot."""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..theme.manager import ThemeManager

CELL_RATIO = 4 / 3  # width / height of a cell in the thumbnail
GAP = 4.0


class GridPreview(QWidget):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("gridPreview")
        self.theme = theme
        self.rows, self.cols = 1, 1
        self.labels: list[tuple[int, int, str]] = []  # (row, col, text), 0-based
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        theme.theme_changed.connect(self._repaint)

    def show_grid(self, rows: int, cols: int, labels: list[tuple[int, int, str]]) -> None:
        self.rows, self.cols = max(rows, 1), max(cols, 1)
        self.labels = list(labels)
        self.update()

    def _repaint(self, *_args) -> None:
        self.update()

    def cell_rect(self, row: int, col: int) -> QRectF:
        """Where position (row, col) is drawn: cells of ``CELL_RATIO``, centred in the widget."""
        area = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        width = min(area.width() / self.cols, area.height() / self.rows * CELL_RATIO)
        height = width / CELL_RATIO
        left = area.left() + (area.width() - width * self.cols) / 2
        top = area.top() + (area.height() - height * self.rows) / 2
        return QRectF(left + col * width, top + row * height, width, height).adjusted(
            GAP / 2, GAP / 2, -GAP / 2, -GAP / 2
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.theme.color
        inside = [(r, c, t) for r, c, t in self.labels if r < self.rows and c < self.cols]
        count = Counter((r, c) for r, c, _t in inside)
        for row in range(self.rows):
            for col in range(self.cols):
                rect = self.cell_rect(row, col)
                taken = count[(row, col)]
                if taken > 1:  # two cells in one position: what the validation complains about
                    fill, border = color("error_soft"), color("error")
                elif taken:
                    fill, border = color("accent_soft"), color("accent")
                else:
                    fill, border = color("panel"), color("border_strong")
                painter.setPen(QPen(border, 1))
                painter.setBrush(fill)
                painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(color("text"))
        for row, col, text in inside:
            if count[(row, col)] > 1:
                continue
            rect = self.cell_rect(row, col).adjusted(6, 4, -6, -4)
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, elided)
        painter.end()
