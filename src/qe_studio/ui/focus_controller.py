"""Keyboard focus of the main window (spec 19 R4): the tab order and the Ctrl+1..4 jumps.

Qt builds the focus chain in creation order, which is not the reading order of the window, and
``QWidget.setTabOrder`` moves one widget at a time. So the order is rebuilt from the chain itself:
the widgets are grouped by region (activity bar, top bar, tree, grid, workspace, adjustments,
footer), keeping each region's own order, and chained region after region. Widgets are created all
the time (crumbs, tabs, chips) and Qt appends each to the end of its chain, so
``MainWindow.focusNextPrevChild`` rebuilds the order before every Tab. Hidden panels need no
handling: Qt skips what is not visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt6.QtCore import QItemSelectionModel, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QWidget

if TYPE_CHECKING:
    from .main_window import MainWindow

NO_PLOT = "Nenhum gráfico aberto: os ajustes aparecem junto com o gráfico."


def focus_chain(start: QWidget) -> list[QWidget]:
    """Every widget of ``start``'s window in Qt's current focus chain order."""
    chain, widget = [], start
    while True:
        chain.append(widget)
        widget = widget.nextInFocusChain()
        if widget is None or widget is start:
            return chain


def tab_order(chain: Sequence[QWidget], regions: Sequence[QWidget]) -> list[QWidget]:
    """``chain`` regrouped by ``regions``, in their order; what belongs to none goes last."""
    groups: list[list[QWidget]] = [[] for _ in regions] + [[]]
    for widget in chain:
        for slot, region in enumerate(regions):
            if widget is region or region.isAncestorOf(widget):
                groups[slot].append(widget)
                break
        else:
            groups[-1].append(widget)
    return [widget for group in groups for widget in group]


def takes_focus(widgets: Sequence[QWidget]) -> list[QWidget]:
    return [w for w in widgets if w.focusPolicy() != Qt.FocusPolicy.NoFocus]


def first_focusable(root: QWidget, window: QWidget) -> QWidget | None:
    """``root`` if it takes the keyboard, else the first visible widget under it that does."""
    for widget in (root, *(w for w in focus_chain(root) if root.isAncestorOf(w))):
        if (
            widget.focusPolicy() & Qt.FocusPolicy.TabFocus
            and widget.isEnabled()
            and widget.isVisibleTo(window)
        ):
            return widget
    return None


def ensure_current(view: QAbstractItemView) -> None:
    """Give an item view without a current item its first one (not selected: the ring needs only
    the current item)."""
    selection, model = view.selectionModel(), view.model()
    if selection is None or model is None or selection.currentIndex().isValid():
        return
    first = model.index(0, 0, view.rootIndex())
    if first.isValid():
        selection.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)


class FocusController(QObject):
    message = pyqtSignal(str, str, int)  # text, level, timeout ms

    def __init__(self, window: MainWindow, parent: QObject | None = None):
        super().__init__(parent)
        self.window = window
        # Reading order of the window (R4.3); the adjustments panel sits in the left stack with the
        # tree, but comes after the workspace.
        self.regions: tuple[QWidget, ...] = (
            window.activity,
            window.top_bar,
            window.explorer,
            window.files,
            window.workspace,
            window.params,
            window.status,
        )

    @classmethod
    def for_window(cls, window: MainWindow) -> FocusController:
        """The controller of a ``MainWindow`` (it builds its own regions)."""
        return cls(window, window)

    # -- tab order (R4.3) -----------------------------------------------------------------------
    def apply_tab_order(self) -> None:
        # setTabOrder ignores a widget that takes no focus, so only the others are chained.
        chain = takes_focus(focus_chain(self.window))
        wanted = takes_focus(tab_order(chain, self.regions))
        if wanted == chain:
            return
        for first, second in zip(wanted, wanted[1:], strict=False):
            QWidget.setTabOrder(first, second)

    # -- jumps to an area (R4.4) ----------------------------------------------------------------
    def focus_tree(self) -> None:
        self.window.panel_layout.set_left_mode("tree")
        self._focus(self.window.explorer.tree)

    def focus_grid(self) -> None:
        self.window.panel_layout.set_panel_visible("grid", True)
        self._focus(self.window.files.view)

    def focus_workspace(self) -> None:
        self.window.panel_layout.set_panel_visible("workspace", True)
        tabs = self.window.workspace.tabs
        current = tabs.currentWidget()
        target = first_focusable(current, self.window) if current is not None else None
        # A plot or an image has nothing to type into: the tab bar is where the keys go.
        self._focus(target or tabs.tabBar())

    def focus_params(self) -> None:
        if self.window.current_plot() is None:
            self.message.emit(NO_PLOT, "info", 3000)
            return
        self.window.panel_layout.set_left_mode("params")
        self._focus(self.window.params)

    def _focus(self, widget: QWidget | None) -> None:
        target = first_focusable(widget, self.window) if widget is not None else None
        if target is None:
            return
        if isinstance(target, QAbstractItemView):
            ensure_current(target)
        target.setFocus(Qt.FocusReason.ShortcutFocusReason)
