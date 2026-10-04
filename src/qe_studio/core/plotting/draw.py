"""Drawing helpers shared by calculation modules."""

from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.figure import Figure, FigureBase

from ..calculations.params import CommonParams
from .style import PlotStyle

DASHED = (0, (5, 3))  # threshold lines
MAX_TICKS = 20  # integer X ticks are thinned above this many


def new_axes(figure: FigureBase, style: PlotStyle) -> Axes:
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    ax = figure.add_subplot()
    ax.set_facecolor(style.axes_bg)
    return ax


def stacked_axes(figure: FigureBase, style: PlotStyle, rows: int) -> list[Axes]:
    """``rows`` panels sharing the X axis (inner tick labels hidden), top to bottom."""
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    axes = figure.subplots(rows, 1, sharex=True, squeeze=False)[:, 0]
    for ax in axes:
        ax.set_facecolor(style.axes_bg)
    return list(axes)


def side_axes(figure: FigureBase, style: PlotStyle, columns: int) -> list[Axes]:
    """``columns`` panels side by side sharing both axes (inner tick labels hidden)."""
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    axes = figure.subplots(1, columns, sharex=True, sharey=True, squeeze=False)[0]
    for ax in axes:
        ax.set_facecolor(style.axes_bg)
    return list(axes)


def bands_dos_axes(figure: FigureBase, style: PlotStyle, ratios: tuple[float, float]) -> list[Axes]:
    """Two panels side by side sharing the Y axis (the energy of bands + DOS), widths in
    ``ratios``, no space between them (``finish_joined`` keeps it so)."""
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    axes = figure.subplots(
        1, 2, sharey=True, gridspec_kw={"width_ratios": list(ratios), "wspace": 0}
    )
    for ax in axes:
        ax.set_facecolor(style.axes_bg)
    return list(axes)


def tight(figure: FigureBase) -> None:
    """``tight_layout`` of a whole figure. A ``SubFigure`` (a cell of a grid, spec 23) has none: the
    grid fits each cell itself (``cell_layout.fit_cell``)."""
    if isinstance(figure, Figure):
        figure.tight_layout(pad=0.6)


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


def finish(figure: FigureBase, ax: Axes, params: CommonParams, handles: list | None = None) -> None:
    """Title, legend and layout. ``handles`` = legend artists (None = axes' labelled artists)."""
    if params.title.strip():
        ax.set_title(params.title.strip(), fontsize=params.font_size * 1.1, pad=8)
    add_legend(ax, params, handles)
    tight(figure)


def finish_side(
    figure: FigureBase, axes: list[Axes], params: CommonParams, handles: list | None = None
) -> None:
    """Like ``finish`` for panels side by side: the title spans the figure, the legend sits in the
    first panel."""
    if params.title.strip():
        figure.suptitle(params.title.strip(), fontsize=params.font_size * 1.1)
    add_legend(axes[0], params, handles)
    tight(figure)


def finish_joined(
    figure: FigureBase, legend_ax: Axes, params: CommonParams, handles: list | None = None
) -> None:
    """Like ``finish_side`` for panels with no space between them (``bands_dos_axes``): the
    legend sits in ``legend_ax`` and the layout keeps the panels together."""
    if params.title.strip():
        figure.suptitle(params.title.strip(), fontsize=params.font_size * 1.1)
    add_legend(legend_ax, params, handles)
    tight(figure)
    figure.subplots_adjust(wspace=0)


def positive_for_log(values: list[float]) -> list[float]:
    """Non-positive values (e.g. |ΔE| = 0 between identical energies) as a floor below the data,
    so a log axis can show them (the reference's ``_positive_for_log``)."""
    positive = [v for v in values if v > 0]
    floor = min(positive) / 10 if positive else 1e-12
    return [v if v > 0 else floor for v in values]


def style_axes(ax: Axes, style: PlotStyle) -> None:
    ax.grid(axis="y", color=style.grid, lw=0.6, ls=":", zorder=0)
    ax.tick_params(axis="y", which="both", right=True)


def empty_panel(ax: Axes, message: str, style: PlotStyle) -> None:
    """Placeholder text in a panel without data (no axes drawn)."""
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        message,
        transform=ax.transAxes,
        ha="center",
        va="center",
        wrap=True,
        color=style.muted,
    )
