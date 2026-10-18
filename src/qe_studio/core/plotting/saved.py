"""Whether a simulation folder was plotted before: what the sidebar "Plot" shows without asking.

Two things in its ``plots/`` say so: a ``<kind>.plot`` (the settings of a plot the user edited) and
figures (what "Gerar Plot" and Ctrl+E write: a file in an export format). The 3D window's
``view3d.plot`` and its prints (``…-3d.png``), a grid's exports (``grid_*``, in the project root) and
whatever else is there (the ``.….tmp`` of an export that crashed, a CSV, a note, a folder) are not
plots of the folder, nor is a ``.plot`` that older versions left in the folder itself (not read any
more). Asked for one kind (the bands + DOS figure of two selected folders, kept in the bands folder),
only that kind's ``<kind>.plot`` and figures count. Reads the folder, so it runs in a worker.
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


def was_plotted(folder: Path, kind: str | None = None) -> bool:
    """True when ``folder/plots`` has a ``.plot`` file or an exported figure of the folder's own;
    with ``kind``, of that kind: its ``<kind>.plot`` or a figure named after it (``…-<kind>``, the
    default ``export_stem``, or ``…-<kind>_2``). Never raises."""
    named = None if kind is None else re.compile(rf"(^|-){re.escape(kind)}(_\d+)?$")
    try:
        return any(
            _is_settings(e, kind) or (_is_figure(e) and (named is None or named.search(e.stem)))
            for e in (Path(folder) / PLOTS_DIR).iterdir()
        )
    except OSError:
        return False


def _is_settings(entry: Path, kind: str | None = None) -> bool:
    if kind is not None and entry.name != kind + SUFFIX:
        return False
    return entry.name.endswith(SUFFIX) and entry.name not in NOT_A_PLOT and entry.is_file()


def _is_figure(entry: Path) -> bool:
    return (
        entry.suffix.lower() in FIGURE_SUFFIXES
        and not entry.name.startswith(".")
        and not entry.stem.startswith(GRID_PREFIX)
        and not PRINT.search(entry.stem)
        and entry.is_file()
    )
