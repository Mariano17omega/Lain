"""The "Calcular adsorção…" item of the context menu (spec 78 R3.2): a new window per request.

The outputs are read in a worker (``core/analysis/adsorption_energy.read_rows``: the GUI never reads
them), under the footer spinner "Lendo energias…"; then an ``AdsorptionEnergyDialog`` opens on the
rows. Its "Salvar resultado" writes the report in a worker too, beside the outputs and never over a
file (``save_report``), refreshes the panels and says the name written in a toast. The open windows
are kept here and closed with the main window (``shutdown.close_dialogs``).
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from ...core.analysis.adsorption_energy import EnergyRow, calculate, read_rows, save_report
from ...core.tasks import TaskGroup
from ...i18n import _
from ..dialogs.adsorption_energy import TITLE, AdsorptionEnergyDialog
from ..shell.busy import BusyTracker
from ..theme.manager import ThemeManager
from ..widgets.toast import Toast

log = logging.getLogger(__name__)

KEY_PREFIX = "adsorption:"  # of the busy label and the task: ``adsorption:<n>``
SAVE_PREFIX = "adsorption-save:"
BUSY_LABEL = _("Lendo energias…")


class AdsorptionEnergyController(QObject):
    opened = pyqtSignal(object)  # AdsorptionEnergyDialog (tests and scripts wait on it)
    saved = pyqtSignal(object)  # Path of the report written
    failed = pyqtSignal(str)  # the message shown

    def __init__(
        self,
        theme: ThemeManager,
        busy: BusyTracker,
        toast: Toast,
        refresh: Callable[[Path], None],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.theme, self.busy, self.toast = theme, busy, toast
        self.refresh, self.dialog_parent = refresh, dialog_parent
        self.dialogs: list[AdsorptionEnergyDialog] = []
        self._tasks = TaskGroup()
        self._reading: set[str] = set()
        self._count = itertools.count(1)

    @classmethod
    def for_window(cls, window) -> AdsorptionEnergyController:
        """The controller of a ``MainWindow``: its context menu, footer spinner and toast."""

        def refresh(folder: Path) -> None:
            window.service.invalidate(folder)
            window.explorer.refresh()
            window.files.refresh()

        busy = window.plot_workflow.busy
        controller = cls(window.theme, busy, window.toast, refresh, window, window)
        window.item_actions.adsorption_requested.connect(controller.open)
        return controller

    def open(self, paths: list[Path]) -> None:
        """Read the energies of ``paths`` and open a new window on them."""
        key = f"{KEY_PREFIX}{next(self._count)}"
        self._reading.add(key)
        self.busy.begin(key, BUSY_LABEL)
        self._tasks.submit(
            key, read_rows, [Path(p) for p in paths], on_done=self._on_read, on_error=self._on_error
        )

    def _on_read(self, key: str, rows: list[EnergyRow]) -> None:
        self._end(key)
        dialog = AdsorptionEnergyDialog(rows, self.theme, self.dialog_parent)
        dialog.save_requested.connect(self.save)
        dialog.closed.connect(self._on_closed)
        self.dialogs.append(dialog)
        dialog.show()
        self.opened.emit(dialog)

    def _on_error(self, key: str, exc: BaseException) -> None:
        self._end(key)
        log.error("reading the energies failed", exc_info=exc)
        message = f"{TITLE}: {exc}"
        self.toast.show_message(message, "warning")
        self.failed.emit(message)

    def _end(self, key: str) -> None:
        self._reading.discard(key)
        self.busy.end(key)

    def _on_closed(self, dialog: AdsorptionEnergyDialog) -> None:
        if dialog in self.dialogs:
            self.dialogs.remove(dialog)

    def save(self, dialog: AdsorptionEnergyDialog, equation: str) -> None:
        """The report of ``dialog`` beside its outputs (worker); nothing when the equation fails."""
        rows = dialog.rows
        outcome = calculate(equation, rows)
        if outcome.value_ry is None or not rows:
            return
        folder = rows[0].path.parent
        key = f"{SAVE_PREFIX}{next(self._count)}"
        self._tasks.submit(
            key,
            save_report,
            folder,
            rows,
            equation,
            outcome,
            on_done=self._on_saved,
            on_error=self._on_save_error,
        )

    def _on_saved(self, _key: str, path: Path) -> None:
        log.info("file: generated %s", path)
        self.refresh(path.parent)
        self.toast.show_message(_("{name} criado").format(name=path.name), "success", str(path))
        self.saved.emit(path)

    def _on_save_error(self, _key: str, exc: BaseException) -> None:
        log.error("writing the adsorption report failed", exc_info=exc)
        reason = _("Erro inesperado: {error}").format(error=exc)
        QMessageBox.warning(self.dialog_parent, TITLE, reason)
        self.failed.emit(reason)

    def close_dialog(self) -> bool:
        """The main window is closing: every window of this item closes."""
        for dialog in list(self.dialogs):
            dialog.close()
        return True

    def cancel(self) -> None:
        """Window close: the readings not finished are dropped."""
        for key in list(self._reading):
            self.busy.end(key)
        self._reading.clear()
        self._tasks.cancel_all()
