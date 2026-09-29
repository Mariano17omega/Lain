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


def finish(figure: Figure, ax: Axes, params: CommonParams, handles: list | None = None) -> None:
    """Title, legend and layout. ``handles`` = legend artists (None = axes' labelled artists)."""
    if params.title.strip():
        ax.set_title(params.title.strip(), fontsize=params.font_size * 1.1, pad=8)
    outside = params.legend_loc == "outside"
    if params.show_legend:
        kwargs = {"frameon": params.legend_frame, "fontsize": params.font_size * 0.85}
        if outside:
            kwargs.update(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
        else:
            kwargs["loc"] = params.legend_loc
        if handles is None:
            ax.legend(**kwargs)
        elif handles:
            ax.legend(handles=handles, **kwargs)
    figure.tight_layout(pad=0.6)
