"""Inputs derived from a finished run (spec 24 R5): "Gerar SCF convergido" of the context menu.

The SCF is built and written in a worker (``core/qe/scf_from_relax.generate_scf_file``); this
controller only shows the footer spinner, refreshes the panels and says how it went: a toast with
the name actually written (it never overwrites), or a warning with the reason and nothing written.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from ..core.qe.scf_from_relax import GeneratedScf, ScfError, generate_scf_file
from ..core.tasks import TaskGroup
from .busy import BusyTracker
from .services import DetectionService
from .widgets.toast import Toast

log = logging.getLogger(__name__)

TITLE = "Gerar SCF convergido"
KEY_PREFIX = "scf:"  # of the busy label and of the task: one generation per output


class DeriveController(QObject):
    generated = pyqtSignal(object)  # Path written (tests and scripts wait on it)
    failed = pyqtSignal(str)  # the reason shown

    def __init__(
        self,
        service: DetectionService,
        busy: BusyTracker,
        toast: Toast,
        refresh: Callable[[Path], None],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.service, self.busy, self.toast = service, busy, toast
        self.refresh, self.dialog_parent = refresh, dialog_parent
        self._tasks = TaskGroup()  # by output: one generation at a time for each

    @classmethod
    def for_window(cls, window) -> DeriveController:
        """The controller of a ``MainWindow``: its context menu, footer spinner and toast."""

        def refresh(folder: Path) -> None:
            window.service.invalidate(folder)
            window.explorer.refresh()
            window.files.refresh()

        busy = window.plot_workflow.busy
        controller = cls(window.service, busy, window.toast, refresh, window, window)
        window.item_actions.scf_from_relax_requested.connect(controller.generate_scf)
        return controller

    def active_under(self, path: Path) -> Path | None:
        """The output whose SCF is being written and lies inside ``path`` (a rename of it or of a
        folder above it would move what the worker writes into), None when there is none."""
        outputs = (Path(str(key).removeprefix(KEY_PREFIX)) for key in self._tasks.active_keys())
        return next((output for output in outputs if output.is_relative_to(path)), None)

    def generate_scf(self, output: Path) -> None:
        key = f"{KEY_PREFIX}{output}"
        if self._tasks.active(key) is not None:  # a second click while the first one writes
            return
        self.busy.begin(key, "Gerando SCF convergido…")
        results = self.service.peek_results(output.parent)  # the relax_in role, if detected
        self._tasks.submit(
            key, generate_scf_file, output, results, on_done=self._on_done, on_error=self._on_error
        )

    def _on_done(self, key: str, generated: GeneratedScf) -> None:
        self.busy.end(key)
        path = generated.path
        self.refresh(path.parent)
        details = "\n".join([str(path), *generated.warnings])
        self.toast.show_message(f"{path.name} criado", "success", details)
        self.generated.emit(path)

    def _on_error(self, key: str, exc: BaseException) -> None:
        self.busy.end(key)
        if isinstance(exc, ScfError):
            reason = str(exc)
        else:
            log.error("generating the converged SCF failed", exc_info=exc)
            reason = f"Erro inesperado: {exc}"
        QMessageBox.warning(self.dialog_parent, TITLE, reason)
        self.failed.emit(reason)
