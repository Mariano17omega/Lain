"""The grid's dataset: its definition and, for each cell, the session of its plot (or why there is
none). Put together by the window from open plots and loads, never by ``GridModule.load``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...plotting.grid import GridCell, GridSpec
from ..base import CalculationModule, DetectionResult

if TYPE_CHECKING:
    from ...plotting.session import PlotSession


@dataclass
class GridCellData:
    cell: GridCell
    session: PlotSession | None = None  # a copy: the grid never edits an open plot
    error: str = ""  # why there is no session ("Pasta não encontrada: …")


@dataclass
class GridDataset:
    folder: Path  # the project root: the grid belongs to no simulation folder
    spec: GridSpec
    cells: list[GridCellData]
    warnings: list[str] = field(default_factory=list)

    def at(self, row: int, col: int) -> GridCellData | None:
        return next((c for c in self.cells if (c.cell.row, c.cell.col) == (row, col)), None)


def grid_result(
    module: CalculationModule, spec: GridSpec, cells: Sequence[GridCellData], root: Path
) -> DetectionResult:
    """The result a grid plots: the root's, named after the grid (its tab is ``plot:grid:<name>``)
    and with the results of its plots as parts (renaming any of their folders closes it)."""
    parts = tuple(c.session.result for c in cells if c.session is not None)
    return DetectionResult(module, root, parts=parts, plot_name=spec.name)
