"""Building blocks of the plot parameters panel: color swatch, accordion section, series list."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..theme.manager import ThemeManager
from .common import set_variant


class ColorButton(QToolButton):
    color_changed = pyqtSignal(str)

    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        set_variant(self, "swatch")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: str) -> None:
        self.color = color
        self.setStyleSheet(f"background: {color};")
        self.setToolTip(color)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color), self, "Escolher cor")
        if chosen.isValid():
            self.set_color(chosen.name())
            self.color_changed.emit(chosen.name())


class Section(QWidget):
    """Collapsible accordion section with a 40/60 label/field grid."""

    opened_changed = pyqtSignal(bool)  # the user opened or closed it

    def __init__(
        self, theme: ThemeManager, title: str, opened: bool = True, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.theme = theme
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = set_variant(QToolButton(), "sectionHeader")
        self.header.setText(title.upper())
        self.header.setCheckable(True)
        self.header.setChecked(opened)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setIconSize(QSize(12, 12))
        self.body = set_variant(QWidget(), "sectionBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body.setVisible(opened)
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(10, 6, 8, 8)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(4)
        self.grid.setColumnStretch(0, 2)
        self.grid.setColumnStretch(1, 3)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        theme.theme_changed.connect(self._refresh_icon)
        self._refresh_icon()

    def add_row(self, label: str, widget: QWidget, tooltip: str = "") -> None:
        row = self.grid.rowCount()
        text = set_variant(QLabel(label), "fieldLabel")
        text.setToolTip(tooltip)
        text.setMinimumWidth(0)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, widget.sizePolicy().verticalPolicy())
        widget.setToolTip(tooltip or widget.toolTip())
        self.grid.addWidget(text, row, 0)
        self.grid.addWidget(widget, row, 1)

    def add_full(self, widget: QWidget) -> None:
        self.grid.addWidget(widget, self.grid.rowCount(), 0, 1, 2)

    def _toggle(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self._refresh_icon()
        self.opened_changed.emit(open_)

    def _refresh_icon(self, *_args) -> None:
        icon = "expand_more" if self.header.isChecked() else "chevron_right"
        self.header.setIcon(self.theme.icon(icon, "text_muted", size=12))


class SeriesList(QWidget):
    """Series of a plot (e.g. PDOS groups): visibility checkbox + color swatch per series."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(2)
        self._rows: dict[str, tuple[QWidget, QCheckBox, ColorButton]] = {}
        self._hidden: list[str] = []
        self._overrides: dict[str, str] = {}

    def set_series(self, colors: dict[str, str], hidden: list[str], overrides: dict[str, str]):
        """Show ``colors`` (label → color); rows are reused while the labels stay the same.

        ``hidden`` and ``overrides`` are the parameters' own list and dict: edits go into them.
        """
        self._hidden, self._overrides = hidden, overrides
        if list(colors) != list(self._rows):
            self._build_rows(colors)
        for label, color in colors.items():
            _row, check, swatch = self._rows[label]
            check.blockSignals(True)
            check.setChecked(label not in hidden)
            check.blockSignals(False)
            swatch.set_color(color)

    def _build_rows(self, colors: dict[str, str]) -> None:
        for row, _check, _swatch in self._rows.values():
            self.layout_.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        for label, color in colors.items():
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            check = QCheckBox(label)
            swatch = ColorButton(color)
            check.toggled.connect(lambda on, name=label: self._set_visible(name, on))
            swatch.color_changed.connect(lambda c, name=label: self._set_color(name, c))
            row_layout.addWidget(swatch)
            row_layout.addWidget(check, 1)
            self.layout_.addWidget(row)
            self._rows[label] = (row, check, swatch)

    def _set_visible(self, name: str, visible: bool) -> None:
        if visible and name in self._hidden:
            self._hidden.remove(name)
        elif not visible and name not in self._hidden:
            self._hidden.append(name)
        self.changed.emit()

    def _set_color(self, name: str, color: str) -> None:
        self._overrides[name] = color
        self.changed.emit()
