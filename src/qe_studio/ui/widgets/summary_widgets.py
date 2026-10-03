"""Widgets of the output summary tab: sections of label/value rows, some expandable (spec 12 R3.3)."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ...core.qe.summary import SummaryRow, SummarySection
from ..theme.manager import ThemeManager
from .common import set_variant

LABEL_WIDTH = 280
INDENT = 18  # per nesting level; also the width of the expand button


class _RowHead(QWidget):
    """The label/value line of a row: a double click asks for the output at the row's line."""

    activated = pyqtSignal()

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        self.activated.emit()
        if event is not None:
            event.accept()


class SummaryRowWidget(QWidget):
    """One row. ``activated(line)`` on a double click when the row knows its line."""

    activated = pyqtSignal(int)

    def __init__(self, row: SummaryRow, theme: ThemeManager, depth: int = 0):
        super().__init__()
        self.row = row
        self.theme = theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.head = _RowHead()
        head = QHBoxLayout(self.head)
        head.setContentsMargins(depth * INDENT, 1, 0, 1)
        head.setSpacing(6)
        self.toggle: QToolButton | None = None
        if row.children:
            self.toggle = QToolButton()
            self.toggle.setProperty("variant", "summaryToggle")
            self.toggle.setCheckable(True)
            self.toggle.setIconSize(QSize(12, 12))
            self.toggle.setFixedSize(INDENT, INDENT)
            self.toggle.setToolTip("Mostrar ou ocultar os detalhes")
            head.addWidget(self.toggle)
        else:
            head.addSpacing(INDENT + 6)
        self.label = set_variant(QLabel(row.label), "summaryLabel")
        self.label.setFixedWidth(LABEL_WIDTH - depth * INDENT)
        self.label.setWordWrap(True)
        self.value = set_variant(QLabel(row.value), "summaryValue")
        self.value.setProperty("level", row.level or "")
        self.value.setWordWrap(True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.label, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.value, 1)
        layout.addWidget(self.head)
        if row.line is not None:
            self.head.setCursor(Qt.CursorShape.PointingHandCursor)
            self.head.setToolTip(f"Duplo clique: abrir a saída na linha {row.line}")
            self.head.activated.connect(self._on_activated)

        self.details = QWidget()
        details = QVBoxLayout(self.details)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(0)
        self.children_widgets = [
            SummaryRowWidget(child, theme, depth + 1) for child in row.children
        ]
        for child in self.children_widgets:
            child.activated.connect(self.activated)
            details.addWidget(child)
        self.details.setVisible(False)
        layout.addWidget(self.details)
        if self.toggle is not None:
            self.toggle.toggled.connect(self._on_toggled)
            theme.theme_changed.connect(self._refresh_icon)
            self._refresh_icon()

    def _on_activated(self) -> None:
        if self.row.line is not None:
            self.activated.emit(self.row.line)

    def _on_toggled(self, expanded: bool) -> None:
        self.details.setVisible(expanded)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if self.toggle is not None:
            name = "expand_more" if self.toggle.isChecked() else "chevron_right"
            self.toggle.setIcon(self.theme.icon(name, "text_muted", size=12))

    def expand(self, expanded: bool = True) -> None:
        if self.toggle is not None:
            self.toggle.setChecked(expanded)


class SummarySectionWidget(QWidget):
    """A titled block of rows (the title is uppercase, like the panel headers)."""

    activated = pyqtSignal(int)

    def __init__(self, section: SummarySection, theme: ThemeManager):
        super().__init__()
        self.setObjectName("summarySection")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.title = set_variant(QLabel(section.title.upper()), "panelTitle")
        layout.addWidget(self.title)
        layout.addSpacing(4)
        self.rows = [SummaryRowWidget(row, theme) for row in section.rows]
        for widget in self.rows:
            widget.activated.connect(self.activated)
            layout.addWidget(widget)
