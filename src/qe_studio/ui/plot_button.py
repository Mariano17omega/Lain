"""The activity bar's "Plot": what it does with the selected folder, or with a bands folder and a
PDOS folder selected in the grid.

An open plot of the folder is brought to front. Else, a folder plotted before (``was_plotted``) is
plotted again as it was left, without exporting, so no overwrite question; a new one is plotted and
saved when ``ui.auto_generate_plot`` is on, and with it off only the panels open ("Gerar Plot"
plots). Two folders that make a bands + DOS figure (spec 22) go by the same rules, with the figure
in place of the folder's plot (plotted before: its ``bands_dos`` settings or figures in the bands
folder's ``plots/``). It only decides: ``PlotWorkflow`` plots. ``was_plotted`` and the pair read the
folders, so they run in a worker.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject

from ..core.calculations.base import SniffFn
from ..core.config import AppConfig
from ..core.detection import PairTarget
from ..core.folder_memory import FolderMemory
from ..core.plotting.saved import was_plotted
from ..core.plotting.session import target_key
from ..core.tasks import TaskGroup

if TYPE_CHECKING:
    from .plot_workflow import PlotWorkflow

log = logging.getLogger(__name__)
BUSY = "plot:pair"


def selected_pair(
    selection: list[Path], sniff: SniffFn, memory: FolderMemory | None
) -> tuple[PairTarget, bool] | None:
    """Worker: the bands + DOS figure the selection makes and whether it was plotted before; None
    when the selection makes none."""
    target = PairTarget.from_selection(selection, sniff, memory)
    return None if target is None else (target, was_plotted(target.bands, target.kind))


class PlotButton(QObject):
    def __init__(self, workflow: PlotWorkflow, config: Callable[[], AppConfig]):
        super().__init__(workflow)
        self.workflow = workflow
        self._config = config
        self._saved = TaskGroup()  # by folder: "was it plotted before?"
        self._pairs = TaskGroup()  # by folder: "do the two selected folders make a pair?"

    def click(self, folder: Path, selection: list[Path] | None = None) -> None:
        """``folder``: the selected folder (the tree's); ``selection``: the grid's items."""
        self._pairs.cancel_all()  # a newer click wins over a pending answer
        workflow = self.workflow
        if selection is None or len(selection) != 2:
            workflow.busy.end(BUSY)
            self._folder(folder)
            return
        workflow.busy.begin(BUSY, "Detectando cálculo…")
        self._pairs.submit(
            str(folder),
            selected_pair,
            list(selection),
            workflow.service.sniff_cache.sniff,
            workflow.memory,
            on_done=self._on_pair,
            on_error=self._on_pair_failed,
        )

    def cancel(self) -> None:
        """Window close: the answers still pending are not wanted any more."""
        self._saved.cancel_all()
        self._pairs.cancel_all()

    def _folder(self, folder: Path) -> None:
        workflow = self.workflow
        view = workflow.plot_of(folder)
        if view is not None:
            self._show_panels()
            workflow.workspace.set_current(view)
            return
        if not self._config().ui.auto_generate_plot:
            self._show_panels()
        self._saved.submit(str(folder), was_plotted, folder, on_done=self._on_plotted_before)

    def _show_panels(self) -> None:
        self.workflow.panel_requested.emit("workspace")
        self.workflow.panel_requested.emit("params")

    def _on_plotted_before(self, key: str, plotted: bool) -> None:
        if plotted:
            self.workflow.generate(Path(key), auto_export=False)
        elif self._config().ui.auto_generate_plot:
            self.workflow.generate(Path(key))

    def _on_pair(self, key: str, found: tuple[PairTarget, bool] | None) -> None:
        workflow = self.workflow
        workflow.busy.end(BUSY)
        if found is None:
            self._folder(Path(key))
            return
        target, plotted = found
        view = workflow.workspace.widget_for(target_key(target))
        if view is not None:
            self._show_panels()
            workflow.workspace.set_current(view)
        elif plotted:
            workflow.plot_pair(target.bands, target.dos)
        elif self._config().ui.auto_generate_plot:
            workflow.plot_pair(target.bands, target.dos, auto_export=True)
        else:
            self._show_panels()  # "Gerar Plot" plots the pair: the selection is still there

    def _on_pair_failed(self, key: str, error: Exception) -> None:
        log.warning("bands + DOS of the selection: %s", error)  # the folder is plotted instead
        self._on_pair(key, None)
