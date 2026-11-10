"""Right-click menu for files and folders in the explorer tree and the file grid (spec 5 R3).

Four actions: Abrir local de origem, Abrir com ▸, Copiar, Renomear. A file one module can plot on
its own (spec 9) also gets "Plotar" on top, a QE output "Resumo" (spec 12) and a converged relax /
vc-relax output "Gerar SCF convergido" (spec 24; disabled, with the reason as tooltip, when its
input is missing). A folder gets "Enviar ao cluster" under "Abrir com" (spec 27; disabled, with the
reason, when sync is off or it is the project root). A pw.x input or output also gets "Abrir com
XCrysDen" (spec 45; disabled, with the reason, when ``paths.xcrysden_path`` is empty or wrong).
Renaming, plotting, generating and pushing touch global state (tabs, plot settings, folder memory,
the file panels, the cluster), so they are handed to the main window and its controllers.

With several items selected in the grid (spec 16 R5) the menu is shorter: the item count, Abrir local
de origem, Copiar and, for exactly two QE inputs, Comparar; for a folder of bands and one of PDOS,
Bandas com DOS (spec 22); for two or more SCF outputs of pw.x, Calcular adsorção… (spec 78).
"""

from __future__ import annotations

import logging
import os
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QMimeDatabase, QObject, QPoint, QProcess, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from ....core.calculations import module_for_file
from ....core.calculations.bands_dos import bands_dos_pair
from ....core.files.desktop_apps import DesktopApp, catalog, catalog_ready, expand_exec
from ....core.files.xcrysden import command, locate, option_for
from ....core.qe.scf_from_relax import scf_availability
from ....core.sniff import FileKind, looks_like_input
from ....core.tasks import run_task
from ....i18n import _, ngettext
from ...dialogs.open_with import ask_command
from ...files.detection_service import DetectionService
from ..shell.workspace_tabs import add_action

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
FILE_MANAGER = "org.freedesktop.FileManager1"
FILE_MANAGER_PATH = "/org/freedesktop/FileManager1"
XCRYSDEN_TEXT = _("Abrir com XCrysDen")  # the user's spelling (spec 45); the program's is XCrySDen


def mime_types_for(path: Path) -> list[str]:
    """The item's MIME type and its parents, without the generic ``application/octet-stream``
    (every file has it, and would list hex editors everywhere)."""
    mime = QMimeDatabase().mimeTypeForFile(str(path))
    parents = [name for name in mime.allAncestors() if name != "application/octet-stream"]
    return [mime.name(), *parents]


class OpenChoices(NamedTuple):
    """The programs that open ``path``: the type's default (or None) and the other ones."""

    path: Path
    default: DesktopApp | None
    others: list[DesktopApp]


def open_with_choices(path: Path) -> OpenChoices:
    """The first call reads the whole catalog of programs: ``_fill_open_with`` and ``open_default``
    run it in a worker until the catalog is built (``QMimeDatabase`` may be asked from any thread)."""
    apps = catalog()
    mime_types = mime_types_for(path)
    default = apps.default_app(mime_types)
    others = [app for app in apps.apps_for(mime_types) if default is None or app != default]
    return OpenChoices(path, default, others)


def default_choice(path: Path) -> OpenChoices:
    """``open_with_choices``, but a catalog that cannot be read gives no program: the desktop's own
    opener then decides (worker side of ``open_default``)."""
    try:
        return open_with_choices(path)
    except Exception:
        log.warning("file: cannot list the programs that open %s", path, exc_info=True)
        return OpenChoices(path, None, [])


class FileActions(NamedTuple):
    """What the cached sniff of a file offers at the top of its menu."""

    plot_kind: str | None  # the module that plots it alone (spec 9)
    is_output: bool  # a QE output: "Resumo" (spec 12)
    structure: bool  # a pw.x input: "Visualização 3D" (spec 43)
    xcrysden: str | None = None  # the XCrySDen option that opens it (--pwi / --pwo, spec 45)
    scf_input: bool = False  # a pw.x input with calculation 'scf': "Gerar CIF" (spec 74)


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
    push_requested = pyqtSignal(Path)  # "Enviar ao cluster" of a folder (spec 27)
    structure_requested = pyqtSignal(Path)  # "Visualização 3D" of a pw.x input (spec 43)
    cif_requested = pyqtSignal(Path)  # "Gerar CIF" of an SCF input (spec 74)
    adsorption_requested = pyqtSignal(list)  # "Calcular adsorção…" of SCF outputs (spec 78)

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
        # "Enviar ao cluster" of a path: None hides it, "" enables it, else why it is disabled.
        # The sync coordinator sets it (SyncCoordinator.bind_menu); without it there is no item.
        self.push_state: Callable[[Path], str | None] = lambda path: None
        # ``paths.xcrysden_path`` as it is now, read at every menu so a config reload applies at
        # once (spec 45). ``Structure3DController.for_window`` sets it: ``main_window.py`` is full.
        self.xcrysden_path: Callable[[], str | None] = lambda: None
        self._reveals: dict[QObject, list[Path]] = {}  # pending D-Bus calls → items
        # The "Abrir com" submenu waiting for the programs of its item (one menu at a time).
        self._pending_open_with: tuple[QMenu, Path] | None = None

    def show(self, paths: list[Path], pos: QPoint, can_rename: bool = True) -> None:
        """The menu of the selected ``paths`` at the global position ``pos``.

        The ``is_dir`` and ``looks_like_input`` (the head of a file) calls below stat or read the
        few selected items while the menu is built: accepted, local disk (spec 27-8 R3.3).
        """
        if len(paths) == 1:
            path = paths[0]
            actions = self.file_actions_of(path)
            favorite = self.is_favorite(path) if path.is_dir() else None
            menu = self.menu(
                path,
                can_rename=can_rename,
                plot_kind=actions.plot_kind,
                summary=actions.is_output,
                structure=actions.structure,
                xcrysden=actions.xcrysden,
                cif=actions.scf_input,
                favorite=favorite,
                scf=self.scf_state(path),
                push=self.push_state(path),
            )
        else:
            menu = self.multi_menu(paths)
        menu.exec(pos)
        menu.deleteLater()

    def file_actions_of(self, path: Path) -> FileActions:
        """Kind of the module that plots ``path`` alone (spec 9), whether it is a QE output (spec 12),
        whether it is a pw.x input (spec 43) and the option XCrySDen opens it with (spec 45), from
        the cached sniff only: the GUI thread never reads the file. On a miss detection is
        requested, so the next menu knows."""
        sniff = self.service.file_sniff(path)
        if sniff is None:
            self.service.results(path.parent)
            return FileActions(None, False, False, None)
        module = module_for_file(sniff)
        return FileActions(
            module.kind if module else None,
            sniff.is_output,
            sniff.kind is FileKind.PW_IN,
            option_for(sniff.kind),
            sniff.kind is FileKind.PW_IN and sniff.calculation == "scf",
        )

    def scf_state(self, path: Path) -> str | None:
        """The "Gerar SCF convergido" item (spec 24): None hides it, "" enables it, any other
        text is why it is disabled. From the caches: no file is read here."""
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
        push: str | None = None,
        structure: bool = False,
        xcrysden: str | None = None,
        cif: bool = False,
    ) -> QMenu:
        """``plot_kind``: the module that plots this file alone (spec 9); ``summary``: it is a QE
        output (spec 12); ``structure``: a pw.x input, "Visualização 3D" (spec 43); ``xcrysden``: the
        option XCrySDen opens it with, None hides the item (spec 45); ``scf``: see ``scf_state``
        (spec 24); ``cif``: an SCF input, "Gerar CIF" (spec 74). They go on top, apart from the actions every item has. ``favorite``: for a folder,
        whether it is one already (spec 16 R4.1); None for files. ``push``: see ``push_state``
        (spec 27)."""
        menu = QMenu(self.window)
        if plot_kind is not None:
            add_action(menu, _("Plotar"), lambda: self.plot_file_requested.emit(path, plot_kind))
        if summary:
            add_action(menu, _("Resumo"), lambda: self.summary_requested.emit(path))
        if structure:
            add_action(menu, _("Visualização 3D"), lambda: self.structure_requested.emit(path))
        if cif:
            add_action(menu, _("Gerar CIF"), lambda: self.cif_requested.emit(path))
        if xcrysden is not None:
            found = locate(self.xcrysden_path())
            add_action(
                menu,
                XCRYSDEN_TEXT,
                lambda: self.open_in_xcrysden(path, xcrysden, found.executable),
                enabled=found.executable is not None,
                tooltip=found.problem,
            )
            menu.setToolTipsVisible(True)  # the reason of a disabled item
        if scf is not None:
            add_action(
                menu,
                _("Gerar SCF convergido"),
                lambda: self.scf_from_relax_requested.emit(path),
                enabled=not scf,
                tooltip=scf,
            )
            menu.setToolTipsVisible(True)  # the reason of a disabled item
        if any(
            (plot_kind is not None, summary, structure, cif, xcrysden is not None, scf is not None)
        ):
            menu.addSeparator()
        add_action(menu, _("Abrir local de origem"), lambda: self.reveal(path))
        open_with = menu.addMenu(_("Abrir com"))
        assert open_with is not None
        open_with.aboutToShow.connect(lambda: self._fill_open_with(open_with, path))
        if push is not None:
            add_action(
                menu,
                _("Enviar ao cluster"),
                lambda: self.push_requested.emit(path),
                enabled=not push,
                tooltip=push,
            )
            menu.setToolTipsVisible(True)  # the reason of a disabled item
        add_action(menu, _("Copiar"), lambda: self.copy(path))
        if favorite is not None:
            text = _("Remover dos favoritos") if favorite else _("Adicionar aos favoritos")
            add_action(menu, text, lambda: self.favorite_toggled.emit(path, not favorite))
        add_action(menu, _("Renomear"), lambda: self.rename_requested.emit(path), can_rename)
        return menu

    def multi_menu(self, paths: list[Path]) -> QMenu:
        """The menu of a selection of several items (grid only): no per-item actions."""
        menu = QMenu(self.window)
        count = ngettext("{n} item", "{n} itens", len(paths)).format(n=len(paths))
        add_action(menu, count, lambda: None, enabled=False)
        menu.addSeparator()
        add_action(menu, _("Abrir local de origem"), lambda: self.reveal_all(paths))
        add_action(menu, _("Copiar"), lambda: self.copy_all(paths))
        pair = self.input_pair(paths)
        if pair is not None:
            add_action(menu, _("Comparar"), lambda: self.compare_requested.emit(*pair))
        folders = self.bands_dos_folders(paths)
        if folders is not None:
            add_action(menu, _("Bandas com DOS"), lambda: self.bands_dos_requested.emit(*folders))
        if self.scf_outputs(paths):
            add_action(
                menu, _("Calcular adsorção…"), lambda: self.adsorption_requested.emit(list(paths))
            )
        if all(path.is_dir() for path in paths):  # favorites are folders
            every = all(self.is_favorite(path) for path in paths)
            text = _("Remover dos favoritos") if every else _("Adicionar aos favoritos")
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

    def scf_outputs(self, paths: list[Path]) -> bool:
        """Two or more pw.x outputs with ``calculation = 'scf'`` (spec 78 R3.1), from the cached sniff
        only: a folder has none, and a file not detected yet is requested, so the next menu knows."""
        if len(paths) < 2:
            return False
        sniffs = [self.service.file_sniff(path) for path in paths]
        for parent in {path.parent for path, sniff in zip(paths, sniffs, strict=True) if not sniff}:
            self.service.results(parent)  # schedules the misses
        return all(
            sniff is not None and sniff.kind is FileKind.PW_OUT and sniff.calculation == "scf"
            for sniff in sniffs
        )

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
            add_action(
                submenu, _("Escolher programa…"), lambda: self._launch(argv, path, "Windows")
            )
            return
        if catalog_ready():
            self._add_apps(submenu, open_with_choices(path))
            return
        # The first time the catalog is read: from a worker, the submenu says so meanwhile.
        add_action(submenu, _("Carregando…"), lambda: None, enabled=False)
        self._pending_open_with = (submenu, path)
        run_task(
            open_with_choices, path, on_done=self._on_apps_listed, on_error=self._on_apps_failed
        )

    def _on_apps_listed(self, choices: OpenChoices) -> None:
        pending = self._pending_open_with
        if pending is None or pending[1] != choices.path:  # the answer of an earlier menu
            return
        self._pending_open_with = None
        if not sip.isdeleted(pending[0]):  # else the menu closed before the answer
            pending[0].clear()
            self._add_apps(pending[0], choices)

    def _on_apps_failed(self, error: Exception) -> None:
        """No list of programs: "Outro programa…" still works."""
        log.warning("file: cannot list the programs: %s", error)
        if self._pending_open_with is not None:
            self._on_apps_listed(OpenChoices(self._pending_open_with[1], None, []))

    def _add_apps(self, submenu: QMenu, choices: OpenChoices) -> None:
        path, default = choices.path, choices.default
        for app in ([default] if default else []) + choices.others:
            text = _("{name} (padrão)").format(name=app.name) if app is default else app.name
            add_action(submenu, text, lambda a=app: self.open_with(path, a), icon=app_icon(app))
        if default is None:
            add_action(submenu, _("Nenhum programa encontrado"), lambda: None, enabled=False)
        submenu.addSeparator()
        add_action(submenu, _("Outro programa…"), lambda: self.open_with_other(path))

    def open_with(self, path: Path, app: DesktopApp) -> None:
        self._launch(expand_exec(app, path), path, app.name)

    def open_default(self, path: Path) -> None:
        """Open ``path`` with the program its type opens with (text viewer's "Abrir no editor
        externo"); the desktop decides when none is registered. The programs are listed in a worker:
        the first time that reads the whole catalog."""
        if IS_WINDOWS:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            run_task(default_choice, path, on_done=self._open_with_default)

    def _open_with_default(self, choices: OpenChoices) -> None:
        if choices.default is None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(choices.path)))
        else:
            self.open_with(choices.path, choices.default)

    def open_in_xcrysden(self, path: Path, option: str, executable: Path | None) -> None:
        """ "Abrir com XCrysDen" (spec 45): ``xcrysden <option> <path>``, detached, no shell. A start
        that fails is the footer's "Não foi possível abrir …"; what XCrySDen does after it starts
        is not followed."""
        if executable is not None:
            self._launch(command(executable, option, path), path, "XCrysDen")

    def open_with_other(self, path: Path) -> None:
        argv = ask_command(self.window, path.name)
        if argv:
            self._launch([*argv, str(path)], path, Path(argv[0]).name)

    def _launch(self, argv: list[str], path: Path, name: str) -> None:
        log.info("file: external program %s", shlex.join(argv))
        ok, _pid = QProcess.startDetached(argv[0], argv[1:], str(path.parent))
        if not ok:
            log.warning("file: could not start %s", argv)
            text = _("Não foi possível abrir {file} com {program}.")
            self.message.emit(text.format(file=path.name, program=name), "error", 4000)

    # -- Abrir local de origem --------------------------------------------------------------------
    def reveal(self, path: Path) -> None:
        """Show the item selected in the system file manager (a folder: in its parent)."""
        self.reveal_all([path])

    def reveal_all(self, paths: list[Path]) -> None:
        """Show the items, all selected when the file manager allows it (Windows' Explorer takes
        one ``/select``: the first)."""
        if IS_WINDOWS:
            # Two arguments: Qt quotes a token with a space whole, and Explorer then selects nothing.
            QProcess.startDetached("explorer", ["/select,", os.path.normpath(str(paths[0]))])
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
        """The watcher has no ``isError``: the outcome is read through a ``QDBusPendingReply``."""
        from PyQt6.QtDBus import QDBusPendingReply

        paths = self._reveals.pop(watcher, None)
        try:
            reply = QDBusPendingReply(watcher)
            if reply.isError() and paths:
                log.warning("file: %s.ShowItems failed: %s", FILE_MANAGER, reply.error().message())
                self._open_parent(paths[0])
        finally:
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
        text = ngettext("Copiado: {name}", "Copiados: {n} itens", len(paths)).format(
            name=paths[0].name, n=len(paths)
        )
        self.message.emit(text, "info", 4000)
