"""Local busy indicator instead of the global cursor (spec 15 R2)."""

import threading

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from qe_studio.core.calculations import module_for
from qe_studio.ui import services


@pytest.fixture
def no_dialogs(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("a dialog was opened")

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(blocked))


@pytest.fixture
def gated_detection(monkeypatch):
    """Detection waits for the test to open the gate."""
    gate = threading.Event()
    real = services.detect_folder

    def detect(folder, **kwargs):
        gate.wait(5)
        return real(folder, **kwargs)

    monkeypatch.setattr(services, "detect_folder", detect)
    yield gate
    gate.set()


def test_the_footer_spins_while_detecting_and_loading(
    qtbot, main_window, demo_project, gated_detection, no_dialogs
):
    window = main_window
    status = window.status
    assert status.spinner.isHidden() and status.busy.isHidden()
    window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    assert not status.spinner.isHidden() and status.busy.text() == "Detectando cálculo…"
    assert QApplication.overrideCursor() is None
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        gated_detection.set()
    assert status.spinner.isHidden() and status.busy.isHidden()


def test_no_busy_cursor_after_an_invalidated_detection(
    qtbot, main_window, demo_project, gated_detection, no_dialogs
):
    window = main_window
    window.generate_plot_for(demo_project / "03_bands", auto_export=False)
    window.service.invalidate()  # F5 while detecting: the detection starts over
    assert QApplication.overrideCursor() is None
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        gated_detection.set()
    assert QApplication.overrideCursor() is None and window.status.spinner.isHidden()


def test_the_tab_spins_while_its_plot_is_generated_again(
    qtbot, main_window, demo_project, monkeypatch, no_dialogs
):
    window = main_window
    folder = demo_project / "03_bands"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=False)
    key = blocker.args[0].key
    assert not window.workspace.is_busy(key)

    gate = threading.Event()
    module = module_for("bands")
    real = type(module).load_cached

    def slow(self, result, sniff):
        gate.wait(5)
        return real(self, result, sniff)

    monkeypatch.setattr(type(module), "load_cached", slow)
    window.generate_plot_for(folder, auto_export=False)
    qtbot.waitUntil(lambda: window.workspace.is_busy(key), timeout=5000)
    assert window.status.busy.text() == "Carregando estrutura de bandas…"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        gate.set()
    assert not window.workspace.is_busy(key) and window.status.spinner.isHidden()


def test_small_spinner_paints_and_animates_only_while_shown(qtbot):
    from qe_studio.ui.theme.manager import ThemeManager
    from qe_studio.ui.widgets.spinner import CircularProgress

    spinner = CircularProgress(ThemeManager("dark"), 12)
    qtbot.addWidget(spinner)
    assert not spinner._timer.isActive()
    spinner.show()
    assert spinner._timer.isActive() and not spinner.grab().isNull()
    spinner.hide()
    assert not spinner._timer.isActive()
