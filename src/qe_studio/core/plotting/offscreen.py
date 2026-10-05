"""Draw a plot off the GUI thread (spec 27-8 R2 step 3).

A figure like a 6×6 grid takes seconds to build and draw (about 1.7 s of layout and 0.8 s of Agg), so
the window never does it: a worker builds the figure in a ``Figure`` of its own, with its own
``FigureCanvasAgg`` (like ``export.render_figure``), draws it at the size the preview has, and the GUI
thread only takes the result over (``ui/widgets/plot_view.py``): the figure, for pan/zoom and the
cursor readout, and the Agg buffer, so nothing is drawn twice. Qt-free.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .. import cancel
from .mpl_lock import MPL_LOCK
from .style import figure_style, register_fonts

if TYPE_CHECKING:
    from ..calculations.params import RenderInfo
    from .session import PlotSession


@dataclass(frozen=True)
class Target:
    """The picture the preview shows: the figure size in inches and the dpi it is drawn at (the
    widget's pixels, device pixel ratio included)."""

    inches: tuple[float, float]
    dpi: float


@dataclass
class Drawn:
    """A figure drawn off-screen: ``canvas.renderer`` holds its pixels."""

    figure: Figure
    canvas: FigureCanvasAgg
    target: Target
    info: RenderInfo
    rc: dict[str, Any]  # what the figure must be drawn with again (mathtext is parsed at draw time)


def snapshot(session: PlotSession) -> Any:
    """The session's parameters as they are now: the worker draws these, not the ones the panel
    goes on editing."""
    return copy.deepcopy(session.params)


def draw_offscreen(session: PlotSession, params: Any, target: Target) -> Drawn:
    """Render ``session`` with ``params`` into a new figure and draw it at ``target``.

    Runs in a worker, holding ``MPL_LOCK`` (matplotlib's global state) all along; it stops at the next
    ``cancel.check()`` when its task is cancelled, which is how a newer render supersedes it.
    """
    style = figure_style(params.background)
    rc = style.rc(params.font_size)
    with MPL_LOCK:
        register_fonts()
        figure = Figure(figsize=target.inches, dpi=target.dpi)
        canvas = FigureCanvasAgg(figure)
        info = session.render(figure, style, params)
        cancel.check()
        with matplotlib.rc_context(rc):
            canvas.draw()
    return Drawn(figure, canvas, target, info, rc)
