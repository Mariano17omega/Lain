"""Small building blocks: panel headers, tool buttons, item view parts."""

from __future__ import annotations

from collections.abc import Collection
from typing import TypeVar

from PyQt6.QtCore import QItemSelectionModel, QSize
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QToolButton,
    QWidget,
)

from ..theme.manager import ThemeManager

W = TypeVar("W", bound=QWidget)


def set_variant(widget: W, variant: str) -> W:
    widget.setProperty("variant", variant)
    return widget


def tool_button(text: str, tip: str, *, checkable: bool = False) -> QToolButton:
    """A text button of a viewer's bar (the ``viewerTool`` variant)."""
    button = set_variant(QToolButton(), "viewerTool")
    button.setText(text)
    button.setToolTip(tip)
    button.setCheckable(checkable)
    return button


def clear_layout(layout: QLayout, keep: Collection[QWidget] = ()) -> None:
    """Take every item out of ``layout`` and delete its widgets, but those of ``keep`` (taken out
    only: the caller puts them back). A widget is hidden first: ``deleteLater`` waits for the event
    loop, and until then it would show where it was."""
    while (item := layout.takeAt(0)) is not None:
        widget = item.widget()
        if widget is not None and widget not in keep:
            widget.hide()
            widget.deleteLater()


def copy_text(text: str) -> None:
    """``text`` on the clipboard (there is none without an application)."""
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


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


def hide_vertical_header(view: QTableView) -> None:
    """No row numbers (PyQt types the header optional; a table view always has one)."""
    header = view.verticalHeader()
    assert header is not None
    header.setVisible(False)


def show_only_page(stack: QStackedWidget, page: QWidget) -> None:
    """Make ``page`` the current one and the only one that counts for the window's size: the others
    are ``Ignored``, so a tall page does not keep a short one tall."""
    for index in range(stack.count()):
        widget = stack.widget(index)
        if widget is not None:
            policy = QSizePolicy.Policy.Preferred if widget is page else QSizePolicy.Policy.Ignored
            widget.setSizePolicy(policy, policy)
    stack.setCurrentWidget(page)


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

    def setToolTip(self, text: str | None) -> None:
        """An icon-only button is named by its tooltip, for screen readers (spec 19 R4.5)."""
        super().setToolTip(text)
        if not self.text():
            self.setAccessibleName(text or "")

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
