"""Qt's own messages reach the log (spec 90 R7.2). Each test puts the handler it found back."""

import logging

import pytest
from PyQt6.QtCore import qCritical, qDebug, qInfo, qInstallMessageHandler, qWarning

from qe_studio.ui.shell import qt_log


@pytest.fixture
def handler(qapp):
    previous = qInstallMessageHandler(None)
    qt_log.install_qt_log()
    yield
    qInstallMessageHandler(previous)


@pytest.mark.parametrize(
    ("say", "level"),
    [
        (qDebug, logging.DEBUG),
        (qInfo, logging.INFO),
        (qWarning, logging.WARNING),
        (qCritical, logging.ERROR),
    ],
)
def test_a_qt_message_reaches_the_log_at_its_level(handler, caplog, say, level):
    caplog.set_level(logging.DEBUG, logger="qe_studio")
    say("uma mensagem do Qt")
    [record] = [r for r in caplog.records if r.name == "qe_studio.qt"]
    assert (record.getMessage(), record.levelno) == ("uma mensagem do Qt", level)


def test_a_qt_warning_reaches_the_log(handler, caplog):
    qWarning("um aviso do Qt")  # at the level of a test: only WARNING and above
    assert "um aviso do Qt" in caplog.text


def test_the_handler_never_raises(handler, monkeypatch):
    def broken(*_args):
        raise RuntimeError("the log is gone")

    monkeypatch.setattr(qt_log.log, "log", broken)
    qWarning("nowhere to go")  # an exception here would reach Qt's C++
