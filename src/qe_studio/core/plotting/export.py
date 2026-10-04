"""Saving figures into the simulation's ``plots/`` folder (PRD §4.4)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ..calculations.base import CalculationModule, D, P
from .mpl_lock import MPL_LOCK
from .style import PlotStyle, register_fonts

if TYPE_CHECKING:
    from .session import PlotSession

PLOTS_DIR = "plots"


def plots_dir(folder: Path) -> Path:
    return Path(folder) / PLOTS_DIR


def target_paths(folder: Path, stem: str, formats: list[str]) -> list[Path]:
    return [plots_dir(folder) / f"{stem}.{fmt}" for fmt in formats]


def existing_targets(folder: Path, stem: str, formats: list[str]) -> list[Path]:
    return [path for path in target_paths(folder, stem, formats) if path.exists()]


def next_free_stem(folder: Path, stem: str, formats: list[str]) -> str:
    """``stem_2``, ``stem_3``… the first version whose files do not exist yet."""
    version = 2
    while existing_targets(folder, f"{stem}_{version}", formats):
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


def plan_export(session: PlotSession) -> ExportPlan:
    """Formats, target stem and the files already there. Stats the targets (GUI thread, before
    the export worker starts, so the overwrite question comes first)."""
    params = session.params
    formats = list(params.export_formats)
    stem = session.module.export_stem(params)
    if not formats:
        return ExportPlan(
            session.folder, stem, [], [], None, "Selecione ao menos um formato de exportação."
        )
    existing = existing_targets(session.folder, stem, formats)
    new_stem = next_free_stem(session.folder, stem, formats) if existing else None
    return ExportPlan(session.folder, stem, formats, existing, new_stem)


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
    for orphan in plots_dir(folder).glob(f".{stem}.*.tmp"):
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
