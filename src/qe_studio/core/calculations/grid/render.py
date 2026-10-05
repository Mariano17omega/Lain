"""The grid figure: one ``SubFigure`` per position, each cell drawn by its own plot's module."""

from __future__ import annotations

import copy

import matplotlib
from matplotlib.figure import Figure, FigureBase, SubFigure

from ... import cancel
from ...plotting.cell_layout import fit_cell
from ...plotting.style import PlotStyle
from ..params import RenderInfo
from .data import GridCellData, GridDataset
from .params import GridParams

UNAVAILABLE = "Plot indisponível: {}"
PAD = 0.6  # in font sizes, like ``draw.finish``'s ``tight_layout``


def cell_figures(figure: FigureBase, rows: int, cols: int) -> list[SubFigure]:
    """A ``SubFigure`` for every position, added in row-major order: ``position_of`` relies on it."""
    grid = figure.add_gridspec(rows, cols, left=0, right=1, bottom=0, top=1, wspace=0, hspace=0)
    return [figure.add_subfigure(grid[row, col]) for row in range(rows) for col in range(cols)]


def position_of(figure: Figure, cell: FigureBase, cols: int) -> tuple[int, int] | None:
    """The (row, col) of a cell ``SubFigure`` of a grid figure drawn by ``render_grid``."""
    for index, sub in enumerate(figure.subfigs):
        if sub is cell:
            return divmod(index, cols)
    return None


def render_grid(
    figure: FigureBase, dataset: GridDataset, params: GridParams, style: PlotStyle
) -> RenderInfo:
    spec = dataset.spec
    figure.clear()
    figure.set_facecolor(style.figure_bg)
    cells = cell_figures(figure, spec.rows, spec.cols)
    for cell in cells:  # empty positions show the grid's background, without axes
        cell.set_facecolor(style.figure_bg)
    drawn, notes = 0, []
    for data in dataset.cells:
        cell = cells[data.cell.row * spec.cols + data.cell.col]
        if data.session is None:
            message = UNAVAILABLE.format(data.error)
            cell.text(0.5, 0.5, message, ha="center", va="center", wrap=True, color=style.muted)
            notes.append(f"Célula ({data.cell.row + 1}, {data.cell.col + 1}): {data.error}")
        else:
            _draw_cell(cell, data, params)
            drawn += 1
    plots = "1 gráfico" if drawn == 1 else f"{drawn} gráficos"
    summary = f"Grid {spec.rows}×{spec.cols} · {plots}"
    return RenderInfo((0.0, 1.0), (0.0, 1.0), summary, tuple(notes))


def _draw_cell(cell: SubFigure, data: GridCellData, params: GridParams) -> None:
    """The plot as its session draws it; a title of the cell takes the place of the plot's own."""
    session = data.session
    assert session is not None
    cancel.check()  # a grid takes seconds: a superseded render stops between cells
    title = data.cell.title.strip() if params.show_titles else ""
    own = None
    if title:
        own = copy.copy(session.params)  # shallow: only the title differs
        own.title = ""
    style = session.style
    session.render(cell, style, own)
    font = (own or session.params).font_size
    with matplotlib.rc_context(style.rc(font)):  # mathtext is measured with the cell's fonts
        if title:
            cell.suptitle(title, fontsize=params.font_size * 1.1, color=style.text)
        fit_cell(cell, PAD * font)
