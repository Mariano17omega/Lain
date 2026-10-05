"""Closing a plot tab (spec 27-4 R1.4, R2.4): ends the load of it that is still pending, and frees
the big datasets it shows."""

import threading

import pytest
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.load_cache import CACHE
from qe_studio.ui import plot_workflow


@pytest.fixture
def no_dialogs(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("a dialog was opened")

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(blocked))


def open_bands(qtbot, window, demo_project):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    return blocker.args[0].key


def slow_loads(monkeypatch):
    """``load_cached`` of the bands module waits for the returned gate."""
    gate, module = threading.Event(), module_for("bands")
    real = type(module).load_cached

    def slow(self, result, sniff):
        gate.wait(5)
        return real(self, result, sniff)

    monkeypatch.setattr(type(module), "load_cached", slow)
    return gate


def test_closing_the_tab_during_a_regenerate_does_not_reopen_it(
    qtbot, main_window, demo_project, monkeypatch, no_dialogs
):
    window = main_window
    key = open_bands(qtbot, window, demo_project)
    gate = slow_loads(monkeypatch)
    window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    qtbot.waitUntil(lambda: window.workspace.is_busy(key), timeout=5000)
    handle = window.plot_workflow._loads.active(key)
    assert handle is not None

    window.workspace.close_key(key)
    assert handle.cancelled
    assert window.workspace.widget_for(key) is None
    assert window.status.spinner.isHidden() and window.plot_workflow._loading == {}

    gate.set()
    assert handle.wait(5)
    qtbot.wait(100)
    assert window.workspace.widget_for(key) is None  # the load ended: nothing opens
    assert window.plot_workflow.current_plot() is None
    assert window.status.spinner.isHidden()


def test_a_plot_can_be_generated_again_after_closing_it_mid_load(
    qtbot, main_window, demo_project, monkeypatch, no_dialogs
):
    window = main_window
    key = open_bands(qtbot, window, demo_project)
    gate = slow_loads(monkeypatch)
    window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    qtbot.waitUntil(lambda: window.workspace.is_busy(key), timeout=5000)
    window.workspace.close_key(key)
    gate.set()
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):  # not blocked by the old load
        window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    assert window.workspace.widget_for(key) is not None


def test_closing_the_tab_frees_its_dataset_when_it_is_big(
    qtbot, main_window, demo_project, monkeypatch, no_dialogs
):
    window = main_window
    monkeypatch.setattr(plot_workflow, "CLOSE_DROP_MIN_BYTES", 1)  # any dataset counts as big
    key = open_bands(qtbot, window, demo_project)
    assert len(CACHE) >= 1
    window.workspace.close_key(key)
    assert len(CACHE) == 0


def test_closing_the_tab_keeps_a_small_dataset(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    key = open_bands(qtbot, window, demo_project)
    cached = len(CACHE)
    assert cached >= 1 and CACHE.total_bytes < 4 * 1024 * 1024
    window.workspace.close_key(key)
    assert len(CACHE) == cached  # reopening it is instant


def test_generating_again_keeps_the_dataset_of_the_tab_it_replaces(
    qtbot, main_window, demo_project, monkeypatch, no_dialogs
):
    window = main_window
    monkeypatch.setattr(plot_workflow, "CLOSE_DROP_MIN_BYTES", 1)
    key = open_bands(qtbot, window, demo_project)
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    assert window.workspace.widget_for(key) is not None
    assert len(CACHE) >= 1  # the new tab shows it: the replaced one did not drop it
    window.workspace.close_key(key)
    assert len(CACHE) == 0
