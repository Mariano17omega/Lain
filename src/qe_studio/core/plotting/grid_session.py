"""The session of a grid figure (spec 23), from the sessions of its cells."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..calculations import module_for
from ..calculations.base import Stores
from ..calculations.grid import GridCellData, GridDataset, grid_result
from ..config import AppConfig
from ..folder_memory import FolderMemory
from .grid import GridSpec
from .session import PlotSession, build_session

GRID_KIND = "grid"


def build_grid_session(
    spec: GridSpec,
    cells: Iterable[GridCellData],
    root: Path,
    config: AppConfig,
    memory: FolderMemory,
    stores: Stores | None = None,
) -> PlotSession:
    """The grid's session: its cells in reading order, its settings from the defaults and what
    ``stores`` keep for it (no ``.plot``: a grid belongs to no folder)."""
    ordered = sorted(cells, key=lambda c: (c.cell.row, c.cell.col))
    dataset = GridDataset(root, spec, ordered)
    result = grid_result(module_for(GRID_KIND), spec, ordered, root)
    session, _warnings = build_session(result, dataset, config, (None, []), memory, None, stores)
    return session
