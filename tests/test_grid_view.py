"""Spec 23 R2.4: a grid tab routes the cursor readout, pan/zoom and Reset to each cell's session."""

from matplotlib.backend_bases import MouseEvent

from plot_grid_helpers import BANDS, RELAX, grid_of, settled
from qe_studio.ui.widgets.plot_view import PlotView


def grid_view(qtbot, main_window, tmp_path):
    grid = grid_of([(0, 0, BANDS, ""), (0, 1, RELAX, "")], tmp_path)
    view = PlotView(main_window.theme, grid)
    qtbot.addWidget(view)
    view.resize(900, 500)
    view.show()
    settled(qtbot, view)
    view.canvas.draw()
    bands, relax = (data.session for data in grid.dataset.cells)
    return view, bands, relax


def test_zoom_in_one_cell_changes_only_that_cells_parameters(qtbot, main_window, tmp_path):
    view, bands, relax = grid_view(qtbot, main_window, tmp_path)
    before = (bands.params.emin, bands.params.emax, bands.params.xmin, bands.params.xmax)
    with qtbot.waitSignal(view.limits_changed, timeout=1000):
        view.figure.axes[1].set_xlim(1.5, 4.5)  # the relax cell, at (0, 1)
        view._on_release(None)
    assert (relax.params.xmin, relax.params.xmax) == (1.5, 4.5)
    assert (bands.params.emin, bands.params.emax, bands.params.xmin, bands.params.xmax) == before
    with qtbot.assertNotEmitted(view.limits_changed):
        view._on_release(None)  # nothing moved since


def test_reset_restores_every_cell(qtbot, main_window, tmp_path):
    view, _bands, relax = grid_view(qtbot, main_window, tmp_path)
    view.figure.axes[2].set_xlim(2.0, 3.0)
    view._on_release(None)
    assert relax.params.xmin == 2.0
    view.toolbar.reset.click()
    assert relax.params.xmin is None and relax.params.xmax is None


def test_the_readout_gets_the_index_inside_the_cell(qtbot, main_window, tmp_path, monkeypatch):
    view, _bands, relax = grid_view(qtbot, main_window, tmp_path)
    seen = []
    module = type(relax.module)

    def spy(self, x, y, axes_index, dataset, params):
        seen.append((axes_index, params is relax.params))
        return "ok"

    monkeypatch.setattr(module, "format_coordinates", spy)
    ax = view.figure.axes[2]  # the second panel of the relax cell
    px, py = ax.transAxes.transform((0.5, 0.5))
    view.canvas.callbacks.process(
        "motion_notify_event", MouseEvent("motion_notify_event", view.canvas, px, py)
    )
    assert seen == [(1, True)]
    assert view.toolbar.message.text() == "ok"
