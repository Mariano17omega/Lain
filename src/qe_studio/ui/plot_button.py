"""The activity bar's "Plot": what it does with the selected folder.

An open plot of the folder is brought to front. Else, a folder plotted before (``was_plotted``) is
plotted again as it was left, without exporting, so no overwrite question; a new one is plotted and
saved when ``ui.auto_generate_plot`` is on, and with it off only the panels open ("Gerar Plot"
plots). It only decides: ``PlotWorkflow`` plots. ``was_plotted`` reads the folder, so it runs in a
worker.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject

from ..core.config import AppConfig
from ..core.plotting.saved import was_plotted
from ..core.tasks import TaskGroup

if TYPE_CHECKING:
    from .plot_workflow import PlotWorkflow


class PlotButton(QObject):
    def __init__(self, workflow: PlotWorkflow, config: Callable[[], AppConfig]):
        super().__init__(workflow)
        self.workflow = workflow
        self._config = config
        self._saved = TaskGroup()  # by folder: "was it plotted before?"

    def click(self, folder: Path) -> None:
        workflow = self.workflow
        view = workflow.plot_of(folder)
        if view is not None:
            self._show_panels()
            workflow.workspace.set_current(view)
            return
        if not self._config().ui.auto_generate_plot:
            self._show_panels()
        self._saved.submit(str(folder), was_plotted, folder, on_done=self._on_plotted_before)

    def cancel(self) -> None:
        """Window close: the answers still pending are not wanted any more."""
        self._saved.cancel_all()

    def _show_panels(self) -> None:
        self.workflow.panel_requested.emit("workspace")
        self.workflow.panel_requested.emit("params")

    def _on_plotted_before(self, key: str, plotted: bool) -> None:
        if plotted:
            self.workflow.generate(Path(key), auto_export=False)
        elif self._config().ui.auto_generate_plot:
            self.workflow.generate(Path(key))
