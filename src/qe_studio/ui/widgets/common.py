"""Small building blocks: panel headers, tool buttons, item view parts."""

from __future__ import annotations

from typing import TypeVar

from PyQt6.QtCore import QItemSelectionModel, QSize
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from ..theme.manager import ThemeManager

W = TypeVar("W", bound=QWidget)


def set_variant(widget: W, variant: str) -> W:
    widget.setProperty("variant", variant)
    return widget


def viewport_of(view: QAbstractItemView) -> QWidget:
    """The view's viewport (PyQt types it optional; an item view always has one)."""
    viewport = view.viewport()
    assert viewport is not None
    return viewport


def selection_of(view: QAbstractItemView) -> QItemSelectionModel:
    """The selection model of a view that has its model set."""
    selection = view.selectionModel()
    assert selection is not None
    return selection


class IconButton(QToolButton):
    """Tool button whose tinted icon follows the theme."""

    def __init__(
        self,
        theme: ThemeManager,
        icon: str,
        tooltip: str = "",
        variant: str = "headerButton",
        token: str = "text_muted",
        active_token: str | None = "accent",
        size: int = 16,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.theme, self.icon_name = theme, icon
        self.token, self.active_token, self.icon_px = token, active_token, size
        set_variant(self, variant)
        self.setToolTip(tooltip)
        self.setIconSize(QSize(size, size))
        self.refresh_icon()
        theme.theme_changed.connect(self.refresh_icon)

    def set_icon_name(self, icon: str) -> None:
        self.icon_name = icon
        self.refresh_icon()

    def refresh_icon(self, *_args) -> None:
        self.setIcon(self.theme.icon(self.icon_name, self.token, self.active_token, self.icon_px))


class PanelHeader(QWidget):
    """30 px header: uppercase mono title, optional count, right-aligned buttons."""

    def __init__(self, theme: ThemeManager, title: str, icon: str | None = None, parent=None):
        super().__init__(parent)
        set_variant(self, "panelHeader")
        self.theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 6, 0)
        layout.setSpacing(4)
        if icon:
            self.icon_label = QLabel()
            self._icon = icon
            layout.addWidget(self.icon_label)
            self._refresh_icon()
            theme.theme_changed.connect(self._refresh_icon)
        self.title = set_variant(QLabel(title.upper()), "panelTitle")
        self.count = set_variant(QLabel(""), "panelCount")
        layout.addWidget(self.title)
        layout.addWidget(self.count)
        layout.addStretch(1)
        self.buttons = layout

    def _refresh_icon(self, *_args) -> None:
        self.icon_label.setPixmap(self.theme.pixmap(self._icon, "text_muted", 14))

    def add_button(self, button: W) -> W:
        self.buttons.addWidget(button)
        return button
