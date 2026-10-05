"""The command palette (spec 18 R2): what its rows are and what choosing one does.

Sources, each with a category: the window's enabled actions, the project's folders (an index built
in a worker on the first open, dropped by F5), the favorite and recent folders, and the open tabs.
The ranking is ``core/fuzzy``; the window (``widgets/command_palette``) only shows rows. Nothing
here reads the disk on the GUI thread: the folder walk is the worker's.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget

from ..core.folder_index import MAX_FOLDERS, list_folders
from ..core.fuzzy import SCOPES, Candidate, parse_query, rank
from ..core.nav_store import NavigationStore
from ..core.tasks import TaskHandle, run_task
from .theme.manager import ThemeManager
from .widgets.command_palette import MAX_ROWS, CommandPalette, PaletteRow
from .widgets.workspace import Workspace

ACTIONS, FOLDERS, TABS = SCOPES[">"], SCOPES["/"], SCOPES["@"]
INDEXING = PaletteRow("", "Pasta", "Indexando pastas…", "folder", selectable=False)
SELF_ACTION = "help.palette"


class PaletteController(QObject):
    def __init__(
        self,
        window: QWidget,
        theme: ThemeManager,
        actions: Callable[[], dict[str, QAction]],
        store: NavigationStore,
        workspace: Workspace,
        root: Callable[[], Path],
        hidden_dirs: Callable[[], list[str]],
        open_folder: Callable[[Path], None],
        show_workspace: Callable[[], None],
        view_root: Callable[[], Path] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window, self._actions, self._store = window, actions, store
        self._workspace, self._root, self._hidden = workspace, root, hidden_dirs
        self._view_root = view_root or root  # spec 31: the folder rows are the selected project's
        self._open_folder, self._show_workspace = open_folder, show_workspace
        self.palette = CommandPalette(theme, window)
        self.palette.activated.connect(self.execute)
        self.palette.query_changed.connect(self._refresh)
        self._folders: list[Path] | None = None  # the index; None until built
        self._task: TaskHandle | None = None
        self._stop: threading.Event | None = None
        self._recency: dict[str, int] = {}
        self._clock = 0

    @classmethod
    def for_window(cls, window) -> PaletteController:
        """The controller of a ``MainWindow``: its actions, workspace and navigation."""
        return cls(
            window,
            window.theme,
            lambda: window._actions,
            window.navigation_store,
            window.workspace,
            lambda: window.root,
            lambda: window.config.ui.hidden_dirs,
            window.navigation.open_entry,
            lambda: window.set_panel_visible("workspace", True),
            view_root=lambda: window.project.view_root,
            parent=window,
        )

    # -- the folder index -----------------------------------------------------------------
    @property
    def indexing(self) -> bool:
        return self._task is not None

    def cancel(self) -> None:
        """Window close: the folder walk stops."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._stop is not None:
            self._stop.set()

    def invalidate(self) -> None:
        """Forget the index (F5, a new root); the next open builds it again."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._stop is not None:
            self._stop.set()
            self._stop = None
        self._folders = None
        if self.palette.isVisible():
            self._ensure_index()
            self._refresh()

    def _ensure_index(self) -> None:
        if self._folders is not None or self._task is not None:
            return
        self._stop = threading.Event()
        self._task = run_task(
            list_folders,
            self._root(),
            list(self._hidden()),
            MAX_FOLDERS,
            self._stop.is_set,
            on_done=self._on_indexed,
        )

    def _on_indexed(self, folders: list[Path]) -> None:
        self._task = None
        self._folders = folders
        if self.palette.isVisible():
            self._refresh()

    # -- opening ------------------------------------------------------------------------
    def open(self) -> None:
        self._ensure_index()
        self.palette.set_query("")
        self._refresh()
        self.palette.popup(self.window)

    def _refresh(self, *_args) -> None:
        self.palette.set_rows(self.rows_for(self.palette.query()))

    # -- rows ---------------------------------------------------------------------------
    def rows_for(self, query: str) -> list[PaletteRow]:
        """The rows to show for ``query``: ranked, or the starting list when it is empty."""
        scope, needle = parse_query(query)
        browsing = not needle and scope is None  # nothing typed: no thousand folders
        rows: dict[str, PaletteRow] = {}
        for row in self._favorite_rows() + self._recent_rows() + self._tab_rows():
            rows.setdefault(row.key, row)
        for row in self._action_rows():
            rows.setdefault(row.key, row)
        if not browsing:
            for row in self._folder_rows():
                rows.setdefault(row.key, row)
        candidates = [Candidate(row.key, self._scope_of(row), row.label) for row in rows.values()]
        ranked = rank(query, candidates, self._recency, MAX_ROWS)
        out = [rows[c.key] for c in ranked]
        if self._folders is None and scope in (None, FOLDERS) and not browsing:
            out.append(INDEXING)
        return out

    @staticmethod
    def _scope_of(row: PaletteRow) -> str:
        if row.key.startswith("action:"):
            return ACTIONS
        return TABS if row.key.startswith("tab:") else FOLDERS

    def _action_rows(self) -> list[PaletteRow]:
        rows = []
        for action_id, action in self._actions().items():
            if action_id == SELF_ACTION or not action.isEnabled():
                continue  # a disabled action cannot run; the palette itself is already open
            text = action.text().replace("&", "")
            rows.append(
                PaletteRow(
                    f"action:{action_id}", "Ação", text, "bolt", action.shortcut().toString()
                )
            )
        return rows

    def _label(self, folder: Path) -> str:
        try:
            return folder.relative_to(self._view_root()).as_posix() or folder.name
        except ValueError:
            return str(folder)

    def _folder_row(self, folder: Path, section: str, icon: str) -> PaletteRow:
        return PaletteRow(f"folder:{folder}", section, self._label(folder), icon)

    def _inside(self, folders: list[Path]) -> list[Path]:
        top = self._view_root()
        if top == self._root():
            return folders  # everything is inside the root: no walk over the whole index
        return [folder for folder in folders if folder.is_relative_to(top)]

    def _favorite_rows(self) -> list[PaletteRow]:
        return [
            self._folder_row(f, "Favorito", "star") for f in self._inside(self._store.favorites())
        ]

    def _recent_rows(self) -> list[PaletteRow]:
        return [
            self._folder_row(f, "Recente", "history") for f in self._inside(self._store.recents())
        ]

    def _folder_rows(self) -> list[PaletteRow]:
        return [self._folder_row(f, "Pasta", "folder") for f in self._inside(self._folders or [])]

    def _tab_rows(self) -> list[PaletteRow]:
        keys = {widget: key for key, widget in self._workspace.items()}
        bar = self._workspace.tabs
        rows = []
        for index in range(bar.count()):
            widget = bar.widget(index)
            if widget in keys:
                rows.append(
                    PaletteRow(f"tab:{keys[widget]}", "Aba", bar.tabText(index), "description")
                )
        return rows

    # -- choosing -----------------------------------------------------------------------
    def execute(self, key: str) -> None:
        self._clock += 1
        self._recency[key] = self._clock
        kind, _, value = key.partition(":")
        if kind == "action":
            action = self._actions().get(value)
            if action is not None and action.isEnabled():
                action.trigger()
        elif kind == "folder":
            self._open_folder(Path(value))
        elif kind == "tab":
            widget = self._workspace.widget_for(value)
            if widget is not None:
                self._workspace.set_current(widget)
                self._show_workspace()
