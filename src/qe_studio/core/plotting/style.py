"""Figure styles for the dark and light themes.

Styles are applied with ``matplotlib.rc_context`` around rendering (never by mutating the
global ``rcParams``), so the preview canvas and off-screen exports can use different themes.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file, files

from matplotlib import font_manager

UI_FONT = "Inter"
MONO_FONT = "JetBrains Mono"

_fonts_registered = False


def register_fonts() -> None:
    """Make the vendored Inter / JetBrains Mono available to matplotlib (idempotent)."""
    global _fonts_registered
    if _fonts_registered:
        return
    for resource in files("qe_studio.resources").joinpath("fonts").iterdir():
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

    def rc(self, font_size: float = 11.0) -> dict[str, object]:
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

STYLES = {"dark": DARK, "light": LIGHT}


def style_for(theme: str) -> PlotStyle:
    return STYLES.get(theme, DARK)
