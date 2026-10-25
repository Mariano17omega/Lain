"""The "Grade", "Lista" and "Ordenar" buttons of a file panel's header (PRD §2.1.3).

The local files and the cluster's (spec 65) each have a set, and the two are kept equal
(``RemoteController``): a choice made in one panel is the other's too. A signal is emitted only when
the value changes, which is what ends that exchange.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu

from ...i18n import _
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader
from .fs_model import SORT_DATE, SORT_NAME, SORT_SIZE


class ViewControls(QObject):
    mode_changed = pyqtSignal(bool)  # True: cards (grid); False: rows (list)
    sort_changed = pyqtSignal(int)  # SORT_NAME, SORT_SIZE or SORT_DATE

    def __init__(
        self,
        theme: ThemeManager,
        header: PanelHeader,
        token: str = "text_muted",
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.grid_mode = True
        self.sort_column = SORT_NAME
        self.grid_button = header.add_button(
            IconButton(theme, "grid_view", _("Grade"), token=token)
        )
        self.list_button = header.add_button(
            IconButton(theme, "view_list", _("Lista"), token=token)
        )
        for button in (self.grid_button, self.list_button):
            button.setCheckable(True)
        self.grid_button.setChecked(True)
        self.sort_button = header.add_button(IconButton(theme, "sort", _("Ordenar"), token=token))
        self.sort_button.setPopupMode(IconButton.ToolButtonPopupMode.InstantPopup)
        self.sort_actions: dict[int, QAction] = {}
        self.sort_button.setMenu(self._sort_menu())
        self.grid_button.clicked.connect(self._show_grid)
        self.list_button.clicked.connect(self._show_list)

    def _show_grid(self) -> None:
        self.set_grid_mode(True)

    def _show_list(self) -> None:
        self.set_grid_mode(False)

    def set_grid_mode(self, grid: bool) -> None:
        """The buttons follow ``grid`` even when it is the mode already (a click unchecks the
        checked one); the signal only when it changed."""
        changed = grid != self.grid_mode
        self.grid_mode = grid
        self.grid_button.setChecked(grid)
        self.list_button.setChecked(not grid)
        if changed:
            self.mode_changed.emit(grid)

    def set_sort(self, column: int) -> None:
        """Sort by name (A→Z), size or date (largest / newest first)."""
        changed = column != self.sort_column
        self.sort_column = column
        self.sort_actions[column].setChecked(True)
        if changed:
            self.sort_changed.emit(column)

    def _sort_menu(self) -> QMenu:
        menu = QMenu(self.sort_button)
        group = QActionGroup(menu)
        for label, column in (
            (_("Nome"), SORT_NAME),
            (_("Tamanho"), SORT_SIZE),
            (_("Data"), SORT_DATE),
        ):
            action = menu.addAction(label)
            assert action is not None
            action.setCheckable(True)
            action.setChecked(column == SORT_NAME)
            group.addAction(action)
            action.triggered.connect(lambda _c=False, col=column: self.set_sort(col))
            self.sort_actions[column] = action
        return menu
