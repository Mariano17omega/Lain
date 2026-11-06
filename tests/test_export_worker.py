"""Exporting in a worker (spec 15 R3): the window keeps running, the screen waits for matplotlib
without blocking, and no half-written file is left."""

import threading
import time

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.plotting import export as export_module
from qe_studio.core.plotting.mpl_lock import MPL_LOCK


@pytest.fixture
def no_dialogs(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("a dialog was opened")

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(blocked))


@pytest.fixture
def slow_export(monkeypatch):
    """The export's render takes half a second (a 600 DPI PDOS, say)."""
    real = export_module.render_figure

    def slow(*args, **kwargs):
        time.sleep(0.5)
        return real(*args, **kwargs)

    monkeypatch.setattr(export_module, "render_figure", slow)


def plot(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=False)
    return blocker.args[0]


def test_exporting_does_not_block_the_event_loop(
    qtbot, main_window, demo_project, slow_export, no_dialogs
):
    window = main_window
    folder = demo_project / "03_bands"
    plot(qtbot, window, folder)
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    with qtbot.waitSignal(window.export_finished, timeout=10_000) as blocker:
        assert window.export_plot()
        assert window.status.busy.text() == "Exportando…" and not window.status.spinner.isHidden()
    timer.stop()
    assert len(ticks) >= 10  # the loop ran during the half-second render
    names = ["03_bands-bands.png", "03_bands-bands.svg", "03_bands-bands.pdf", "03_bands-bands.csv"]
    assert [p.name for p in blocker.args[0]] == names
    assert all(p.stat().st_size > 0 for p in blocker.args[0])
    assert not list((folder / "plots").glob(".*.tmp"))
    assert window.status.spinner.isHidden()
    assert window.status.message.text() == "Salvo em plots/: " + ", ".join(names)


def test_a_screen_render_during_an_export_waits_and_then_happens(
    qtbot, main_window, demo_project, no_dialogs
):
    window = main_window
    plot(qtbot, window, demo_project / "03_bands")
    view = window.current_plot()
    held, release = threading.Event(), threading.Event()

    def exporter():  # stands for an export holding matplotlib
        with MPL_LOCK:
            held.set()
            release.wait(5)

    thread = threading.Thread(target=exporter)
    thread.start()
    try:
        assert held.wait(5)
        with qtbot.assertNotEmitted(view.rendered, wait=150):
            view.render()  # returns at once: the GUI thread never waits for the lock
        assert view.render_pending
        with qtbot.waitSignal(view.rendered, timeout=3000):
            release.set()
    finally:
        release.set()
        thread.join(5)
    assert not view.render_pending


def test_closing_the_window_waits_for_a_running_export(
    qtbot, main_window, demo_project, slow_export, no_dialogs
):
    window = main_window
    folder = demo_project / "03_bands"
    plot(qtbot, window, folder)
    assert window.export_plot()
    window.close()  # the export was still rendering
    assert sorted(p.name for p in (folder / "plots").iterdir()) == [
        "03_bands-bands.csv",
        "03_bands-bands.pdf",
        "03_bands-bands.png",
        "03_bands-bands.svg",
    ]


def test_edits_after_the_export_starts_are_not_in_it(
    qtbot, main_window, demo_project, slow_export, no_dialogs, monkeypatch
):
    window = main_window
    plot(qtbot, window, demo_project / "03_bands")
    seen = []
    real = export_module.export_figure  # what ``export_files`` calls

    def spy(module, dataset, params, *args, **kwargs):
        seen.append(params.emin)
        return real(module, dataset, params, *args, **kwargs)

    monkeypatch.setattr(export_module, "export_figure", spy)
    with qtbot.waitSignal(window.export_finished, timeout=10_000):
        assert window.export_plot()
        window.params.set_param("emin", -1.0)
    assert seen == [-5.0]
