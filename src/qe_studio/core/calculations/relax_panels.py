"""The pressure and volume panels of the vc-relax figure (spec 27-7), and the readout of the cell
quantities. ``relax.py`` stacks them under the energy and force panels of ``panels = "all"``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from ..plotting.draw import DASHED, style_axes
from ..plotting.style import PlotStyle
from ..qe.relax import QE_DEFAULT, RelaxData

if TYPE_CHECKING:
    from .relax import RelaxParams


def _line_panel(
    ax: Axes, xs: list[int], ys: list[float], color: str, params: RelaxParams, style: PlotStyle
) -> None:
    ax.plot(
        xs,
        ys,
        color=color,
        lw=params.line_width,
        marker="o",
        markersize=max(3.0, params.line_width * 3),
        zorder=3,
    )
    style_axes(ax, style)


def draw_pressure(ax: Axes, data: RelaxData, params: RelaxParams, style: PlotStyle) -> list:
    """Pressure of each step's SCF (linear: it changes sign), with the ``press_conv_thr`` band
    around the target pressure. Steps without a pressure are skipped."""
    points = [(s.index, s.pressure_kbar) for s in data.steps if s.pressure_kbar is not None]
    _line_panel(
        ax, [x for x, _ in points], [y for _, y in points], params.pressure_color, params, style
    )
    ax.set_ylabel("Pressão (kbar)")
    if not params.show_thresholds:
        return []
    target, threshold = data.target_pressure_kbar, data.pressure_threshold
    for edge in (target - threshold, target + threshold):
        ax.axhline(edge, color=params.threshold_color, lw=1.0, ls=DASHED, zorder=3)
    label = f"press_conv_thr = {threshold:.1e} kbar" + (
        f" ({QE_DEFAULT})" if data.pressure_threshold_source == QE_DEFAULT else ""
    )
    return [Line2D([], [], color=params.threshold_color, lw=1.0, ls=DASHED, label=label)]


def draw_volume(ax: Axes, data: RelaxData, params: RelaxParams, style: PlotStyle) -> list:
    """Volume of the geometry of each step (Å³); steps whose geometry the run did not print are
    skipped."""
    points = [(s.index, s.volume_ang3) for s in data.steps if s.volume_ang3 is not None]
    _line_panel(
        ax, [x for x, _ in points], [y for _, y in points], params.volume_color, params, style
    )
    ax.set_ylabel("Volume (Å³)")
    return []


def cell_readout(data: RelaxData, step: int, panel: str) -> str:
    """``passo 4 · P = 0.03 kbar`` / ``passo 4 · V = 334.00 Å³`` ("" when the step has none)."""
    if not 0 <= step < len(data.steps):
        return ""
    item = data.steps[step]
    if panel == "pressure" and item.pressure_kbar is not None:
        return f"passo {step} · P = {item.pressure_kbar:.2f} kbar"
    if panel == "volume" and item.volume_ang3 is not None:
        return f"passo {step} · V = {item.volume_ang3:.2f} Å³"
    return ""


def cell_summary(data: RelaxData) -> list[str]:
    """Parts of the status-bar summary of a vc-relax: ``V: 334.3 → 334.0 Å³``, ``P final = …``."""
    parts = []
    volumes = [s.volume_ang3 for s in data.steps if s.volume_ang3 is not None]
    if volumes:
        parts.append(f"V: {volumes[0]:.1f} → {volumes[-1]:.1f} Å³")
    if (pressure := data.steps[-1].pressure_kbar) is not None:
        parts.append(f"P final = {pressure:.2f} kbar")
    return parts
