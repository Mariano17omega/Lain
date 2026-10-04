"""Figure styles: dark or light text, axes and guides for the plot's background colour.

Figures do not follow the app theme: the style comes from ``params.background`` (default white),
so preview and exported files look the same. Styles are applied with ``matplotlib.rc_context``
around rendering, never by mutating the global ``rcParams``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.resources import as_file, files
from typing import Any

from matplotlib import font_manager

# Moved to core/colors.py (spec 19); re-exported here for the old import path.
from ..colors import contrast_ratio as contrast_ratio
from ..colors import relative_luminance as relative_luminance

UI_FONT = "Inter"
MONO_FONT = "JetBrains Mono"

_fonts_registered = False


def register_fonts() -> None:
    """Make the vendored Inter / JetBrains Mono available to matplotlib (idempotent)."""
    global _fonts_registered
    if _fonts_registered:
        return
    for resource in files("qe_studio.ui.resources").joinpath("fonts").iterdir():
        if resource.name.endswith(".ttf"):
            with as_file(resource) as path:
                font_manager.fontManager.addfont(str(path))
    _fonts_registered = True


@dataclass(frozen=True)
class PlotStyle:
    name: str
    figure_bg: str
    axes_bg: str
    text: str
    muted: str
    spine: str
    grid: str
    guide: str  # high-symmetry lines, zero lines
    total_dos: str
    palette: tuple[str, ...]

    def rc(self, font_size: float = 11.0) -> dict[Any, Any]:  # matplotlib rcParams keys
        return {
            "font.family": "sans-serif",
            "font.sans-serif": [UI_FONT, "DejaVu Sans"],
            "font.size": font_size,
            "mathtext.fontset": "custom",
            "mathtext.rm": UI_FONT,
            "mathtext.it": UI_FONT,
            "mathtext.bf": f"{UI_FONT}:bold",
            "mathtext.sf": UI_FONT,
            "mathtext.tt": MONO_FONT,
            "mathtext.cal": UI_FONT,
            "mathtext.default": "regular",
            "figure.facecolor": self.figure_bg,
            "savefig.facecolor": self.figure_bg,
            "axes.facecolor": self.axes_bg,
            "axes.edgecolor": self.spine,
            "axes.labelcolor": self.text,
            "axes.titlecolor": self.text,
            "axes.linewidth": 0.9,
            "xtick.color": self.spine,
            "ytick.color": self.spine,
            "xtick.labelcolor": self.text,
            "ytick.labelcolor": self.text,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "legend.labelcolor": self.text,
            "legend.facecolor": self.axes_bg,
            "legend.edgecolor": self.grid,
            "grid.color": self.grid,
            "text.color": self.text,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }


DARK = PlotStyle(
    name="dark",
    figure_bg="#0f1216",
    axes_bg="#0f1216",
    text="#e1e2eb",
    muted="#94a3b8",
    spine="#859399",
    grid="#323846",
    guide="#4b5563",
    total_dos="#e1e2eb",
    palette=("#00d2ff", "#2563eb", "#10b981", "#f59e0b", "#a855f7", "#ec4899", "#f43f5e"),
)

LIGHT = PlotStyle(
    name="light",
    figure_bg="#ffffff",
    axes_bg="#ffffff",
    text="#0f172a",
    muted="#64748b",
    spine="#334155",
    grid="#e2e8f0",
    guide="#94a3b8",
    total_dos="#0f172a",
    palette=("#2563eb", "#0284c7", "#059669", "#d97706", "#7c3aed", "#db2777", "#dc2626"),
)


def figure_style(background: str) -> PlotStyle:
    """Style for a figure background: the base (light or dark) whose text reads best on it."""
    base = max((LIGHT, DARK), key=lambda style: contrast_ratio(style.text, background))
    return replace(base, figure_bg=background, axes_bg=background)
