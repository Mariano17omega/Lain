"""``core/plotting/offscreen``: a figure drawn in a worker is the figure the GUI thread would draw
(spec 27-8 R2 step 3)."""

import matplotlib
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from plot_grid_helpers import BANDS, RELAX, grid_of, session_of
from qe_studio.core import cancel
from qe_studio.core.plotting.mpl_lock import MPL_LOCK
from qe_studio.core.plotting.offscreen import Target, draw_offscreen, snapshot

DPI = 72


def pixels(canvas) -> np.ndarray:
    return np.asarray(canvas.buffer_rgba()).copy()


def on_the_spot(session, dpi: float = DPI) -> Figure:
    """What ``PlotView`` draws on the GUI thread: the render, then the draw with the style's rc."""
    figure = Figure(figsize=session.params.figure_size, dpi=dpi)
    FigureCanvasAgg(figure)
    session.render(figure, session.style)
    with matplotlib.rc_context(session.style.rc(session.params.font_size)):
        figure.canvas.draw()
    return figure


@pytest.fixture
def grid(tmp_path):
    return grid_of([(0, 0, BANDS, "a"), (0, 1, RELAX, "")], tmp_path)


def test_a_grid_drawn_off_screen_has_the_pixels_of_the_one_drawn_on_the_spot(grid):
    target = Target(grid.params.figure_size, DPI)
    drawn = draw_offscreen(grid, snapshot(grid), target)
    same = on_the_spot(grid)
    assert drawn.canvas.figure is drawn.figure and drawn.target == target
    assert np.array_equal(pixels(drawn.canvas), pixels(same.canvas))
    assert drawn.info == grid.info and "2 gráficos" in drawn.info.summary
    assert len(drawn.figure.axes) == len(same.axes) == 3


def test_a_plot_is_drawn_off_screen_the_same_way(tmp_path):
    session = session_of(BANDS, tmp_path)
    drawn = draw_offscreen(session, snapshot(session), Target(session.params.figure_size, DPI))
    assert np.array_equal(pixels(drawn.canvas), pixels(on_the_spot(session).canvas))


def test_the_size_and_the_dpi_are_the_targets(grid):
    drawn = draw_offscreen(grid, snapshot(grid), Target((8.0, 4.0), 50))
    assert tuple(drawn.figure.get_size_inches()) == (8.0, 4.0) and drawn.figure.dpi == 50
    assert (drawn.canvas.renderer.width, drawn.canvas.renderer.height) == (400, 200)


def test_the_snapshot_keeps_the_parameters_it_was_taken_with(grid):
    frozen = snapshot(grid)
    assert frozen == grid.params and frozen is not grid.params
    grid.params.show_titles = not grid.params.show_titles
    assert frozen != grid.params
    # What is drawn follows the snapshot, not the session's parameters of the moment.
    target = Target(frozen.figure_size, DPI)
    drawn = draw_offscreen(grid, frozen, target)
    assert [t.get_text() for sub in drawn.figure.subfigs for t in sub.texts] == ["a"]


def test_a_cancelled_task_stops_drawing_and_releases_matplotlib(grid):
    class Token:
        cancelled = True

    with cancel.bind(Token()), pytest.raises(cancel.Cancelled):
        draw_offscreen(grid, snapshot(grid), Target(grid.params.figure_size, DPI))
    assert MPL_LOCK.acquire(blocking=False)
    MPL_LOCK.release()
