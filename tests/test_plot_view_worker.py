"""A figure that ``render_in_worker`` (a grid) is drawn off the GUI thread and shown when it is done
(spec 27-8 R2 step 3): the tab keeps working, the last picture stays, a newer render supersedes."""

import threading

import pytest
from PyQt6.QtGui import QImage

from plot_grid_helpers import BANDS, RELAX, grid_of, settled
from qe_studio.core.plotting.mpl_lock import MPL_LOCK
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets import plot_view
from qe_studio.ui.widgets.plot_view import PlotView


@pytest.fixture
def grid(tmp_path):
    return grid_of([(0, 0, BANDS, ""), (0, 1, RELAX, "")], tmp_path)


def shown(qtbot, session, width=900, height=500) -> PlotView:
    view = PlotView(ThemeManager("dark"), session)
    qtbot.addWidget(view)
    view.resize(width, height)
    view.show()
    settled(qtbot, view)
    return view


def grabbed(view: PlotView) -> QImage:
    return view.canvas.grab().toImage()


def inked(image: QImage) -> int:
    """Samples of the picture that are not its corner's color: something was painted."""
    corner = image.pixelColor(1, 1)
    return sum(
        image.pixelColor(x, y) != corner
        for x in range(0, image.width(), 5)
        for y in range(0, image.height(), 5)
    )


def test_a_grid_is_drawn_by_a_worker_and_shown(qtbot, grid):
    view = PlotView(ThemeManager("dark"), grid)
    qtbot.addWidget(view)
    assert view.canvas.worker_draws and view.drawing and view.render_pending
    assert view.figure.axes == []  # nothing on the GUI thread: the figure comes with the worker's
    emitted = []
    view.rendered.connect(emitted.append)
    view.resize(900, 500)
    view.show()
    settled(qtbot, view)
    assert not view.drawing and len(emitted) >= 1
    assert view.canvas.figure is view.figure and len(view.figure.axes) == 3
    assert view.canvas.renderer.width == view.canvas.width()  # drawn at the size on show
    assert inked(grabbed(view)) > 100  # and painted as it is


def test_the_picture_on_show_stays_while_the_next_one_is_drawn(qtbot, grid):
    view = shown(qtbot, grid)
    before = view.figure
    view.render()
    assert view.drawing and view.figure is before  # the old figure, still interactive
    assert inked(grabbed(view)) > 100
    settled(qtbot, view)
    assert view.figure is not before and view.canvas.figure is view.figure


def test_a_newer_render_supersedes_the_one_drawing(qtbot, grid):
    view = shown(qtbot, grid)
    emitted = []
    view.rendered.connect(emitted.append)
    view.render()
    grid.params.show_titles = not grid.params.show_titles
    view.render()  # the first one stops between cells; only this one is shown
    settled(qtbot, view)
    assert len(emitted) == 1


def test_a_resize_stretches_the_picture_then_draws_it_again(qtbot, grid):
    view = shown(qtbot, grid)
    first = view.figure
    view.resize(1200, 760)
    assert view.canvas._stale is not None  # kept, not blank
    assert view.render_pending and view.figure is first
    assert inked(grabbed(view)) > 100
    settled(qtbot, view)
    assert view.figure is not first and view.canvas._stale is None
    canvas = view.canvas
    assert (canvas.renderer.width, canvas.renderer.height) == (canvas.width(), canvas.height())
    assert inked(grabbed(view)) > 100


def test_a_figure_size_edit_draws_a_figure_of_the_new_size(qtbot, grid):
    view = shown(qtbot, grid)
    grid.params.figure_width, grid.params.figure_height = 12.0, 6.0
    view.render()
    settled(qtbot, view)
    assert tuple(view.figure.get_size_inches()) == (12.0, 6.0) and view.canvas._inches == (
        12.0,
        6.0,
    )
    assert view.box.ratio == 2.0


def test_the_pan_and_zoom_of_the_picture_on_show_go_on_working(qtbot, grid):
    view = shown(qtbot, grid)
    relax = grid.dataset.cells[1].session
    with qtbot.waitSignal(view.limits_changed, timeout=1000):
        view.figure.axes[1].set_xlim(1.5, 4.5)
        view._on_release(None)
    assert (relax.params.xmin, relax.params.xmax) == (1.5, 4.5)
    view.canvas.draw()  # an interaction draws the adopted figure like any other
    assert view.canvas._stale is None and inked(grabbed(view)) > 100


def test_closing_the_tab_stops_the_worker_and_frees_matplotlib(qtbot, grid):
    view = shown(qtbot, grid)
    states = []
    view.drawing_changed.connect(lambda key, on: states.append(on))
    emitted = []
    view.rendered.connect(emitted.append)
    view.render()
    assert states == [True]
    view.cancel_load()
    assert not view.drawing and states == [True, False]
    assert MPL_LOCK.acquire(timeout=20)  # the worker stopped at its next cell
    MPL_LOCK.release()
    qtbot.wait(100)
    assert emitted == []


def test_a_failed_drawing_is_reported_and_the_old_picture_stays(qtbot, grid, monkeypatch):
    view = shown(qtbot, grid)
    before = view.figure
    states = []
    view.drawing_changed.connect(lambda key, on: states.append(on))

    def broken(session, params, target):
        raise ValueError("boom")

    monkeypatch.setattr(plot_view, "draw_offscreen", broken)
    with qtbot.capture_exceptions() as caught:
        view.render()
        qtbot.waitUntil(lambda: bool(caught), timeout=5000)
    assert [type(exc) for _kind, exc, _tb in caught] == [ValueError]
    assert states == [True, False] and not view.drawing and view.figure is before


def test_a_render_waits_for_nobody_when_matplotlib_is_busy(qtbot, grid):
    """The worker waits for ``MPL_LOCK``; the GUI thread never does (it only starts the worker)."""
    view = shown(qtbot, grid)
    held, release = threading.Event(), threading.Event()

    def exporter():
        with MPL_LOCK:
            held.set()
            release.wait(10)

    thread = threading.Thread(target=exporter)
    thread.start()
    try:
        assert held.wait(5)
        with qtbot.assertNotEmitted(view.rendered, wait=200):
            view.render()
        assert view.drawing
        with qtbot.waitSignal(view.rendered, timeout=30_000):
            release.set()
    finally:
        release.set()
        thread.join(10)
