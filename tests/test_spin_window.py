"""Spin plots through the whole window: the params panel, re-render, zoom and ``*.plot`` (spec 13)."""

import pytest
from matplotlib.backend_bases import MouseEvent
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.ui.widgets.param_widgets import Section
from spin_helpers import SPIN_BANDS, SPIN_PDOS, copy_fixture


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    """Fail loudly if a dialog would block."""
    monkeypatch.setattr("qe_studio.ui.plot_export.ask_overwrite", _blocked)
    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", _blocked)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_blocked))


def _blocked(*args, **kwargs):
    raise AssertionError("a dialog was opened")


def generate(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)


def test_the_panel_offers_the_spin_section_and_rerenders_on_edit(qtbot, main_window, tmp_path):
    folder = copy_fixture(SPIN_BANDS.name, tmp_path)
    generate(qtbot, main_window, folder)
    view = main_window.current_plot()
    assert view.session.dataset.spin and len(view.figure.axes) == 1
    titles = [s.title for s in main_window.params.body.findChildren(Section)]
    assert titles.index("Spin") == titles.index("Estilo") - 1

    main_window.params.set_param("spin_layout", "side")
    qtbot.waitUntil(lambda: len(view.figure.axes) == 2, timeout=3000)
    assert view.figure.axes[0].get_title() == "Spin ↑"

    ax = view.figure.axes[1]  # zoom the right panel: both share the limits
    ax.set_xlim(0.5, 2.0)
    ax.set_ylim(-2.0, 1.0)
    view._on_release(None)
    params = view.session.params
    assert (params.xmin, params.xmax, params.emin, params.emax) == (0.5, 2.0, -2.0, 1.0)

    # the cursor readout of the second panel is the module's, whatever the axes
    view.canvas.draw()
    px, py = view.figure.axes[1].transData.transform((1.0, 0.0))
    view.canvas.callbacks.process(
        "motion_notify_event", MouseEvent("motion_notify_event", view.canvas, px, py)
    )
    assert view.toolbar.message.text().startswith("k = ")

    qtbot.waitUntil(lambda: (folder / "bands.plot").exists(), timeout=5000)
    stored, _ = read_plot_file(folder, "bands")
    assert stored["spin_layout"] == "side" and stored["xmin"] == 0.5


def test_the_pdos_panel_changes_the_spin_mode(qtbot, main_window, tmp_path):
    folder = copy_fixture(SPIN_PDOS.name, tmp_path)
    generate(qtbot, main_window, folder)
    view = main_window.current_plot()
    assert view.figure.axes[0].get_ylim()[0] < 0  # mirrored
    main_window.params.set_param("spin_mode", "overlay")
    qtbot.waitUntil(lambda: view.figure.axes[0].get_ylim()[0] == 0.0, timeout=3000)
