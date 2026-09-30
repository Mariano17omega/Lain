"""Right-click menu for files and folders in the explorer tree and the file grid (spec 5 R3).

Exactly four actions: Abrir local de origem, Abrir com ▸, Copiar, Renomear. Renaming touches
global state (tabs, plot settings, folder memory), so it is handed to the main window.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QMimeData, QMimeDatabase, QObject, QProcess, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from ...core.desktop_apps import DesktopApp, catalog, expand_exec
from ..dialogs.open_with import ask_command

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
FILE_MANAGER = "org.freedesktop.FileManager1"
FILE_MANAGER_PATH = "/org/freedesktop/FileManager1"


def mime_types_for(path: Path) -> list[str]:
    """The item's MIME type and its parents, without the generic ``application/octet-stream``
    (every file has it, and would list hex editors everywhere)."""
    mime = QMimeDatabase().mimeTypeForFile(str(path))
    parents = [name for name in mime.allAncestors() if name != "application/octet-stream"]
    return [mime.name(), *parents]


def app_icon(app: DesktopApp) -> QIcon:
    if not app.icon:
        return QIcon()
    return QIcon(app.icon) if os.path.isabs(app.icon) else QIcon.fromTheme(app.icon)


class ItemActions(QObject):
    message = pyqtSignal(str, str)  # footer text, level
    rename_requested = pyqtSignal(Path)

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window = window
        self._reveals: dict[QObject, Path] = {}  # pending D-Bus calls → item

    def menu(self, path: Path, can_rename: bool = True) -> QMenu:
        menu = QMenu(self.window)
        menu.addAction("Abrir local de origem").triggered.connect(
            lambda _c=False: self.reveal(path)
        )
        open_with = menu.addMenu("Abrir com")
        open_with.aboutToShow.connect(lambda: self._fill_open_with(open_with, path))
        menu.addAction("Copiar").triggered.connect(lambda _c=False: self.copy(path))
        rename = menu.addAction("Renomear")
        rename.setEnabled(can_rename)
        rename.triggered.connect(lambda _c=False: self.rename_requested.emit(path))
        return menu

    # -- Abrir com --------------------------------------------------------------------------------
    def _fill_open_with(self, submenu: QMenu, path: Path) -> None:
        if submenu.actions():  # filled on the first opening
            return
        if IS_WINDOWS:
            choose = submenu.addAction("Escolher programa…")
            choose.triggered.connect(
                lambda _c=False: self._launch(
                    ["rundll32", "shell32.dll,OpenAs_RunDLL", str(path)], path, "Windows"
                )
            )
            return
        apps = catalog()
        mime_types = mime_types_for(path)
        default = apps.default_app(mime_types)
        others = [app for app in apps.apps_for(mime_types) if default is None or app != default]
        for app in ([default] if default else []) + others:
            text = f"{app.name} (padrão)" if app is default else app.name
            action = submenu.addAction(app_icon(app), text)
            action.triggered.connect(lambda _c=False, a=app: self.open_with(path, a))
        if default is None:
            submenu.addAction("Nenhum programa encontrado").setEnabled(False)
        submenu.addSeparator()
        submenu.addAction("Outro programa…").triggered.connect(
            lambda _c=False: self.open_with_other(path)
        )

    def open_with(self, path: Path, app: DesktopApp) -> None:
        self._launch(expand_exec(app, path), path, app.name)

    def open_with_other(self, path: Path) -> None:
        argv = ask_command(self.window, path.name)
        if argv:
            self._launch([*argv, str(path)], path, Path(argv[0]).name)

    def _launch(self, argv: list[str], path: Path, name: str) -> None:
        ok, _pid = QProcess.startDetached(argv[0], argv[1:], str(path.parent))
        if not ok:
            log.warning("could not start %s", argv)
            self.message.emit(f"Não foi possível abrir {path.name} com {name}.", "error")

    # -- Abrir local de origem --------------------------------------------------------------------
    def reveal(self, path: Path) -> None:
        """Show the item selected in the system file manager (a folder: in its parent)."""
        if IS_WINDOWS:
            QProcess.startDetached("explorer", [f"/select,{path}"])
        elif not self._show_items_dbus(path):
            self._open_parent(path)

    def _show_items_dbus(self, path: Path) -> bool:
        """FileManager1.ShowItems (Dolphin, Nautilus, Nemo…), answered asynchronously: starting
        the file manager may take seconds. False when there is no session bus."""
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher
        except ImportError:
            return False
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        call = QDBusMessage.createMethodCall(
            FILE_MANAGER, FILE_MANAGER_PATH, FILE_MANAGER, "ShowItems"
        )
        call.setArguments([[QUrl.fromLocalFile(str(path)).toString()], ""])
        watcher = QDBusPendingCallWatcher(bus.asyncCall(call), self)
        self._reveals[watcher] = path
        watcher.finished.connect(self._on_reveal_finished)
        return True

    def _on_reveal_finished(self, watcher) -> None:
        path = self._reveals.pop(watcher, None)
        if watcher.isError() and path is not None:
            log.info("%s.ShowItems failed: %s", FILE_MANAGER, watcher.error().message())
            self._open_parent(path)
        watcher.deleteLater()

    @staticmethod
    def _open_parent(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    # -- Copiar -----------------------------------------------------------------------------------
    def copy(self, path: Path) -> None:
        """Clipboard ready to paste in file managers (URL list, GNOME format) or a terminal."""
        url = QUrl.fromLocalFile(str(path))
        data = QMimeData()
        data.setUrls([url])
        data.setData("x-special/gnome-copied-files", b"copy\n" + bytes(url.toEncoded()))
        data.setText(str(path))
        QApplication.clipboard().setMimeData(data)
        self.message.emit(f"Copiado: {path.name}", "info")
