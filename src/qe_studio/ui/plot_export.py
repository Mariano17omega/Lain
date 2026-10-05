"""Saving a plot into ``<simulation>/plots/`` (PRD §4.4) without blocking the window (spec 15 R3).

``core`` plans (``plan_export``) and writes (``export_figure``, in a worker with its own figure,
serialized with the screen by ``MPL_LOCK``); this asks before overwriting, on the GUI thread, and
reports.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from ..core.plotting.export import export_figure, plan_export
from ..core.plotting.session import PlotSession
from ..core.tasks import TaskGroup
from .busy import BusyTracker
from .dialogs.overwrite import OverwriteChoice, ask_overwrite

log = logging.getLogger(__name__)
EXPORT_WAIT_MS = 10_000  # window close waits this long for exports (no half-written files)


class PlotExporter(QObject):
    finished = pyqtSignal(object)  # list[Path] written into plots/
    message = pyqtSignal(str, str, int)  # text, level, timeout (ms)

    def __init__(self, busy: BusyTracker, dialog_parent: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        self.busy = busy
        self._dialog_parent = dialog_parent
        self._tasks = TaskGroup()  # by plot key, in the global pool
        self._overwrite_always = False  # "Sempre" in the overwrite dialog, for this run

    def export(self, session: PlotSession) -> bool:
        """Save ``session`` in the configured formats; returns whether an export started.

        Existing files are never overwritten without asking (PRD §7 data integrity): the question
        comes first, then the worker writes.
        """
        plan = plan_export(session)  # stats the targets on this thread: see its docstring
        if plan.error is not None:
            self.message.emit(plan.error, "warning", 4000)
            return False
        stem = plan.stem
        if plan.existing and not self._overwrite_always:
            assert plan.new_stem is not None
            choice, remember = ask_overwrite(self._dialog_parent, plan.existing, plan.new_stem)
            if choice is OverwriteChoice.CANCEL:
                self.message.emit("Exportação cancelada.", "info", 3000)
                return False
            if choice is OverwriteChoice.NEW_VERSION:
                stem = plan.new_stem
            self._overwrite_always = remember
        params = copy.deepcopy(session.params)  # edits made meanwhile are not this export's
        self.busy.begin(f"export:{session.key}", "Exportando…")
        self._tasks.submit(
            session.key,
            export_figure,
            session.module,
            session.dataset,
            params,
            session.style,
            session.folder,
            stem,
            plan.formats,
            on_done=self._on_done,
            on_error=self._on_failed,
        )
        return True

    @property
    def running(self) -> bool:
        """Is a figure being written? (A rename waits for none: it is refused meanwhile.)"""
        return len(self._tasks) > 0

    def wait(self) -> bool:
        """Block until the running exports are written (before a rename moves their folder)."""
        return self._tasks.wait(EXPORT_WAIT_MS)

    def shutdown(self, timeout_ms: int = EXPORT_WAIT_MS) -> bool:
        """Window close: every export asked for is written first (up to ``timeout_ms``), so
        no file is left half written; whatever is left after that is dropped."""
        written = self._tasks.wait(timeout_ms)
        self._tasks.shutdown(0)
        return written

    def _on_done(self, key: str, written: list[Path]) -> None:
        self.busy.end(f"export:{key}")
        names = ", ".join(p.name for p in written)
        self.message.emit(f"Salvo em plots/: {names}", "info", 8000)
        self.finished.emit(written)

    def _on_failed(self, key: str, error: Exception) -> None:
        self.busy.end(f"export:{key}")
        if not isinstance(error, OSError | ValueError):
            log.error("export failed", exc_info=error)
        QMessageBox.warning(self._dialog_parent, "Falha ao exportar", str(error))
