"""The adjustments panel's "Gerar Plot" (and Ctrl+G): plot what is selected and save it to plots/.

Two folders selected in the grid that make a bands + DOS figure (spec 22) plot that figure, as the
grid menu's "Bandas com DOS" does, and save it in the bands folder's ``plots/``. Any other selection
plots the selected folder and saves it (``PlotWorkflow.generate``: an open plot of it is redrawn
with its edits). Whether two folders make a pair reads them (``PairTarget.from_selection``), so it
runs in a worker. It only decides: ``PlotWorkflow`` plots.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject

from ..core.detection import PairTarget
from ..core.tasks import TaskGroup

if TYPE_CHECKING:
    from .plot_workflow import PlotWorkflow

log = logging.getLogger(__name__)
BUSY = "generate:pair"


class GeneratePlot(QObject):
    def __init__(self, workflow: PlotWorkflow):
        super().__init__(workflow)
        self.workflow = workflow
        self._pairs = TaskGroup()  # by folder: "do the two selected folders make a pair?"

    def click(self, folder: Path, selection: list[Path]) -> None:
        """``folder``: the selected folder (the tree's); ``selection``: the grid's items."""
        self._pairs.cancel_all()  # a newer click wins over a pending answer
        workflow = self.workflow
        if len(selection) != 2:
            workflow.busy.end(BUSY)
            workflow.generate(folder)
            return
        workflow.busy.begin(BUSY, "Detectando cálculo…")
        self._pairs.submit(
            str(folder),
            PairTarget.from_selection,
            list(selection),
            workflow.service.sniff_cache.sniff,
            workflow.memory,
            on_done=self._on_pair,
            on_error=self._on_failed,
        )

    def cancel(self) -> None:
        """Window close: the answer still pending is not wanted any more."""
        self._pairs.cancel_all()

    def _on_pair(self, key: str, target: PairTarget | None) -> None:
        self.workflow.busy.end(BUSY)
        if target is None:
            self.workflow.generate(Path(key))
        else:
            self.workflow.plot_pair(target.bands, target.dos, auto_export=True)

    def _on_failed(self, key: str, error: Exception) -> None:
        log.warning("bands + DOS of the selection: %s", error)  # the folder is plotted instead
        self._on_pair(key, None)
