"""The layout of one cell of a grid of plots (spec 23): ``tight_layout`` for a ``SubFigure``.

A ``SubFigure`` has no ``tight_layout``, and matplotlib's constrained layout pads every axes on both
sides, which opens a gap between the joined panels of bands + DOS. So the grid's figure has no layout
engine and each cell moves the outer edges of its own axes grid until their labels, ticks, legends
and the cell's titles fit inside it. The space between the panels of a cell stays as its module set
it (none for bands + DOS).
"""

from __future__ import annotations

from matplotlib.figure import SubFigure
from matplotlib.transforms import Bbox

PASSES = 2  # tick labels change with the axes size: measure again once
MIN_FRACTION = 0.05  # the axes keep at least this much of the cell in each direction


def fit_cell(cell: SubFigure, pad_points: float) -> None:
    """Fit the axes of ``cell`` inside it, ``pad_points`` from its edges. Text of the cell itself
    (its title, or the plot's ``suptitle``) is anchored to the cell: the axes go below it. A cell
    without axes, or one whose decorations would not leave room for them, is left as it is."""
    axes = [ax for ax in cell.axes if ax.get_visible()]
    if not axes:
        return
    pad = pad_points / 72 * cell.get_figure(root=True).dpi
    for _ in range(PASSES):
        box = cell.bbox
        if box.width <= 0 or box.height <= 0:
            return
        inner = Bbox.union([ax.get_window_extent() for ax in axes])
        tight = Bbox.union([ax.get_tightbbox(for_layout_only=True) or inner for ax in axes])
        middle = box.y0 + box.height / 2
        extents = [text.get_window_extent() for text in cell.texts if text.get_visible()]
        titles = [t for t in extents if t.y0 > middle]  # suptitles, in the upper half
        below_titles = max([0.0] + [box.y1 - t.y0 for t in titles])
        top = below_titles + tight.y1 - inner.y1 + pad
        left = (inner.x0 - tight.x0 + pad) / box.width
        right = 1 - (tight.x1 - inner.x1 + pad) / box.width
        bottom = (inner.y0 - tight.y0 + pad) / box.height
        top = 1 - top / box.height
        if right - left < MIN_FRACTION or top - bottom < MIN_FRACTION:
            return
        cell.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
