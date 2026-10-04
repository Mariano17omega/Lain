"""Right-click menu for files and folders in the explorer tree and the file grid (spec 5 R3).

Four actions: Abrir local de origem, Abrir com ▸, Copiar, Renomear. A file one module can plot on
its own (spec 9) also gets "Plotar" on top. Renaming and plotting touch global state (tabs, plot
settings, folder memory), so they are handed to the main window.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QMimeData, QMimeDatabase, QObject, QPoint, QProcess, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from ...core.calculations import module_for_file
from ...core.desktop_apps import DesktopApp, catalog, expand_exec
from ..dialogs.open_with import ask_command
from ..services import DetectionService
from .workspace_tabs import add_action

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
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)
    rename_requested = pyqtSignal(Path)
    plot_file_requested = pyqtSignal(Path, str)  # file, kind of the module that plots it
    summary_requested = pyqtSignal(Path)  # "Resumo" of a QE output (spec 12)

    def __init__(self, window: QWidget, service: DetectionService):
        super().__init__(window)
        self.window = window
        self.service = service
        self._reveals: dict[QObject, Path] = {}  # pending D-Bus calls → item

    def show(self, path: Path, pos: QPoint, can_rename: bool = True) -> None:
        """The menu of ``path`` at the global position ``pos``."""
        plot_kind, is_output = self.file_actions_of(path)
        menu = self.menu(path, can_rename=can_rename, plot_kind=plot_kind, summary=is_output)
        menu.exec(pos)
        menu.deleteLater()

    def file_actions_of(self, path: Path) -> tuple[str | None, bool]:
        """Kind of the module that plots ``path`` alone (spec 9) and whether it is a QE output
        (spec 12), from the cached sniff only: the GUI thread never reads the file. On a miss
        detection is requested, so the next menu knows."""
        sniff = self.service.file_sniff(path)
        if sniff is None:
            self.service.results(path.parent)
            return None, False
        module = module_for_file(sniff)
        return (module.kind if module else None), sniff.is_output

    def menu(
        self,
        path: Path,
        can_rename: bool = True,
        plot_kind: str | None = None,
        summary: bool = False,
    ) -> QMenu:
        """``plot_kind``: the module that plots this file alone (spec 9); ``summary``: it is a QE
        output (spec 12). Both go on top, apart from the actions every item has."""
        menu = QMenu(self.window)
        if plot_kind is not None:
            add_action(menu, "Plotar", lambda: self.plot_file_requested.emit(path, plot_kind))
        if summary:
            add_action(menu, "Resumo", lambda: self.summary_requested.emit(path))
        if plot_kind is not None or summary:
            menu.addSeparator()
        add_action(menu, "Abrir local de origem", lambda: self.reveal(path))
        open_with = menu.addMenu("Abrir com")
        assert open_with is not None
        open_with.aboutToShow.connect(lambda: self._fill_open_with(open_with, path))
        add_action(menu, "Copiar", lambda: self.copy(path))
        add_action(menu, "Renomear", lambda: self.rename_requested.emit(path), can_rename)
        return menu

    # -- Abrir com --------------------------------------------------------------------------------
    def _fill_open_with(self, submenu: QMenu, path: Path) -> None:
        if submenu.actions():  # filled on the first opening
            return
        if IS_WINDOWS:
            argv = ["rundll32", "shell32.dll,OpenAs_RunDLL", str(path)]
            add_action(submenu, "Escolher programa…", lambda: self._launch(argv, path, "Windows"))
            return
        apps = catalog()
        mime_types = mime_types_for(path)
        default = apps.default_app(mime_types)
        others = [app for app in apps.apps_for(mime_types) if default is None or app != default]
        for app in ([default] if default else []) + others:
            text = f"{app.name} (padrão)" if app is default else app.name
            add_action(submenu, text, lambda a=app: self.open_with(path, a), icon=app_icon(app))
        if default is None:
            add_action(submenu, "Nenhum programa encontrado", lambda: None, enabled=False)
        submenu.addSeparator()
        add_action(submenu, "Outro programa…", lambda: self.open_with_other(path))

    def open_with(self, path: Path, app: DesktopApp) -> None:
        self._launch(expand_exec(app, path), path, app.name)

    def open_default(self, path: Path) -> None:
        """Open ``path`` with the program its type opens with (text viewer's "Abrir no editor
        externo"); the desktop decides when none is registered."""
        app = None if IS_WINDOWS else catalog().default_app(mime_types_for(path))
        if app is None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.open_with(path, app)

    def open_with_other(self, path: Path) -> None:
        argv = ask_command(self.window, path.name)
        if argv:
            self._launch([*argv, str(path)], path, Path(argv[0]).name)

    def _launch(self, argv: list[str], path: Path, name: str) -> None:
        ok, _pid = QProcess.startDetached(argv[0], argv[1:], str(path.parent))
        if not ok:
            log.warning("could not start %s", argv)
            self.message.emit(f"Não foi possível abrir {path.name} com {name}.", "error", 4000)

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
        data.setData("x-special/gnome-copied-files", b"copy\n" + url.toEncoded().data())
        data.setText(str(path))
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setMimeData(data)
        self.message.emit(f"Copiado: {path.name}", "info", 4000)
