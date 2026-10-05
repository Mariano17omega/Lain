"""Plot settings files ``<simulation>/<kind>.plot``: written after edits, off the GUI thread.

Every read, write and removal runs in one private single-thread pool, so they happen in the order
they were asked for (a regenerate reads what closing the tab just wrote) and the GUI thread never
waits for a slow disk (spec 15 R3.7). ``flush_now`` writes on the spot: on window close, and before
a rename moves the folder.
"""

from __future__ import annotations

import copy
import logging
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QThreadPool, QTimer, pyqtSignal

from ..core.plotting.plot_file import (
    WriteOrder,
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


def _write(order: WriteOrder, ticket: int, folder: Path, kind: str, params: object) -> str | None:
    """Worker (or the GUI thread, from ``flush_now``): write the file unless a newer write of it
    already happened; the warning for the user if it cannot be written."""
    try:
        order.run(
            plot_file_path(folder, kind), ticket, lambda: write_plot_file(folder, kind, params)
        )
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
        self._order = WriteOrder()  # a write queued before a newer one never lands after it
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
                session.key,
                _write,
                self._order,
                self._order.ticket(),
                session.folder,
                session.kind,
                params,
                on_done=self._report,
            )

    def flush_now(
        self, key: str | None = None, inside: Path | None = None, timeout_ms: int | None = None
    ) -> bool:
        """Write the pending settings here and now: all, the plot ``key`` or the plots that show
        something ``inside`` a path (a rename is about to move it). Writes already queued land
        first, unless the disk is too slow (``timeout_ms``): then what is still queued is older
        than what is written here and, by its ticket, does not overwrite it. ``timeout_ms`` is
        ``DRAIN_MS`` unless given. False: it did not drain in time (all pending was written anyway)."""
        timeout_ms = DRAIN_MS if timeout_ms is None else timeout_ms
        if key is None and inside is None:
            self._timer.stop()
        drained = self._pool.waitForDone(timeout_ms)
        if not drained:
            log.warning("plot settings: writes still queued after %d ms; writing now", timeout_ms)
        for session in self._take(key, inside):
            ticket = self._order.ticket()
            self._report(
                session.key,
                _write(self._order, ticket, session.folder, session.kind, session.params),
            )
        return drained

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

    def shutdown(self, timeout_ms: int | None = None) -> bool:
        """Window close, after ``flush_now``: nothing may stay queued behind a slow disk. The
        two queues share ``timeout_ms`` (``DRAIN_MS`` unless given)."""
        timeout_ms = DRAIN_MS if timeout_ms is None else timeout_ms
        deadline = time.monotonic() + timeout_ms / 1000
        self._timer.stop()
        reads = self._reads.shutdown(timeout_ms)
        left = max(0, int((deadline - time.monotonic()) * 1000))
        return self._writes.shutdown(left) and reads

    def close(self, timeout_ms: int | None = None) -> bool:
        """Window close: write what is pending and stop both queues, all within ``timeout_ms``
        (``DRAIN_MS`` unless given): one drain, not one wait per step."""
        timeout_ms = DRAIN_MS if timeout_ms is None else timeout_ms
        deadline = time.monotonic() + timeout_ms / 1000
        drained = self.flush_now(timeout_ms=timeout_ms)
        left = max(0, int((deadline - time.monotonic()) * 1000))
        return self.shutdown(left) and drained

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
