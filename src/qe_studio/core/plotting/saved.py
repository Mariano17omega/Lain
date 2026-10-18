"""Whether a simulation folder was plotted before: what the sidebar "Plot" shows without asking.

Two things say so: a ``<kind>.plot`` (the settings of a plot the user edited) and figures in
``plots/`` (what "Gerar Plot" and Ctrl+E write: a file in an export format). The 3D window's
``view3d.plot`` and its prints (``…-3d.png``), a grid's exports (``grid_*``, in the project root) and
whatever else is in ``plots/`` (the ``.….tmp`` of an export that crashed, a CSV, a note, a folder) are
not plots of the folder. Reads the folder, so it runs in a worker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from ..config import ExportFormat
from .names import PLOTS_DIR
from .plot_file import SUFFIX

NOT_A_PLOT = {"view3d" + SUFFIX}
FIGURE_SUFFIXES = {f".{fmt}" for fmt in get_args(ExportFormat)}
GRID_PREFIX = "grid_"
PRINT = re.compile(r"-3d(_\d+)?$")  # image_file.print_stem: ``<prefix>-3d``, ``…_2`` if taken


def was_plotted(folder: Path) -> bool:
    """True when ``folder`` has a ``.plot`` file or an exported figure of its own. Never raises."""
    try:
        for entry in Path(folder).iterdir():
            if entry.name.endswith(SUFFIX) and entry.name not in NOT_A_PLOT and entry.is_file():
                return True
        return any(_is_figure(e) for e in (Path(folder) / PLOTS_DIR).iterdir())
    except OSError:
        return False


def _is_figure(entry: Path) -> bool:
    return (
        entry.suffix.lower() in FIGURE_SUFFIXES
        and not entry.name.startswith(".")
        and not entry.stem.startswith(GRID_PREFIX)
        and not PRINT.search(entry.stem)
        and entry.is_file()
    )
