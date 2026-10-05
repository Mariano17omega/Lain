"""The sessions of a grid's cells (spec 23 R3.4), then the grid's own session.

A cell whose plot is open in a tab takes a copy of that session as it is now (unsaved edits too). The
others load like a plot does, off the GUI thread: detection and data in the global pool
(``ref_target`` + ``load_plot``), then the ``.plot`` through the settings queue (after any write still
pending for it) and ``build_session``. A cell that cannot load is drawn as "Plot indisponível".
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.calculations import DetectionResult
from ..core.calculations.base import LoadError, SniffFn, Stores
from ..core.calculations.grid import GridCellData
from ..core.config import AppConfig
from ..core.detection import ref_target
from ..core.folder_memory import FolderMemory
from ..core.plotting.grid import GridCell, GridSpec, PlotRef
from ..core.plotting.grid_session import build_grid_session
from ..core.plotting.session import PlotSession, build_session, load_plot
from ..core.tasks import TaskGroup
from .busy import BusyTracker
from .plot_settings import PlotSettingsStore

log = logging.getLogger(__name__)


def load_cell(ref: PlotRef, sniff: SniffFn, memory: FolderMemory) -> tuple[DetectionResult, Any]:
    """Worker: the result and data of a cell's plot (``LoadError`` when its folder is gone)."""
    return load_plot(ref_target(ref, sniff, memory), sniff)


def error_text(error: Exception) -> str:
    if isinstance(error, LoadError):
        return str(error)
    log.error("grid cell failed to load", exc_info=error)
    return f"{type(error).__name__}: {error}"


@dataclass
class _GridLoad:
    spec: GridSpec
    cells: dict[tuple[int, int], GridCellData] = field(default_factory=dict)
    waiting: dict[str, GridCell] = field(default_factory=dict)  # by task key
    loaded: dict[str, tuple[DetectionResult, Any]] = field(default_factory=dict)


class GridLoader(QObject):
    ready = pyqtSignal(object)  # PlotSession of the grid

    def __init__(
        self,
        *,
        sniff: Callable[[], SniffFn],
        settings: PlotSettingsStore,
        open_sessions: Callable[[], list[PlotSession]],
        config: Callable[[], AppConfig],
        root: Callable[[], Path],
        memory: FolderMemory,
        stores: Stores,
        busy: BusyTracker,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._sniff, self.settings, self._open_sessions = sniff, settings, open_sessions
        self._config, self._root = config, root
        self.memory, self.stores, self.busy = memory, stores, busy
        self._tasks = TaskGroup()  # by cell key, in the global pool
        self._loads: dict[str, _GridLoad] = {}  # by grid name: the one being loaded
        self._generation = itertools.count()

    def load(self, spec: GridSpec) -> None:
        """Gather the cells of ``spec``; ``ready`` carries the grid's session when all are in.
        Asking again for the same grid drops what the previous request still loads."""
        self.cancel(spec.name)
        state = _GridLoad(spec)
        self._loads[spec.name] = state
        generation = next(self._generation)
        open_plots = {s.ref: s for s in self._open_sessions() if s.module.grid_cell}
        for cell in spec.cells:
            if cell.ref is None:
                continue
            session = open_plots.get(cell.ref)
            if session is not None:
                state.cells[(cell.row, cell.col)] = GridCellData(cell, session.copy())
                continue
            key = f"{spec.name}#{generation}:{cell.row},{cell.col}"
            state.waiting[key] = cell
            self._tasks.submit(
                key,
                load_cell,
                cell.ref,
                self._sniff(),
                self.memory,
                on_done=self._on_data,
                on_error=self._on_error,
            )
        if state.waiting:
            self.busy.begin(self._busy_name(spec.name), "Carregando grid…")
        self._finish_if_done(state)

    def cancel_all(self) -> None:
        """Window close: no grid goes on loading."""
        for name in list(self._loads):
            self.cancel(name)
        self._tasks.cancel_all()

    def cancel(self, name: str) -> None:
        state = self._loads.pop(name, None)
        if state is not None:
            for key in state.waiting:
                self._tasks.cancel(key)
            self.busy.end(self._busy_name(name))

    # -- cells ---------------------------------------------------------------------------------
    def _state_of(self, key: str) -> _GridLoad | None:
        return next((s for s in self._loads.values() if key in s.waiting), None)

    def _on_data(self, key: str, loaded: tuple[DetectionResult, Any]) -> None:
        state = self._state_of(key)
        if state is None:
            return
        state.loaded[key] = loaded
        result = loaded[0]
        self.settings.read(
            key, result.folder, result.kind, on_done=self._on_stored, on_error=self._on_error
        )

    def _on_stored(self, key: str, stored: tuple[dict[str, Any] | None, list[str]]) -> None:
        state = self._state_of(key)
        if state is None or key not in state.loaded:
            return
        result, dataset = state.loaded.pop(key)
        session, _warnings = build_session(
            result, dataset, self._config(), stored, self.memory, None, self.stores
        )
        self._set_cell(state, key, GridCellData(state.waiting[key], session))

    def _on_error(self, key: str, error: Exception) -> None:
        state = self._state_of(key)
        if state is not None:
            state.loaded.pop(key, None)
            self._set_cell(state, key, GridCellData(state.waiting[key], None, error_text(error)))

    def _set_cell(self, state: _GridLoad, key: str, data: GridCellData) -> None:
        cell = state.waiting.pop(key)
        state.cells[(cell.row, cell.col)] = data
        self._finish_if_done(state)

    # -- the grid ------------------------------------------------------------------------------
    def _finish_if_done(self, state: _GridLoad) -> None:
        if state.waiting or self._loads.get(state.spec.name) is not state:
            return
        del self._loads[state.spec.name]
        self.busy.end(self._busy_name(state.spec.name))
        session = build_grid_session(
            state.spec, state.cells.values(), self._root(), self._config(), self.memory, self.stores
        )
        self.ready.emit(session)

    @staticmethod
    def _busy_name(name: str) -> str:
        return f"grid:{name}"
