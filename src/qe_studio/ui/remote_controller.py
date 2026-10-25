"""The cluster mode (spec 65): the cluster's folders in the tree and its files in the grid, on a red
background, until the sidebar's "Cluster" is clicked again.

What is shown is listed over ssh (``core/remote/listing.py``) in a pool of two threads of its own,
one listing per folder at a time (a ``TaskGroup`` keyed by the folder): a click elsewhere in the grid
cancels the listing of the folder it leaves, unless the tree waits for it too. Every listing goes to
the session's cache (``RemoteBrowser``): a folder listed before shows at once, and is listed again in
the background when older than ``STALE_SECONDS``; F5 and "Atualizar" list the folder shown again.

Nothing local is read or changed: the local panels stay under the cluster's ones (pages of the left
panel and of the file panel) and come back as they were. "Baixar" is the pull of always
(``SyncCoordinator.start``): of the local mirror of a folder, or of a file's folder narrowed to it.
"Plotar", and the sidebar's "Plot", "Gerar" and Ctrl+G while the mode is on, plot a copy of the
folder in its mirror's ``tmp_remote/`` (spec 66, ``RemotePlot``).

With ``auth: password`` and no password known, only what the user does asks for it (turning the mode
on, "Tentar de novo", "Atualizar", F5); a refused login forgets it and nothing retries on its own.
The answers feed the LED as the jobs' do (spec 64).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Hashable
from pathlib import Path, PurePosixPath

from PyQt6.QtCore import QObject, QPoint, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from ..core.config import AppConfig
from ..core.remote.browser import RemoteBrowser
from ..core.remote.listing import RemoteEntry, RemoteFailure, list_remote
from ..core.sync.request import SYNC_OFF, SYNC_RUNNING
from ..core.tasks import TaskGroup
from ..i18n import _, ngettext
from .busy import BusyTracker
from .footer_path import FooterPath
from .layout_controller import LayoutController
from .remote_plot import RemotePlot
from .sync_coordinator import SyncCoordinator
from .widgets.bars import REMOTE_TIP, ActivityButton, TopBar
from .widgets.file_grid import FilePanel
from .widgets.remote_model import RemotePath
from .widgets.remote_panels import RemoteFilePanel, RemoteTreePanel
from .widgets.toast import Toast
from .widgets.workspace_tabs import add_action

log = logging.getLogger(__name__)

BUSY_KEY = "remote:list"
LISTING = _("Listando no cluster…")
ONE_ITEM = _("Selecione um item para baixar.")
PICK = _("Selecione uma ou duas pastas para plotar.")  # spec 66 R4.2
CONFIG_CHANGED = _("Modo cluster desligado: a configuração mudou.")
NO_PASSWORD = _("Senha do cluster não informada: clique em Tentar de novo.")


def _subfolders(entries: list[RemoteEntry]) -> list[str]:
    return [entry.name for entry in entries if entry.is_dir]


class RemoteController(QObject):
    listed = pyqtSignal(str, object)  # folder, list[RemoteEntry] | RemoteFailure (tests wait on it)
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)

    def __init__(
        self,
        tree_panel: RemoteTreePanel,
        file_panel: RemoteFilePanel,
        button: ActivityButton,
        layout: LayoutController,
        files: FilePanel,
        top_bar: TopBar,
        footer: FooterPath,
        sync: SyncCoordinator,
        busy: BusyTracker,
        toast: Toast,
        config: AppConfig,
        view_root: Callable[[], Path],
        plotter: RemotePlot,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.tree_panel, self.file_panel, self.button = tree_panel, file_panel, button
        self.plotter = plotter
        self.layout, self.files, self.top_bar, self.footer = layout, files, top_bar, footer
        self.sync, self.busy, self.toast, self.config = sync, busy, toast, config
        self._view_root = view_root
        self.active = False
        self.browser: RemoteBrowser | None = None  # with the cache of the session
        self.current = ""  # the folder the grid shows
        self._walking = False  # the start folder goes up while the cluster does not have it
        self._tree_wanted: set[str] = set()  # folders whose subfolders the tree waits for
        self._local_tree: QWidget | None = None  # the left panel's tree page before the mode
        self._clock: Callable[[], float] = time.monotonic
        self._pool = QThreadPool()  # no Qt parent (CLAUDE.md, Threading)
        self._pool.setMaxThreadCount(2)
        self._tasks = TaskGroup(self._pool)
        tree_panel.folder_selected.connect(self.open)
        tree_panel.model.fetch_requested.connect(self._on_fetch)
        tree_panel.refresh_requested.connect(self.refresh)
        tree_panel.menu_requested.connect(self.show_menu)
        file_panel.folder_activated.connect(self.open)
        file_panel.up_requested.connect(self.go_up)
        file_panel.retry_requested.connect(self.refresh)
        file_panel.menu_requested.connect(self.show_menu)
        self._update_button()

    @classmethod
    def for_window(cls, window) -> RemoteController:
        """The cluster's panels become pages of the window's left panel and file panel; the
        sidebar's "Cluster", the project and "Revelar no explorador" drive the mode."""
        tree_panel, file_panel = RemoteTreePanel(window.theme), RemoteFilePanel(window.theme)
        window.left.addWidget(tree_panel)
        window.files.pages.addWidget(file_panel)
        controller = cls(
            tree_panel,
            file_panel,
            window.activity.remote,
            window.panel_layout,
            window.files,
            window.top_bar,
            window.footer,
            window.sync,
            window.plot_workflow.busy,
            window.toast,
            window.config,
            view_root=lambda: window.project.view_root,
            plotter=RemotePlot(window.sync, window.plot_workflow, window),
            parent=window,
        )
        window.activity.remote_toggled.connect(controller.set_active)
        window.project.project_changed.connect(controller.on_project_changed)
        # Before the window's own slot (connected later): the local tree is the one to reveal in.
        window.workspace.reveal_requested.connect(controller.leave)
        controller.message.connect(window.status.set_message)
        return controller

    @property
    def enabled(self) -> bool:
        """A cluster to list: the one sync uses."""
        return self.config.sync_enabled

    # -- on and off ------------------------------------------------------------------------------
    def toggle(self) -> None:
        """ "Ver arquivos do cluster" of the "Cluster" menu."""
        self.set_active(not self.active)

    def set_active(self, on: bool) -> None:
        if on and not self.active:
            self._turn_on()
        elif not on and self.active:
            self._turn_off()
        self._update_button()

    def leave(self, *_args) -> None:
        """Back to the local files (a local item is about to be revealed)."""
        self.set_active(False)

    def _update_button(self) -> None:
        self.button.setEnabled(self.enabled)
        self.button.setToolTip(REMOTE_TIP if self.enabled else SYNC_OFF)
        self.button.setChecked(self.active)

    def _turn_on(self) -> None:
        if not self.enabled:
            self.message.emit(SYNC_OFF, "warning", 5000)
            return
        if self._needs_password() and self.sync.session_password(ask=True) is None:
            return
        try:
            if self.browser is None:
                self.browser = RemoteBrowser(self.config, self._view_root())
            else:
                self.browser.set_view_root(self._view_root())
            start = self.browser.remote_of(self.files.folder)
        except ValueError as exc:  # a folder outside ``paths.local_root``
            self.message.emit(str(exc), "warning", 6000)
            return
        browser = self.browser
        self.active = True
        self._local_tree = self.layout.tree_page
        self.layout.set_tree_page(self.tree_panel)
        self.layout.set_left_mode("tree")
        self.files.show_alternate(self.file_panel)
        self.layout.set_panel_visible("grid", True)
        self.top_bar.set_remote(True)
        self._reset_tree()
        self.open(start if browser.inside(start) else browser.top, walk_up=True)

    def _turn_off(self) -> None:
        self.active = False
        self._tasks.cancel_all()
        self._tree_wanted.clear()
        self._update_busy()
        if self._local_tree is not None:
            self.layout.set_tree_page(self._local_tree)
        self.files.show_alternate(None)
        self.top_bar.set_remote(False)
        self.footer.set_remote(None)

    def _reset_tree(self) -> None:
        browser = self.browser
        assert browser is not None
        self._tree_wanted.clear()
        self.tree_panel.reset(browser.top, browser.account)
        self.tree_panel.model.request(browser.top)  # its folders, without waiting for the view

    def set_config(self, config: AppConfig) -> None:
        """ "Recarregar config.yaml": the mode turns off and the cache goes (another cluster)."""
        if self.active:
            self.set_active(False)
            # A toast: the footer gets "config.yaml recarregado." right after this.
            self.toast.show_message(CONFIG_CHANGED)
        self._tasks.cancel_all()
        self.config, self.browser = config, None
        self._update_button()

    def on_project_changed(self, _top: object) -> None:
        """Another project with the mode on: its top, from the top."""
        if self.active and self.browser is not None:
            self.browser.set_view_root(self._view_root())
            self._reset_tree()
            self.open(self.browser.top)

    def cancel(self) -> None:
        """Window close (the "cancelar" step): no listing; a running one has its ssh killed within
        ``core/sync/command.py:POLL_SECONDS``."""
        self._tasks.shutdown(0)

    # -- navigation ------------------------------------------------------------------------------
    def open(self, remote_dir: str, walk_up: bool = False) -> None:
        """Show ``remote_dir`` in the grid: a folder of the tree, or one entered in the grid. A
        folder in the cache shows at once (listed again in the background when it is old)."""
        browser = self.browser
        if not self.active or browser is None or not browser.inside(remote_dir):
            return
        left, self.current, self._walking = self.current, remote_dir, walk_up
        if left != remote_dir and left not in self._tree_wanted:
            self._tasks.cancel(left)  # the click elsewhere replaces it
        self.file_panel.set_folder(remote_dir, browser.parent(remote_dir))
        self.tree_panel.reveal(remote_dir)
        self.footer.set_remote(browser.label(remote_dir))
        cached = browser.get(remote_dir)
        if cached is None:
            self.file_panel.set_loading(True)
            self._request(remote_dir)
        else:
            self.file_panel.show_entries(cached)
            if browser.needs_refresh(remote_dir, self._clock()):
                self._request(remote_dir)
        self._update_busy()

    def go_up(self) -> None:
        """Backspace, Alt+↑: the folder above, never above the top."""
        parent = self.browser.parent(self.current) if self.browser is not None else None
        if parent is not None:
            self.open(parent)

    def refresh(self) -> bool:
        """F5, "Atualizar", "Tentar de novo": the folder shown, listed again. False when the mode
        is off (F5 is then the local refresh)."""
        browser = self.browser
        if not self.active or browser is None:
            return False
        if self._needs_password() and self.sync.session_password(ask=True) is None:
            return True
        browser.invalidate(self.current)
        self._tasks.cancel(self.current)  # one started before may predate what changed
        self.tree_panel.model.retry_failed()
        self.tree_panel.model.request(browser.top)  # its folders, if the first listing failed
        if self.file_panel.failed:
            self.file_panel.set_folder(self.current, browser.parent(self.current))
        self.file_panel.set_loading(True)
        self._request(self.current)
        return True

    def _on_fetch(self, remote_dir: str) -> None:
        """The tree opened ``remote_dir``: its subfolders, from the cache or listed."""
        browser = self.browser
        if not self.active or browser is None:
            return
        cached = browser.get(remote_dir)
        if cached is not None:
            self.tree_panel.set_subfolders(remote_dir, _subfolders(cached))
            if not browser.needs_refresh(remote_dir, self._clock()):
                return
        else:
            self._tree_wanted.add(remote_dir)
        self._request(remote_dir)

    # -- listings --------------------------------------------------------------------------------
    def _needs_password(self) -> bool:
        cluster = self.config.cluster
        return cluster.auth == "password" and cluster.resolve_password() is None

    def _password(self) -> str | None:
        """The one typed in this session, when the config has none (``child_env`` reads the
        config's itself)."""
        return self.sync.session_password(ask=False) if self._needs_password() else None

    def _request(self, remote_dir: str) -> None:
        if self._tasks.active(remote_dir) is not None:
            return  # being listed: its answer goes to the tree and the grid alike
        password = self._password()
        if password is None and self._needs_password():
            self._deliver(remote_dir, RemoteFailure(NO_PASSWORD, local=True))
            return
        self._tasks.submit(
            remote_dir,
            list_remote,
            self.config,
            remote_dir,
            password,
            on_done=self._on_listed,
            on_error=self._on_error,
        )
        self._update_busy()

    def _update_busy(self) -> None:
        if len(self._tasks):
            self.busy.begin(BUSY_KEY, LISTING)
        else:
            self.busy.end(BUSY_KEY)

    def _on_error(self, key: Hashable, error: Exception) -> None:
        log.error("listing the cluster failed", exc_info=error)
        message = _("Falha ao listar a pasta: {error}").format(error=error)
        self._on_listed(key, RemoteFailure(message, local=True))

    def _on_listed(self, key: Hashable, result: list[RemoteEntry] | RemoteFailure) -> None:
        self._deliver(str(key), result)

    def _deliver(self, remote_dir: str, result: list[RemoteEntry] | RemoteFailure) -> None:
        self._update_busy()
        browser = self.browser
        if not self.active or browser is None:
            return
        self._report(result)
        tree_waits = remote_dir in self._tree_wanted
        self._tree_wanted.discard(remote_dir)
        if isinstance(result, RemoteFailure):
            if tree_waits:
                self.tree_panel.model.mark_failed(remote_dir)
            if remote_dir == self.current:
                self._show_failure(remote_dir, result)
        else:
            browser.put(remote_dir, result, self._clock())
            self.tree_panel.set_subfolders(remote_dir, _subfolders(result))
            if remote_dir == self.current:
                self._walking = False
                self.file_panel.show_entries(result)
            if PurePosixPath(self.current).is_relative_to(remote_dir):
                self.tree_panel.reveal(self.current)  # the tree may now reach the folder shown
        self.listed.emit(remote_dir, result)

    def _report(self, result: list[RemoteEntry] | RemoteFailure) -> None:
        """The LED, as the jobs' answers feed it; a refused login forgets the password."""
        monitor = self.sync.monitor
        if not isinstance(result, RemoteFailure):
            monitor.report(True)
            return
        if result.connection:
            monitor.report(False)
        elif not (result.auth or result.local):
            monitor.report(True)  # the cluster answered: it is the folder that failed
        if result.auth:
            self.sync.forget_password()

    def _show_failure(self, remote_dir: str, failure: RemoteFailure) -> None:
        browser = self.browser
        assert browser is not None
        parent = browser.parent(remote_dir)
        if failure.missing and self._walking and parent is not None:
            self.open(parent, walk_up=True)  # the start folder is not on the cluster: go up
            return
        self._walking = False
        if failure.missing:
            browser.invalidate(remote_dir)
        if browser.get(remote_dir) is not None:  # a cached listing stays on screen
            self.file_panel.set_loading(False)
            self.message.emit(failure.message, "warning", 6000)
        else:
            self.file_panel.show_failure(failure.message)

    # -- the menu (R5) ---------------------------------------------------------------------------
    def show_menu(self, items: list[RemotePath], pos: QPoint) -> None:
        """ "Baixar" and "Copiar caminho": nothing of the local menu (sending, renaming, opening)."""
        if not items:
            return
        menu = QMenu(self.file_panel)
        menu.setToolTipsVisible(True)  # the reason of a disabled item
        reason = self.download_blocked(items)
        first = items[0]
        add_action(
            menu, _("Baixar"), lambda: self.download(first), enabled=not reason, tooltip=reason
        )
        if all(item.is_dir for item in items):  # spec 66 R4.1: never of a file
            reason = self.plot_blocked(items) or (SYNC_RUNNING if self.sync.running else "")
            add_action(
                menu,
                _("Plotar"),
                lambda: self.plot_items(items),
                enabled=not reason,
                tooltip=reason,
            )
        add_action(menu, _("Copiar caminho"), lambda: self.copy_paths(items))
        menu.exec(pos)
        menu.deleteLater()

    def download_blocked(self, items: list[RemotePath]) -> str:
        """Why "Baixar" is disabled; "" when it is not."""
        if len(items) != 1:
            return ONE_ITEM
        if self.sync.running:
            return SYNC_RUNNING
        return ""

    def download(self, item: RemotePath) -> None:
        """The pull of a folder's local mirror (made when missing), or of a file's folder narrowed
        to it: dry run, preview and conflict questions as always."""
        browser = self.browser
        if browser is None:
            return
        if item.is_dir:
            self.sync.start(browser.mirror_of(item.path))
            return
        path = PurePosixPath(item.path)
        self.sync.start(browser.mirror_of(str(path.parent)), only=path.name)

    # -- plotting (spec 66) ----------------------------------------------------------------------
    def plot(self, generate: bool) -> bool:
        """The sidebar's "Plot" (``generate`` False), "Gerar" and Ctrl+G: with the mode on, of the
        list's selection, or of the folder shown when nothing is selected. False when the mode is
        off (the window plots the local selection)."""
        if not self.active or self.browser is None:
            return False
        items = self.file_panel.selected_paths() or [RemotePath(self.current, True)]
        self.plot_items(items, generate)
        return True

    @staticmethod
    def plot_blocked(items: list[RemotePath]) -> str:
        """Why ``items`` cannot be plotted; "" when they can (one or two folders)."""
        ok = 1 <= len(items) <= 2 and all(item.is_dir for item in items)
        return "" if ok else PICK

    def plot_items(self, items: list[RemotePath], generate: bool = False) -> None:
        """Copy ``items`` into their mirrors' ``tmp_remote/`` and plot the copies."""
        browser = self.browser
        if browser is None:
            return
        if reason := self.plot_blocked(items):
            self.message.emit(reason, "warning", 5000)
            return
        self.plotter.plot([browser.mirror_of(item.path) for item in items], generate)

    def copy_paths(self, items: list[RemotePath]) -> None:
        """The cluster paths, one per line."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(item.path for item in items))
        text = ngettext("Copiado: {name}", "Copiados: {n} itens", len(items))
        self.message.emit(text.format(name=items[0].path, n=len(items)), "info", 4000)
