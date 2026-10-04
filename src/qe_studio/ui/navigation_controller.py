"""Folder navigation of the main window: history, breadcrumb, the keys that drive them and the
favorite / recent folders (spec 16 R1, R2, R4).

``MainWindow.on_folder_selected`` is where every folder change arrives (tree click, grid
double click, ``..``, history), and tells ``visited``. Moving through the history goes through the
tree like any other navigation (``ExplorerPanel.select_path``), so the grid and the breadcrumb
follow; the history already holds the target by then, so ``visited`` finds nothing new to push.
Favorites and recents live in a ``NavigationStore``; the explorer's two sections show them.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from ..core.nav_store import NavigationStore
from ..core.navigation import NavigationHistory
from .widgets.bars import TopBar
from .widgets.explorer import ExplorerPanel
from .widgets.nav_sections import NavEntry, NavSection

SAVE_DELAY_MS = 500  # recents change on every visit: written after a pause


class NavigationController(QObject):
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)

    def __init__(
        self,
        window: QWidget,
        explorer: ExplorerPanel,
        top_bar: TopBar,
        root: Path,
        store: NavigationStore,
        settings: QSettings,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window, self.explorer, self.top_bar = window, explorer, top_bar
        self.store, self.settings, self.root = store, settings, Path(root)
        self.history = NavigationHistory()
        self.exists: Callable[[Path], bool] = os.path.isdir  # what a visited folder must satisfy
        top_bar.set_root(root)
        store.set_root(root)
        store.prune_missing_recents(self.exists)  # a recent folder gone since last time leaves
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.store.flush)
        for name, section in self._sections().items():
            section.set_open(settings.value(f"explorer/sections/{name}", True, type=bool))
            section.toggled.connect(self._on_section_toggled)
            section.folder_requested.connect(self.open_entry)
        self._refresh_sections()
        top_bar.back_button.clicked.connect(self.back)
        top_bar.forward_button.clicked.connect(self.forward)
        top_bar.breadcrumb.folder_requested.connect(self.go_to)
        top_bar.breadcrumb.path_copied.connect(self._on_path_copied)
        # The side mouse buttons work with the focus in any panel. Qt hands a click to the widget
        # under the cursor, so the filter is the application's, limited to this window.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def shutdown(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._save_timer.stop()
        self.store.flush()

    def set_root(self, root: Path) -> None:
        """Another project (config reload): its history starts empty, its favorites load."""
        self.root = Path(root)
        self.history.clear()
        self.top_bar.set_root(root)
        self.store.set_root(root)
        self.store.prune_missing_recents(self.exists)
        self._refresh_sections()
        self._sync_buttons()

    # -- visits ----------------------------------------------------------------------------------
    def visited(self, folder: Path) -> None:
        """The window now shows ``folder``."""
        self.history.visit(folder)
        self.top_bar.set_path(folder)
        self._sync_buttons()
        if self.store.touch_recent(folder):
            self._save_timer.start()
            self._refresh_sections()

    def rename(self, old: Path, new: Path) -> None:
        """A file or folder was renamed: the history, favorites and recents follow it."""
        self.history.rename(old, new)
        if self.store.rename(old, new):
            self._refresh_sections()

    def go_to(self, folder: Path) -> None:
        """Navigate to ``folder`` the way a click in the tree does."""
        self.explorer.select_path(folder)

    # -- history ---------------------------------------------------------------------------------
    def back(self) -> None:
        self._step(self.history.back)

    def forward(self) -> None:
        self._step(self.history.forward)

    def _step(self, move) -> None:
        target, skipped = move(self.exists)
        if skipped:
            names = ", ".join(path.name or str(path) for path in skipped)
            self.message.emit(f"Pasta não existe mais: {names}", "warning", 4000)
        if target is not None:
            self.go_to(target)
        self._sync_buttons()

    # -- favorites and recents -------------------------------------------------------------------
    def is_favorite(self, folder: Path) -> bool:
        return self.store.is_favorite(folder)

    def set_favorite(self, folder: Path, favorite: bool) -> None:
        """The context menu's "Adicionar aos favoritos" / "Remover dos favoritos"."""
        changed = (self.store.add_favorite if favorite else self.store.remove_favorite)(folder)
        if changed:
            self._refresh_sections()
            verb = "Adicionado aos" if favorite else "Removido dos"
            self.message.emit(f"{verb} favoritos: {folder.name or folder}", "info", 3000)

    def open_entry(self, folder: Path) -> None:
        """A click on a favorite or recent folder."""
        if self.exists(folder):
            self.go_to(folder)
        else:
            self.message.emit(f"Pasta não existe mais: {folder.name}", "warning", 4000)

    def _sections(self) -> dict[str, NavSection]:
        return {"favorites": self.explorer.favorites, "recents": self.explorer.recents}

    def _on_section_toggled(self, opened: bool) -> None:
        for name, section in self._sections().items():
            if section is self.sender():
                self.settings.setValue(f"explorer/sections/{name}", opened)

    def _refresh_sections(self) -> None:
        def entries(folders: list[Path]) -> list[NavEntry]:
            return [NavEntry(path, self._label(path), self.exists(path)) for path in folders]

        self.explorer.favorites.set_entries(entries(self.store.favorites()))
        self.explorer.recents.set_entries(entries(self.store.recents()))

    def _label(self, folder: Path) -> str:
        """The path below the project; the project itself by its name."""
        if folder == self.root:
            return self.root.name or str(self.root)
        return (
            folder.relative_to(self.root).as_posix()
            if folder.is_relative_to(self.root)
            else str(folder)
        )

    def _sync_buttons(self) -> None:
        self.top_bar.set_history(self.history.can_back, self.history.can_forward)

    def _on_path_copied(self, path: str) -> None:
        self.message.emit(f"Copiado: {path}", "info", 4000)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            isinstance(event, QMouseEvent)
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(obj, QWidget)
            and obj.window() is self.window
        ):
            if event.button() == Qt.MouseButton.BackButton:
                self.back()
                return True
            if event.button() == Qt.MouseButton.ForwardButton:
                self.forward()
                return True
        return False
