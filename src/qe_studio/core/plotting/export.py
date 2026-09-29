"""Saving figures into the simulation's ``plots/`` folder (PRD §4.4)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .style import PlotStyle, register_fonts

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


def render_figure(module: Any, dataset: Any, params: Any, style: PlotStyle, dpi: float) -> Figure:
    """Render off-screen at the export size (independent of the preview widget)."""
    register_fonts()
    figure = Figure(figsize=params.figure_size, dpi=dpi)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(style.rc(params.font_size)):
        module.render(figure, dataset, params, style)
    return figure


def export_figure(
    module: Any,
    dataset: Any,
    params: Any,
    style: PlotStyle,
    folder: Path,
    stem: str,
    formats: list[str] | None = None,
    dpi: int | None = None,
) -> list[Path]:
    """Write ``plots/<stem>.<fmt>`` for each format; returns the written paths."""
    formats = formats or params.export_formats
    dpi = dpi or params.export_dpi
    figure = render_figure(module, dataset, params, style, dpi)
    out_dir = plots_dir(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with matplotlib.rc_context(style.rc(params.font_size)):
        for fmt, path in zip(formats, target_paths(folder, stem, formats), strict=True):
            tmp = path.with_name(f".{path.name}.tmp")
            figure.savefig(tmp, format=fmt, dpi=dpi, facecolor=figure.get_facecolor())
            os.replace(tmp, path)
            written.append(path)
    return written
