"""The Ajuda menu (spec 18 R1): shortcuts, log, data folder and "Sobre".

Shortcut rows come from two places, so the list cannot go stale: the action registry (every menu
action that has a key) and the ``shortcut_help()`` of the widgets that handle keys themselves.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import QWidget

from .. import APP_NAME, __version__
from ..core.about import package_versions
from ..core.appdirs import data_dir, log_path
from ..core.config import LoadedConfig
from .actions import ACTIONS
from .dialogs.about import AboutDialog
from .dialogs.shortcuts import ShortcutsDialog
from .widgets.text_viewer import TextViewer

ShortcutRows = list[tuple[str, str, str]]


class HelpController(QObject):
    message = pyqtSignal(str, str, int)  # text, level, timeout ms

    def __init__(
        self,
        window: QWidget,
        actions: Callable[[], dict[str, QAction]],
        providers: Sequence[Callable[[], ShortcutRows]],
        loaded: Callable[[], LoadedConfig],
        open_file: Callable[[Path], None],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window = window
        self._actions, self._providers = actions, providers
        self._loaded, self._open_file = loaded, open_file
        self.dialog: ShortcutsDialog | None = None

    @classmethod
    def for_window(cls, window) -> HelpController:
        """The controller of a ``MainWindow``: its action registry and its key-handling widgets."""
        providers = [
            window.explorer.shortcut_help,
            window.files.shortcut_help,
            TextViewer.shortcut_help,
            window.workspace.shortcut_help,
            window.navigation.shortcut_help,
        ]
        return cls(
            window,
            lambda: window._actions,
            providers,
            lambda: window.loaded,
            window.open_file,
            parent=window,
        )

    # -- shortcuts ----------------------------------------------------------------------------
    def shortcut_rows(self) -> ShortcutRows:
        actions = self._actions()
        rows: ShortcutRows = []
        for spec in ACTIONS:
            action = actions.get(spec.id)
            keys = action.shortcut().toString() if action is not None else ""
            if keys:
                rows.append((spec.text, keys, f"Menu {spec.menu}"))
        for provider in self._providers:
            rows.extend(provider())
        return rows

    def show_shortcuts(self) -> None:
        """One non-modal dialog: asking again brings the open one to the front."""
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        dialog = ShortcutsDialog(self.shortcut_rows(), self.window)
        dialog.destroyed.connect(self._on_dialog_closed)
        self.dialog = dialog
        dialog.show()

    def _on_dialog_closed(self) -> None:
        self.dialog = None

    def close_dialog(self) -> bool:
        """The main window is closing: the shortcuts window has no state."""
        dialog = self.dialog
        return dialog is None or dialog.close()

    # -- log and data -------------------------------------------------------------------------
    def open_log(self) -> None:
        path = log_path()
        if not path.is_file():
            self.message.emit(f"Ainda não há arquivo de log: {path}", "warning", 5000)
            return
        self._open_file(path)

    def open_data_dir(self) -> None:
        folder = data_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.message.emit(
                f"Não foi possível abrir {folder}: {exc.strerror or exc}", "error", 5000
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # -- about --------------------------------------------------------------------------------
    def about_rows(self) -> list[tuple[str, str]]:
        config_path = self._loaded().path
        stack = package_versions()
        rows = [(APP_NAME, __version__), stack[0]]
        rows += [("Qt", QT_VERSION_STR), ("PyQt", PYQT_VERSION_STR), *stack[1:]]
        rows += [
            ("Config", str(config_path) if config_path else "nenhum"),
            ("Log", str(log_path())),
            ("Dados", str(data_dir())),
        ]
        return rows

    def show_about(self) -> None:
        dialog = AboutDialog(f"{APP_NAME} {__version__}", self.about_rows(), self.window)
        dialog.exec()
        dialog.deleteLater()
