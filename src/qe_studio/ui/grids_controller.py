"""The "Grids" button and window (spec 23 R3): which plots a grid can show, its saved definitions
and its tab.

The grid's tab is an ordinary plot tab (``PlotWorkflow.show_session``); its cells are gathered by
``GridLoader``. The saved grids (``GridStore``) are the workflow's ``Stores.grids``: the grid module
saves the grid's settings there too.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject

from ..core.calculations import REGISTRY
from ..core.grid_store import GridStore
from ..core.plotting.grid import GridSpec, PlotRef
from ..core.plotting.session import PlotSession
from .dialogs.grid_cells import PlotChoice
from .dialogs.grid_dialog import GridDialog
from .grid_loader import GridLoader
from .theme.manager import ThemeManager
from .widgets.plot_view import PlotView
from .widgets.workspace import Workspace


class GridsController(QObject):
    def __init__(
        self,
        window,
        theme: ThemeManager,
        store: GridStore,
        loader: GridLoader,
        workspace: Workspace,
        root: Callable[[], Path],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window, self.theme, self.store, self.loader = window, theme, store, loader
        self.workspace, self._root = workspace, root
        self.dialog: GridDialog | None = None

    @classmethod
    def for_window(cls, window) -> GridsController:
        """The controller of a ``MainWindow``: its workspace tabs, plot workflow and top bar."""
        workflow = window.plot_workflow
        store = workflow.stores.grids
        assert store is not None
        root = lambda: window.root  # noqa: E731 (the project can change: read it every time)
        loader = GridLoader(
            sniff=lambda: window.service.sniff_cache.sniff,
            settings=window.plot_settings,
            open_sessions=lambda: open_sessions(window.workspace),
            config=lambda: window.config,
            root=root,
            memory=window.memory,
            stores=workflow.stores,
            busy=workflow.busy,
            parent=window,
        )
        controller = cls(window, window.theme, store, loader, window.workspace, root, window)
        loader.ready.connect(workflow.show_session)
        window.top_bar.grids_requested.connect(controller.open)
        return controller

    # -- the window ----------------------------------------------------------------------------
    def open(self) -> None:
        """One non-modal window: asking again brings the open one to the front."""
        self.store.set_root(self._root())
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        dialog = GridDialog(self.theme, self.store, self.choices, self.describe, self.window)
        dialog.generate_requested.connect(self.generate)
        dialog.finished.connect(self._on_dialog_closed)  # closed: a new click opens a new one
        dialog.destroyed.connect(self._on_dialog_closed)
        self.dialog = dialog
        dialog.show()

    def _on_dialog_closed(self, *_args) -> None:
        self.dialog = None

    def close_dialog(self) -> bool:
        """The main window is closing. Nothing to protect here ("Gerar" saves, "Cancelar" drops
        the draft by design), so it always closes (spec 27-5 R2.3)."""
        dialog = self.dialog
        return dialog is None or dialog.close()

    def choices(self) -> list[PlotChoice]:
        """The open plot tabs a cell can show (a grid cannot be a cell), in tab order."""
        return [
            PlotChoice(s.title + self._where(s.paths[0]), s.ref)
            for s in open_sessions(self.workspace)
            if s.module.grid_cell
        ]

    def describe(self, ref: PlotRef) -> PlotChoice:
        """A saved cell's plot that is not open: its kind and path, and whether it is gone."""
        module = next((m for m in REGISTRY if m.kind == ref.kind), None)
        name = module.display_name if module is not None else ref.kind
        # Accepted, local disk: a stat per path of one reference, at most 6×6 of them (spec 27-8 R3.3).
        missing = not all(path.exists() for path in ref.paths)
        return PlotChoice(f"{name} · {ref.path.name}{self._where(ref.path)}", ref, missing)

    def _where(self, path: Path) -> str:
        """`` — <folder>``: where ``path`` is, relative to the project (nothing at its top)."""
        root, parent = self._root(), path.parent
        if parent == root:
            return ""
        try:
            where = os.path.relpath(parent, root) if parent.is_relative_to(root) else str(parent)
        except ValueError:
            where = str(parent)
        return f" — {where}"

    # -- grids ---------------------------------------------------------------------------------
    def generate(self, spec: GridSpec) -> None:
        """The grid's tab, once its cells are loaded (the window saved it already)."""
        self.loader.load(spec)

    def rename(self, old: Path, new: Path) -> None:
        """A folder or file was renamed: the saved grids follow it."""
        self.store.set_root(self._root())
        self.store.rename(old, new)


def open_sessions(workspace: Workspace) -> list[PlotSession]:
    return [w.session for _key, w in workspace.items() if isinstance(w, PlotView)]
