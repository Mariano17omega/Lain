"""Qt's own messages in the log (spec 90 R7.2): by default they only reach the stderr, which a program
started from the desktop menu does not have. A warning about a style or a plugin is often the cause
of what the user sees."""

from __future__ import annotations

import atexit
import contextlib
import logging

from PyQt6.QtCore import QMessageLogContext, QtMsgType, qInstallMessageHandler

log = logging.getLogger("qe_studio.qt")

_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def _on_message(kind: QtMsgType, _context: QMessageLogContext, message: str | None) -> None:
    """Called by Qt, from any thread: an exception that left here would have nowhere to go."""
    with contextlib.suppress(Exception):
        log.log(_LEVELS.get(kind, logging.WARNING), "%s", message)


def install_qt_log() -> None:
    """Qt's messages go to the log until Python starts to finalize: what Qt says after that cannot
    enter Python, so it goes back to the stderr."""
    qInstallMessageHandler(_on_message)
    atexit.register(qInstallMessageHandler, None)
