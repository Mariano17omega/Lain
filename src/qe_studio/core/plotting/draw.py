"""Drawing helpers shared by calculation modules."""

from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from ..calculations.params import CommonParams
from .style import PlotStyle


def new_axes(figure: Figure, style: PlotStyle) -> Axes:
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    ax = figure.add_subplot()
    ax.set_facecolor(style.axes_bg)
    return ax


def stacked_axes(figure: Figure, style: PlotStyle, rows: int) -> list[Axes]:
    """``rows`` panels sharing the X axis (inner tick labels hidden), top to bottom."""
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    axes = figure.subplots(rows, 1, sharex=True, squeeze=False)[:, 0]
    for ax in axes:
        ax.set_facecolor(style.axes_bg)
    return list(axes)


def add_legend(ax: Axes, params: CommonParams, handles: list | None = None) -> None:
    """Legend as configured (position, frame). ``handles`` None = the axes' labelled artists."""
    if not params.show_legend:
        return
    kwargs = {"frameon": params.legend_frame, "fontsize": params.font_size * 0.85}
    if params.legend_loc == "outside":
        kwargs.update(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
    else:
        kwargs["loc"] = params.legend_loc
    if handles is None:
        ax.legend(**kwargs)
    elif handles:
        ax.legend(handles=handles, **kwargs)


def finish(figure: Figure, ax: Axes, params: CommonParams, handles: list | None = None) -> None:
    """Title, legend and layout. ``handles`` = legend artists (None = axes' labelled artists)."""
    if params.title.strip():
        ax.set_title(params.title.strip(), fontsize=params.font_size * 1.1, pad=8)
    add_legend(ax, params, handles)
    figure.tight_layout(pad=0.6)
