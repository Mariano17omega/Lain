"""Plotting in the cluster mode (spec 66 R4): the folder (or the two folders of a bands + DOS figure) is
copied into its mirror's ``tmp_remote/``, one sync at a time, and the copy is plotted as a local folder
is: the sidebar's "Plot" (``PlotButton``) or "Gerar" and Ctrl+G (``GeneratePlot``), which save into
``tmp_remote/plots_remote/``. It only chains: ``SyncCoordinator.start_scratch`` copies, ``PlotWorkflow``
plots; nothing here reads the disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject

if TYPE_CHECKING:
    from .plot_workflow import PlotWorkflow
    from .sync_coordinator import SyncCoordinator


class RemotePlot(QObject):
    def __init__(
        self, sync: SyncCoordinator, workflow: PlotWorkflow, parent: QObject | None = None
    ):
        super().__init__(parent)
        self.sync, self.workflow = sync, workflow
        self._mirrors: list[Path] = []
        self._copies: list[Path] = []
        self._generate = False

    def plot(self, mirrors: list[Path], generate: bool) -> None:
        """Copy the cluster side of each of ``mirrors`` (one or two), then plot: "Gerar" with
        ``generate``, else "Plot". A copy that fails, or is cancelled, plots nothing."""
        self._mirrors, self._copies, self._generate = list(mirrors), [], generate
        self._next()

    def _next(self) -> None:
        self.sync.start_scratch(self._mirrors[len(self._copies)], self._copied)

    def _copied(self, copy: Path) -> None:
        self._copies.append(copy)
        if len(self._copies) < len(self._mirrors):
            self._next()
            return
        copies = self._copies
        selection = copies if len(copies) == 2 else []  # two folders: the bands + DOS figure
        target = self.workflow.generator if self._generate else self.workflow.button
        target.click(copies[0], selection)
