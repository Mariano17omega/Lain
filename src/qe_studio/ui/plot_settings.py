"""Plot settings files ``<simulation>/<kind>.plot``: written after edits, off the GUI thread.

Every read, write and removal runs in one private single-thread pool, so they happen in the order
they were asked for (a regenerate reads what closing the tab just wrote) and the GUI thread never
waits for a slow disk (spec 15 R3.7). ``flush_now`` writes on the spot: on window close, and before
a rename moves the folder.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QThreadPool, QTimer, pyqtSignal

from ..core.plotting.plot_file import (
    delete_plot_file,
    plot_file_path,
    read_plot_file,
    write_plot_file,
)
from ..core.plotting.session import PlotSession
from ..core.tasks import TaskGroup

log = logging.getLogger(__name__)
SAVE_DEBOUNCE_MS = 1000
DRAIN_MS = 5000  # flush_now: how long the queued writes may take before writing anyway


def _write(folder: Path, kind: str, params: object) -> str | None:
    """Worker: write the file; the warning for the user if it cannot be written."""
    try:
        write_plot_file(folder, kind, params)
    except OSError as exc:
        log.warning("cannot save %s.plot in %s: %s", kind, folder, exc)
        return f"Não foi possível salvar {kind}.plot em {folder.name}: {exc.strerror or exc}"
    return None


def _delete(folder: Path, kind: str) -> str | None:
    try:
        delete_plot_file(folder, kind)
    except OSError as exc:
        return f"Não foi possível apagar {plot_file_path(folder, kind).name}: {exc}"
    return None


class PlotSettingsStore(QObject):
    """Pending edits by plot key, written 1 s after the last one (or at once when asked)."""

    warning = pyqtSignal(str)  # a file could not be written or removed (once per plot and run)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = QThreadPool()  # no Qt parent: see core/tasks.py, "private pools"
        self._pool.setMaxThreadCount(1)  # one at a time: the queue keeps the order
        self._writes = TaskGroup(self._pool)  # by plot key: a newer write or a removal wins
        self._reads = TaskGroup(self._pool)
        self._dirty: dict[str, PlotSession] = {}  # edited since their last write, by plot key
        self._warned: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SAVE_DEBOUNCE_MS)
        self._timer.timeout.connect(self.flush)

    def is_dirty(self, key: str) -> bool:
        return key in self._dirty

    def mark(self, session: PlotSession) -> None:
        """The user edited ``session`` (panel or pan/zoom): write it after a pause. A plot without
        a ``.plot`` (a grid: ``plot_file`` False) has nothing to write."""
        if not session.module.plot_file:
            return
        self._dirty[session.key] = session
        self._timer.start()

    def flush(self, key: str | None = None) -> None:
        """Write the pending settings (all, or the plot ``key``) in the worker."""
        for session in self._take(key):
            params = copy.deepcopy(session.params)  # edits go on while the worker writes
            self._writes.submit(
                session.key, _write, session.folder, session.kind, params, on_done=self._report
            )

    def flush_now(self, key: str | None = None, inside: Path | None = None) -> None:
        """Write the pending settings here and now: all, the plot ``key`` or the plots that show
        something ``inside`` a path (a rename is about to move it). Writes already queued land
        first."""
        if key is None and inside is None:
            self._timer.stop()
        self._pool.waitForDone(DRAIN_MS)
        for session in self._take(key, inside):
            self._report(session.key, _write(session.folder, session.kind, session.params))

    def read(
        self, key: str, folder: Path, kind: str, on_done: Callable, on_error: Callable
    ) -> None:
        """``read_plot_file`` in the worker, after the writes asked before it; then
        ``on_done(key, (params or None, warnings))``."""
        self._reads.submit(key, read_plot_file, folder, kind, on_done=on_done, on_error=on_error)

    def delete(self, session: PlotSession) -> None:
        """ "Restaurar padrões": drop the pending edits and remove the file, after the queued
        writes (a write still queued for it is dropped)."""
        self._dirty.pop(session.key, None)
        if not session.module.plot_file:
            return
        self._writes.submit(
            session.key, _delete, session.folder, session.kind, on_done=self._report
        )

    def shutdown(self, timeout_ms: int = DRAIN_MS) -> bool:
        """Window close, after ``flush_now``: nothing may stay queued behind a slow disk."""
        self._timer.stop()
        reads = self._reads.shutdown(timeout_ms)
        return self._writes.shutdown(timeout_ms) and reads

    def _take(self, key: str | None = None, inside: Path | None = None) -> list[PlotSession]:
        if inside is not None:  # plots of a folder inside it, or of a file inside it (SCF)
            keys = [
                k
                for k, s in self._dirty.items()
                if s.folder.is_relative_to(inside) or s.plot_target.is_relative_to(inside)
            ]
        else:
            keys = list(self._dirty) if key is None else [key]
        return [s for s in (self._dirty.pop(k, None) for k in keys) if s is not None]

    def _report(self, key: str, warning: str | None) -> None:
        if warning is not None and key not in self._warned:
            self._warned.add(key)
            self.warning.emit(warning)
