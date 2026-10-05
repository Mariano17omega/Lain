"""The unexpected-error hook (spec 27-5 R3): a toast instead of a modal per exception, the same
error counted instead of repeated, one at a time."""

import logging
import sys

import pytest
from PyQt6.QtWidgets import QMessageBox

from qe_studio.ui import app, excepthook
from qe_studio.ui.excepthook import ExceptionReporter


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeToast:
    def __init__(self):
        self.shown = []

    def show_message(self, text, level="info", details=""):
        self.shown.append((text, level, details))


class FakeWindow:
    def __init__(self, visible=True):
        self.toast, self.visible = FakeToast(), visible

    def isVisible(self) -> bool:
        return self.visible


def raised(error: Exception):
    """``(type, value, traceback)`` of ``error`` as ``sys.excepthook`` gets them."""
    try:
        raise error
    except Exception:
        return sys.exc_info()


def boom(message="falhou"):
    return raised(ValueError(message))


@pytest.fixture
def boxes(qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    return shown


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def reporter(clock):
    return ExceptionReporter(clock=clock)


@pytest.fixture
def window(reporter):
    window = FakeWindow()
    reporter.set_window(window)
    return window


def test_the_error_is_a_toast_with_the_traceback(qtbot, boxes, reporter, window):
    reporter(*boom("sem espaço"))
    [(text, level, details)] = window.toast.shown
    assert text == "Erro inesperado: ValueError: sem espaço (ver o log)"
    assert level == "error"
    assert "Traceback" in details and "ValueError: sem espaço" in details
    assert "Log: " in details
    assert boxes == []


def test_a_long_message_is_cut_in_the_toast_and_whole_in_the_details(
    qtbot, boxes, reporter, window
):
    reporter(*boom("x" * 500 + "\nsegunda linha"))
    [(text, _level, details)] = window.toast.shown
    assert len(text) < 200 and "segunda linha" not in text
    assert "segunda linha" in details


def test_the_same_error_twice_is_one_toast_and_a_count(qtbot, boxes, reporter, window, caplog):
    with caplog.at_level(logging.ERROR, logger="qe_studio"):
        for _ in range(2):
            reporter(*boom())  # one call site: the same ``file:line``
    assert len(window.toast.shown) == 1
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["erro inesperado", "erro inesperado (x2)"]  # every one is in the log


def test_another_error_is_another_toast(qtbot, boxes, reporter, window):
    reporter(*boom("um"))
    reporter(*boom("dois"))
    reporter(*raised(KeyError("um")))
    assert len(window.toast.shown) == 3


def test_after_the_window_the_same_error_shows_again(qtbot, boxes, reporter, window, clock, caplog):
    def again():
        reporter(*boom())

    again()
    clock.now += 9.9
    again()
    assert len(window.toast.shown) == 1
    clock.now += 0.2  # 10.1 s after it was shown
    with caplog.at_level(logging.ERROR, logger="qe_studio"):
        again()
    assert len(window.toast.shown) == 2
    assert caplog.records[-1].getMessage() == "erro inesperado"  # the count starts over


def test_an_error_while_reporting_goes_to_the_log_only(qtbot, boxes, reporter, window, caplog):
    inner = boom("de dentro")

    def failing_toast(text, level="info", details=""):
        reporter(*inner)  # a slot that fails in the middle of showing the first error
        window.toast.shown.append(text)

    window.toast.show_message = failing_toast
    with caplog.at_level(logging.ERROR, logger="qe_studio"):
        reporter(*boom("de fora"))
    assert window.toast.shown == ["Erro inesperado: ValueError: de fora (ver o log)"]
    assert boxes == []
    assert any("durante o tratamento" in r.getMessage() for r in caplog.records)


def test_the_hook_survives_a_failing_toast(qtbot, boxes, reporter, window, caplog):
    def broken(text, level="info", details=""):
        raise RuntimeError("toast gone")

    window.toast.show_message = broken
    with caplog.at_level(logging.ERROR, logger="qe_studio"):
        reporter(*boom())
        reporter(*boom("outro"))  # not stuck "handling"
    assert "falha ao informar" in caplog.text


def test_before_the_window_exists_one_box_per_error(qtbot, boxes, reporter):
    reporter(*boom())
    reporter(*boom())
    assert len(boxes) == 1
    title, text = boxes[0][1], boxes[0][2]
    assert title == "Erro inesperado" and "ValueError: falhou" in text


def test_a_hidden_window_gets_the_log_only(qtbot, boxes, reporter, window):
    window.visible = False  # closing
    reporter(*boom())
    assert window.toast.shown == [] and boxes == []


def test_a_window_that_is_gone_gets_the_log_only(qtbot, boxes, reporter):
    reporter.set_window(FakeWindow())  # nothing else holds it: the weak reference dies
    reporter(*boom())
    assert boxes == []


def test_no_application_no_box(monkeypatch, boxes, reporter):
    monkeypatch.setattr(excepthook.QApplication, "instance", staticmethod(lambda: None))
    reporter(*boom())
    assert boxes == []


def test_install_replaces_sys_excepthook_and_the_app_reexports_it(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    app.install_excepthook()
    assert sys.excepthook is excepthook.REPORTER
    assert app.set_excepthook_window is excepthook.set_excepthook_window
