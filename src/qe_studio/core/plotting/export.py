"""Saving figures, and the CSV of their data, into the simulation's ``plots/`` folder (PRD §4.4,
spec 32)."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ..calculations.base import CalculationModule, D, P
from .mpl_lock import MPL_LOCK
from .names import export_prefix, join_stem
from .style import PlotStyle, register_fonts
from .table import BOM, PlotTable, to_csv

if TYPE_CHECKING:
    from .session import PlotSession

PLOTS_DIR = "plots"


def plots_dir(folder: Path) -> Path:
    return Path(folder) / PLOTS_DIR


def target_paths(folder: Path, stem: str, formats: list[str]) -> list[Path]:
    return [plots_dir(folder) / f"{stem}.{fmt}" for fmt in formats]


def table_path(folder: Path, stem: str) -> Path:
    """The CSV of the data, next to the figures (spec 32 R4)."""
    return plots_dir(folder) / f"{stem}.csv"


def existing_targets(
    folder: Path, stem: str, formats: list[str], table: bool = False
) -> list[Path]:
    """The files of an export that exist: the figures, then the CSV when ``table``."""
    paths = target_paths(folder, stem, formats)
    if table:
        paths.append(table_path(folder, stem))
    return [path for path in paths if path.exists()]


def next_free_stem(folder: Path, stem: str, formats: list[str], table: bool = False) -> str:
    """``stem_2``, ``stem_3``… the first version whose files do not exist yet."""
    version = 2
    while existing_targets(folder, f"{stem}_{version}", formats, table):
        version += 1
    return f"{stem}_{version}"


@dataclass(frozen=True)
class ExportPlan:
    """What "Exportar" would write, decided before anything is (PRD §4.4, §7 data integrity)."""

    folder: Path
    stem: str
    formats: list[str]
    existing: list[Path]  # targets already there: ask before overwriting them
    new_stem: str | None  # the first free version (``stem_2``…), offered instead
    error: str | None = None  # nothing to export, for the user
    table: bool = False  # the module's data goes to a CSV too (spec 32 R4)


def plan_export(session: PlotSession, root: Path | None = None) -> ExportPlan:
    """Formats, target stem and the files already there.

    The stem is the path from ``root`` down to the simulation folder, then the module's own name
    (``projeto-bulk-bandas-bands``, spec 32 R3); without a ``root`` it is just the module's.

    **Runs on the GUI thread**: it stats the targets (``existing_targets``, ``next_free_stem``)
    before the export worker starts, so the overwrite question comes first. A few stats on a local
    disk: accepted (spec 27-8 R3.3); do not add reads of content here."""
    params = session.params
    formats = list(params.export_formats)
    prefix = export_prefix(session.folder, root) if root is not None else ""
    stem = join_stem(prefix, session.module.export_stem(params))
    table = session.module.has_table
    if not formats:
        return ExportPlan(
            session.folder,
            stem,
            [],
            [],
            None,
            "Selecione ao menos um formato de exportação.",
            table,
        )
    existing = existing_targets(session.folder, stem, formats, table)
    new_stem = next_free_stem(session.folder, stem, formats, table) if existing else None
    return ExportPlan(session.folder, stem, formats, existing, new_stem, None, table)


def render_figure(
    module: CalculationModule[D, P], dataset: D, params: P, style: PlotStyle, dpi: float
) -> Figure:
    """Render off-screen at the export size (independent of the preview widget)."""
    with MPL_LOCK:
        register_fonts()
        figure = Figure(figsize=params.figure_size, dpi=dpi)
        FigureCanvasAgg(figure)
        with matplotlib.rc_context(style.rc(params.font_size)):
            module.render(figure, dataset, params, style)
    return figure


def _temp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def _remove_orphans(folder: Path, stem: str) -> None:
    """Temporary files of an export that crashed: never read, removed by the next export of the
    same stem."""
    for orphan in plots_dir(folder).glob(f".{glob.escape(stem)}.*.tmp"):
        orphan.unlink(missing_ok=True)


def export_figure(
    module: CalculationModule[D, P],
    dataset: D,
    params: P,
    style: PlotStyle,
    folder: Path,
    stem: str,
    formats: list[str] | None = None,
    dpi: int | None = None,
) -> list[Path]:
    """Write ``plots/<stem>.<fmt>`` for each format; returns the written paths.

    Runs in a worker with its own figure and canvas. Each file is written to a temporary name and
    moved in place, so a target is never left half written.
    """
    chosen = formats or params.export_formats
    dpi = dpi or params.export_dpi
    out_dir = plots_dir(folder)
    with MPL_LOCK:  # the whole export: render, savefig and the moves (two exports, one .tmp)
        figure = render_figure(module, dataset, params, style, dpi)
        out_dir.mkdir(parents=True, exist_ok=True)
        _remove_orphans(folder, stem)
        written = []
        with matplotlib.rc_context(style.rc(params.font_size)):
            for fmt, path in zip(chosen, target_paths(folder, stem, chosen), strict=True):
                tmp = _temp_path(path)
                try:
                    figure.savefig(tmp, format=fmt, dpi=dpi, facecolor=figure.get_facecolor())
                    os.replace(tmp, path)
                finally:
                    tmp.unlink(missing_ok=True)
                written.append(path)
    return written


def write_table(path: Path, table: PlotTable) -> None:
    """``path`` as UTF-8 with a byte-order mark; a temporary name and a move, like the figures."""
    tmp = _temp_path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(BOM + to_csv(table), encoding="utf-8", newline="")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def export_files(
    module: CalculationModule[D, P],
    dataset: D,
    params: P,
    style: PlotStyle,
    folder: Path,
    stem: str,
    formats: list[str] | None = None,
    dpi: int | None = None,
) -> list[Path]:
    """``export_figure`` and then, for a module with data to give (``has_table``), ``plots/<stem>.csv``;
    returns the written paths, the CSV last. What the export worker runs (spec 32 R4)."""
    written = export_figure(module, dataset, params, style, folder, stem, formats, dpi)
    table = module.table(dataset, params) if module.has_table else None
    if table is not None:
        path = table_path(folder, stem)
        write_table(path, table)
        written.append(path)
    return written
