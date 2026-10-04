"""The toast (spec 17 R3.4): placement, queue, countdown and fade, pause, click, details and its
life inside the window. Durations are injected: nothing waits 6 real seconds."""

import logging
import time

import pytest
from PyQt6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, QSize, Qt
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QStatusBar

from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.toast import FADE_MS, MARGIN, TOAST_MS, WIDTH, Toast, toast_position


@pytest.mark.parametrize(
    ("parent", "toast", "footer", "expected"),
    [
        (QSize(800, 600), QSize(300, 80), 24, QPoint(484, 480)),
        (QSize(800, 600), QSize(300, 80), 0, QPoint(484, 504)),
        (QSize(200, 600), QSize(380, 80), 24, QPoint(16, 480)),  # narrowed to the parent
        (QSize(20, 50), QSize(380, 80), 24, QPoint(4, 0)),  # no room: zero wide, never negative
    ],
)
def test_toast_position(parent, toast, footer, expected):
    assert toast_position(parent, toast, MARGIN, footer) == expected


@pytest.fixture
def window(qtbot):
    window = QMainWindow()
    window.setStatusBar(QStatusBar())
    window.resize(800, 600)
    qtbot.addWidget(window)
    window.show()
    return window


def make(window, duration_ms=60, fade_ms=30):
    status = window.statusBar()
    return Toast(ThemeManager("dark"), window, status, duration_ms=duration_ms, fade_ms=fade_ms)


def record(toast):
    events = []
    toast.shown.connect(lambda text: events.append(("shown", text)))
    toast.expired.connect(lambda: events.append(("expired",)))
    toast.closed.connect(lambda: events.append(("closed",)))
    return events


def expected_pos(window, toast):
    footer = window.statusBar().height()
    return toast_position(window.size(), toast.size(), MARGIN, footer)


def test_defaults_are_six_seconds_and_a_300_ms_fade(window):
    toast = Toast(ThemeManager("dark"), window)
    toast.show_message("12 arquivo(s) baixado(s).", "success")
    animation = toast.countdown_animation
    assert (toast.duration_ms, toast.fade_ms) == (TOAST_MS, FADE_MS) == (6000, 300)
    assert animation.duration() == 6000 and animation.state() == QAbstractAnimation.State.Running
    assert (animation.startValue(), animation.endValue()) == (1.0, 0.0)
    assert toast.isVisible() and toast.text.text() == "12 arquivo(s) baixado(s)."
    assert toast.countdown.height() == 3 and toast.countdown.y() + 3 <= toast.height()
    toast.shutdown()


def test_the_countdown_runs_out_then_the_toast_fades(qtbot, window):
    toast = make(window, duration_ms=80, fade_ms=40)
    events = record(toast)
    start = time.monotonic()
    with qtbot.waitSignal(toast.closed, timeout=3000):
        toast.show_message("oi")
    assert time.monotonic() - start >= 0.1
    assert events == [("shown", "oi"), ("expired",), ("closed",)]
    assert toast.fade_animation.duration() == 40 and toast.countdown.fraction == 0.0
    assert not toast.isVisible() and toast.current is None


def test_the_next_notice_waits_for_the_fade(qtbot, window):
    toast = make(window)
    events = record(toast)
    toast.show_message("primeiro")
    toast.show_message("segundo", "warning")
    assert events == [("shown", "primeiro")]
    qtbot.waitUntil(lambda: ("shown", "segundo") in events, timeout=3000)
    assert events[:4] == [("shown", "primeiro"), ("expired",), ("closed",), ("shown", "segundo")]
    assert toast.property("level") == "warning"
    with qtbot.waitSignal(toast.closed, timeout=3000):
        pass


def test_a_click_closes_at_once(qtbot, window):
    toast = make(window, duration_ms=5000)
    events = record(toast)
    toast.show_message("um")
    toast.show_message("dois")
    QTest.mouseClick(toast, Qt.MouseButton.LeftButton)
    assert events == [("shown", "um"), ("closed",), ("shown", "dois")]  # no fade
    QTest.mouseClick(toast, Qt.MouseButton.LeftButton)
    assert (
        not toast.isVisible() and toast.fade_animation.state() == QAbstractAnimation.State.Stopped
    )


def test_the_mouse_over_it_pauses_the_countdown(qtbot, window):
    toast = make(window, duration_ms=300)
    toast.show_message("oi")
    animation = toast.countdown_animation
    qtbot.wait(50)
    point = QPointF(5, 5)
    QApplication.sendEvent(toast, QEnterEvent(point, point, toast.mapToGlobal(point)))
    assert animation.state() == QAbstractAnimation.State.Paused
    paused_at = animation.currentTime()
    qtbot.wait(400)  # longer than the whole countdown
    assert animation.currentTime() == paused_at and toast.isVisible()
    QApplication.sendEvent(toast, QEvent(QEvent.Type.Leave))
    assert animation.state() == QAbstractAnimation.State.Running
    assert animation.currentTime() >= paused_at  # resumes where it stopped
    with qtbot.waitSignal(toast.closed, timeout=3000):
        pass


def test_it_follows_the_window_size(qtbot, window):
    toast = make(window, duration_ms=5000)
    toast.show_message("oi")
    assert toast.width() == WIDTH and toast.pos() == expected_pos(window, toast)
    window.resize(1000, 700)
    assert toast.pos() == expected_pos(window, toast)
    assert toast.geometry().bottom() < window.height() - window.statusBar().height()
    window.resize(300, 400)
    assert toast.width() == 300 - 2 * MARGIN and toast.pos() == expected_pos(window, toast)
    toast.shutdown()


def test_it_is_a_child_that_moves_with_the_window(qtbot, window):
    toast = make(window, duration_ms=5000)
    toast.show_message("oi")
    assert toast.parentWidget() is window and not toast.isWindow()
    before = toast.pos()
    window.move(window.pos() + QPoint(40, 30))
    assert toast.pos() == before  # same corner: its position is relative to the window
    toast.shutdown()


def test_closing_the_window_stops_everything(qtbot, window):
    toast = make(window, duration_ms=60, fade_ms=30)
    events = record(toast)
    toast.show_message("oi")
    toast.show_message("depois")
    window.close()
    assert not toast.isVisible() and toast.current is None
    for animation in (toast.countdown_animation, toast.fade_animation):
        assert animation.state() == QAbstractAnimation.State.Stopped
    qtbot.wait(200)  # past both durations: nothing fires
    toast.show_message("tarde demais")
    assert events == [("shown", "oi")] and not toast.isVisible()


def test_details_open_beside_the_window(qtbot, window):
    toast = make(window, duration_ms=5000)
    toast.show_message("sem detalhes")
    assert toast.details_button.isHidden()
    toast.dismiss()
    toast.show_message("2 arquivo(s) baixado(s).", "success", "relatório\ncompleto")
    assert not toast.details_button.isHidden()
    toast.details_button.click()
    dialog = toast.details_dialog
    assert dialog is not None and dialog.isVisible() and not dialog.isModal()
    assert dialog.text.toPlainText() == "relatório\ncompleto"
    assert not toast.isVisible()  # the notice is done
    dialog.close()


def test_a_theme_change_repaints_it(qtbot, window):
    theme = ThemeManager("dark")
    toast = Toast(theme, window, duration_ms=5000)
    toast.show_message("oi", "warning")
    theme.toggle()
    assert toast.countdown.color() == theme.color("warning")
    toast.shutdown()


def test_the_main_window_toast_follows_resize_and_close(qtbot, main_window, caplog):
    toast = main_window.toast
    toast.duration_ms, toast.fade_ms = 60, 30
    events = record(toast)
    toast.show_message("oi")
    main_window.resize(1000, 700)
    footer = main_window.status.height()
    assert toast.pos() == toast_position(main_window.size(), toast.size(), MARGIN, footer)
    main_window.close()
    qtbot.wait(200)
    assert events == [("shown", "oi")] and not toast.isVisible()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
