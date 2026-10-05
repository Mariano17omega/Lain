"""What the app does with an exception nobody caught (spec 27-5 R3).

PyQt6 would abort the whole app on one, so ``sys.excepthook`` is replaced. Every occurrence goes to
the log. The user hears of it once: a toast of the window ("Detalhes" has the traceback), or, before
the window exists (an error while starting), one message box. The same error repeated within
``DEDUP_S`` only counts, and an exception raised while another is being reported (a slot that
fails in the box's own event loop) goes to the log alone, so one bug never becomes a stack of
modal boxes.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
import weakref
from collections.abc import Callable
from types import TracebackType

from PyQt6.QtWidgets import QApplication, QMessageBox

from ..core.appdirs import log_path

log = logging.getLogger("qe_studio")

DEDUP_S = 10.0  # the same error inside this long after it was shown only counts
TITLE = "Erro inesperado"
MAX_KEYS = 50  # kinds of error remembered
SHORT_CHARS = 120  # of the error's text in the toast; the rest is in "Detalhes"

Key = tuple[str, str, str]


class ExceptionReporter:
    """``sys.excepthook`` with state: the dedup table, the reentrancy flag and the window."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, window_s: float = DEDUP_S):
        self._clock, self._window_s = clock, window_s
        self._seen: dict[Key, tuple[float, int]] = {}  # key → (when it was shown, how many since)
        self._handling = False
        self._window: weakref.ref | None = None  # set once the window exists

    def set_window(self, window) -> None:
        """Errors are shown as toasts of ``window`` from now on (a weak reference is kept)."""
        self._window = weakref.ref(window)

    def __call__(
        self, kind: type[BaseException], value: BaseException, tb: TracebackType | None
    ) -> None:
        exc_info = (kind, value, tb)
        if self._handling:
            log.error("erro inesperado (durante o tratamento de outro)", exc_info=exc_info)
            return
        self._handling = True
        try:
            shown, count = self._count(kind, value, tb)
            log.error("erro inesperado" + (f" (x{count})" if count > 1 else ""), exc_info=exc_info)
            if shown:
                self._present(kind, value, tb)
        except Exception:  # the hook itself must never raise: that would end the app
            log.exception("falha ao informar um erro inesperado")
        finally:
            self._handling = False

    def _count(self, kind, value, tb) -> tuple[bool, int]:
        """(show it now?, how many times it happened since it was last shown)."""
        key = (kind.__name__, str(value), _where(tb))
        now = self._clock()
        if len(self._seen) > MAX_KEYS:  # a long session: forget what is out of the window anyway
            self._seen = {k: v for k, v in self._seen.items() if now - v[0] < self._window_s}
        last = self._seen.get(key)
        if last is not None and now - last[0] < self._window_s:
            self._seen[key] = (last[0], last[1] + 1)
            return False, last[1] + 1
        self._seen[key] = (now, 1)
        return True, 1

    def _present(self, kind, value, tb) -> None:
        if QApplication.instance() is None:
            return
        if self._window is None:  # before the window: a failing start-up
            QMessageBox.critical(
                None, TITLE, f"{kind.__name__}: {value}\n\nDetalhes no log ({log_path()})."
            )
            return
        window = self._window()
        try:
            if window is None or not window.isVisible():
                return  # closing or closed: the log has it
        except RuntimeError:  # the Qt object is deleted already
            return
        short = str(value).splitlines()[0][:SHORT_CHARS] if str(value) else ""
        text = f"{TITLE}: {kind.__name__}" + (f": {short}" if short else "") + " (ver o log)"
        trace = "".join(traceback.format_exception(kind, value, tb))
        window.toast.show_message(text, "error", f"{trace}\nLog: {log_path()}")


def _where(tb: TracebackType | None) -> str:
    """``file:line`` of the innermost frame: where the error was raised."""
    frames = traceback.extract_tb(tb)
    return f"{frames[-1].filename}:{frames[-1].lineno}" if frames else "?"


REPORTER = ExceptionReporter()


def install_excepthook() -> None:
    """Report unexpected errors instead of letting PyQt6 abort the whole app."""
    sys.excepthook = REPORTER


def set_excepthook_window(window) -> None:
    """The window whose toast shows the errors (``app.main`` calls it once it is built)."""
    REPORTER.set_window(window)
