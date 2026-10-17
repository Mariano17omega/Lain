"""Spec 49 R3: the path takes what is left; the LED and the toggles stay where they are."""

from __future__ import annotations

from PyQt6.QtCore import QPoint


def x_of(widget) -> int:
    return widget.mapTo(widget.window(), QPoint(0, 0)).x()


def measure(window) -> tuple[int, int, int]:
    bar = window.top_bar
    return bar.breadcrumb.width(), x_of(bar.led), x_of(bar.toggles["tree"])


def settle(qtbot, window, folder):
    window.top_bar.set_path(folder)
    qtbot.wait(30)
    return measure(window)


def test_the_right_side_does_not_move_with_the_path(qtbot, main_window, demo_project, tmp_path):
    window = main_window
    window.resize(1400, 800)
    window.show()
    qtbot.waitExposed(window)
    long = demo_project / ("x" * 60 + "_" + "y" * 60)
    long.mkdir()
    root = settle(qtbot, window, demo_project)
    assert settle(qtbot, window, demo_project / "03_bands") == root
    assert settle(qtbot, window, long) == root


def test_plot_file_button_does_not_move_the_led(qtbot, main_window, demo_project):
    window = main_window
    window.resize(1400, 800)
    window.show()
    qtbot.waitExposed(window)
    before = settle(qtbot, window, demo_project / "03_bands")
    window.top_bar.set_plot_file(True, "Plotar SCF", "")
    qtbot.wait(30)
    shown = measure(window)
    assert shown[1:] == before[1:]
    window.top_bar.set_plot_file(False)
    qtbot.wait(30)
    assert measure(window)[1:] == before[1:]


def test_narrow_window_collapses_the_path_and_keeps_the_led_right(qtbot, main_window, demo_project):
    window = main_window
    window.resize(700, 800)
    window.show()
    qtbot.waitExposed(window)
    deep = demo_project / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    window.top_bar.set_path(deep)
    qtbot.wait(30)
    bar = window.top_bar
    assert not bar.breadcrumb.more.isHidden()
    assert x_of(bar.led) > bar.width() // 2
