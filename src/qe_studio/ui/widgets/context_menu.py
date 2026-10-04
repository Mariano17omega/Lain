"""Right-click menu for files and folders in the explorer tree and the file grid (spec 5 R3).

Four actions: Abrir local de origem, Abrir com ▸, Copiar, Renomear. A file one module can plot on
its own (spec 9) also gets "Plotar" on top, a QE output "Resumo" (spec 12) and a converged relax /
vc-relax output "Gerar SCF convergido" (spec 24; disabled, with the reason as tooltip, when its
input is missing). Renaming, plotting and generating touch global state (tabs, plot settings,
folder memory, the file panels), so they are handed to the main window and its controllers.

With several items selected in the grid (spec 16 R5) the menu is shorter: the item count, Abrir local
de origem, Copiar and, for exactly two QE inputs, Comparar; for a folder of bands and one of PDOS,
Bandas com DOS (spec 22).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QMimeData, QMimeDatabase, QObject, QPoint, QProcess, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from ...core.calculations import module_for_file
from ...core.calculations.bands_dos import bands_dos_pair
from ...core.desktop_apps import DesktopApp, catalog, expand_exec
from ...core.qe.scf_from_relax import scf_availability
from ...core.sniff import looks_like_input
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
    compare_requested = pyqtSignal(Path, Path)  # "Comparar" of two QE inputs (spec 16 R5.5)
    bands_dos_requested = pyqtSignal(Path, Path)  # bands folder, DOS folder (spec 22)
    scf_from_relax_requested = pyqtSignal(Path)  # "Gerar SCF convergido" of an output (spec 24)
    favorite_toggled = pyqtSignal(Path, bool)  # folder, now a favorite (spec 16 R4.1)

    def __init__(
        self,
        window: QWidget,
        service: DetectionService,
        is_favorite: Callable[[Path], bool] = lambda path: False,
    ):
        super().__init__(window)
        self.window = window
        self.service = service
        self.is_favorite = is_favorite
        self._reveals: dict[QObject, list[Path]] = {}  # pending D-Bus calls → items

    def show(self, paths: list[Path], pos: QPoint, can_rename: bool = True) -> None:
        """The menu of the selected ``paths`` at the global position ``pos``."""
        if len(paths) == 1:
            path = paths[0]
            plot_kind, is_output = self.file_actions_of(path)
            favorite = self.is_favorite(path) if path.is_dir() else None
            menu = self.menu(
                path,
                can_rename=can_rename,
                plot_kind=plot_kind,
                summary=is_output,
                favorite=favorite,
                scf=self.scf_state(path),
            )
        else:
            menu = self.multi_menu(paths)
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

    def scf_state(self, path: Path) -> str | None:
        """The "Gerar SCF convergido" item (spec 24): None hides it, "" enables it, any other
        text is why it is disabled. From the caches (and the head of the paired input)."""
        service = self.service
        results = service.peek_results(path.parent)
        return scf_availability(path, service.file_sniff(path), results, service.file_sniff)

    def menu(
        self,
        path: Path,
        can_rename: bool = True,
        plot_kind: str | None = None,
        summary: bool = False,
        favorite: bool | None = None,
        scf: str | None = None,
    ) -> QMenu:
        """``plot_kind``: the module that plots this file alone (spec 9); ``summary``: it is a QE
        output (spec 12); ``scf``: see ``scf_state`` (spec 24). They go on top, apart from the
        actions every item has. ``favorite``: for a folder, whether it is one already (spec 16
        R4.1); None for files."""
        menu = QMenu(self.window)
        if plot_kind is not None:
            add_action(menu, "Plotar", lambda: self.plot_file_requested.emit(path, plot_kind))
        if summary:
            add_action(menu, "Resumo", lambda: self.summary_requested.emit(path))
        if scf is not None:
            add_action(
                menu,
                "Gerar SCF convergido",
                lambda: self.scf_from_relax_requested.emit(path),
                enabled=not scf,
                tooltip=scf,
            )
            menu.setToolTipsVisible(True)  # the reason of a disabled item
        if plot_kind is not None or summary or scf is not None:
            menu.addSeparator()
        add_action(menu, "Abrir local de origem", lambda: self.reveal(path))
        open_with = menu.addMenu("Abrir com")
        assert open_with is not None
        open_with.aboutToShow.connect(lambda: self._fill_open_with(open_with, path))
        add_action(menu, "Copiar", lambda: self.copy(path))
        if favorite is not None:
            text = "Remover dos favoritos" if favorite else "Adicionar aos favoritos"
            add_action(menu, text, lambda: self.favorite_toggled.emit(path, not favorite))
        add_action(menu, "Renomear", lambda: self.rename_requested.emit(path), can_rename)
        return menu

    def multi_menu(self, paths: list[Path]) -> QMenu:
        """The menu of a selection of several items (grid only): no per-item actions."""
        menu = QMenu(self.window)
        add_action(menu, f"{len(paths)} itens", lambda: None, enabled=False)
        menu.addSeparator()
        add_action(menu, "Abrir local de origem", lambda: self.reveal_all(paths))
        add_action(menu, "Copiar", lambda: self.copy_all(paths))
        pair = self.input_pair(paths)
        if pair is not None:
            add_action(menu, "Comparar", lambda: self.compare_requested.emit(*pair))
        folders = self.bands_dos_folders(paths)
        if folders is not None:
            add_action(menu, "Bandas com DOS", lambda: self.bands_dos_requested.emit(*folders))
        if all(path.is_dir() for path in paths):  # favorites are folders
            every = all(self.is_favorite(path) for path in paths)
            text = "Remover dos favoritos" if every else "Adicionar aos favoritos"
            add_action(menu, text, lambda: self._toggle_favorites(paths, not every))
        return menu

    def _toggle_favorites(self, paths: list[Path], favorite: bool) -> None:
        for path in paths:
            self.favorite_toggled.emit(path, favorite)

    @staticmethod
    def input_pair(paths: list[Path]) -> tuple[Path, Path] | None:
        """Exactly two QE inputs (spec 11 R4.1, the head of each file), in path order: what
        "Comparar" takes. Folders are never inputs."""
        if len(paths) != 2 or any(p.is_dir() or not looks_like_input(p) for p in paths):
            return None
        first, second = sorted(paths)
        return first, second

    def bands_dos_folders(self, paths: list[Path]) -> tuple[Path, Path] | None:
        """(bands folder, DOS folder) when the selection is two folders that make a bands + DOS
        figure, from the cached detection only; a folder not detected yet is requested, so the
        next menu knows."""
        if len(paths) != 2 or not all(path.is_dir() for path in paths):
            return None
        results = [self.service.results(path) for path in paths]  # schedules the misses
        found = bands_dos_pair(*results)
        return None if found is None else (found.bands.folder, found.dos.folder)

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
        self.reveal_all([path])

    def reveal_all(self, paths: list[Path]) -> None:
        """Show the items, all selected when the file manager allows it (Windows' Explorer takes
        one ``/select``: the first)."""
        if IS_WINDOWS:
            QProcess.startDetached("explorer", [f"/select,{paths[0]}"])
        elif not self._show_items_dbus(paths):
            self._open_parent(paths[0])

    def _show_items_dbus(self, paths: list[Path]) -> bool:
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
        call.setArguments([[QUrl.fromLocalFile(str(p)).toString() for p in paths], ""])
        watcher = QDBusPendingCallWatcher(bus.asyncCall(call), self)
        self._reveals[watcher] = paths
        watcher.finished.connect(self._on_reveal_finished)
        return True

    def _on_reveal_finished(self, watcher) -> None:
        paths = self._reveals.pop(watcher, None)
        if watcher.isError() and paths:
            log.info("%s.ShowItems failed: %s", FILE_MANAGER, watcher.error().message())
            self._open_parent(paths[0])
        watcher.deleteLater()

    @staticmethod
    def _open_parent(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    # -- Copiar -----------------------------------------------------------------------------------
    def copy(self, path: Path) -> None:
        """Clipboard ready to paste in file managers (URL list, GNOME format) or a terminal."""
        self.copy_all([path])

    def copy_all(self, paths: list[Path]) -> None:
        """The same for several items: one URL per line, one path per line as text."""
        urls = [QUrl.fromLocalFile(str(path)) for path in paths]
        data = QMimeData()
        data.setUrls(urls)
        encoded = b"\n".join(url.toEncoded().data() for url in urls)
        data.setData("x-special/gnome-copied-files", b"copy\n" + encoded)
        data.setText("\n".join(str(path) for path in paths))
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setMimeData(data)
        text = f"Copiado: {paths[0].name}" if len(paths) == 1 else f"Copiados: {len(paths)} itens"
        self.message.emit(text, "info", 4000)
