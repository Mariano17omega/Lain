"""Closing the main window (spec 27-5).

``MainWindow.closeEvent`` asks the open dialogs first (``close_dialogs``: the "Criar cálculo"
window keeps what was typed until the user says so), then ``run_shutdown`` hides the window and
runs the steps of ``steps_for`` inside one budget (``TOTAL_MS``), so a slow disk or cluster never
leaves a frozen window on screen. Every step gets the milliseconds it may take and says whether it
finished in time; the ones that did not are logged. No step is skipped: with the budget gone a step
gets 0 ms and does only its non-blocking part, and the state of the user (``estado``) is written
whatever happened before. Figure exports are the exception to the budget: they are never cut short
before their own deadline (``EXPORT_WAIT_MS``: no half-written file), and the time they take is not
charged to it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple

from .plot_export import EXPORT_WAIT_MS

if TYPE_CHECKING:
    from .main_window import MainWindow

log = logging.getLogger(__name__)

TOTAL_MS = 8000  # all the steps together, exports aside
SYNC_MS = 2000  # a running pull or push, then it is killed
DETECTION_MS = 2000
GRID_MS = 1000


class Step(NamedTuple):
    name: str
    run: Callable[[int], bool | None]  # given the ms it may take; False: it did not finish in time
    cap_ms: int | None = None  # its share of the budget never goes above this
    own_budget: bool = False  # waits ``cap_ms`` whatever is left, and is not charged to the total


class ShutdownReport(NamedTuple):
    elapsed_ms: int
    ok: list[str]
    late: list[str]  # steps that overran their time or raised


class ShutdownSequence:
    def __init__(
        self,
        steps: list[Step],
        total_ms: int = TOTAL_MS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.steps, self.total_ms, self._clock = steps, total_ms, clock

    def run(self) -> ShutdownReport:
        start = self._clock()
        free = 0.0  # seconds spent in steps with their own budget
        ok: list[str] = []
        late: list[str] = []
        for step in self.steps:
            left = max(0, int(self.total_ms - (self._clock() - start - free) * 1000))
            if step.own_budget and step.cap_ms is not None:
                ms = step.cap_ms
            else:
                ms = left if step.cap_ms is None else min(step.cap_ms, left)
            began = self._clock()
            try:
                finished = step.run(ms) is not False
            except Exception:  # the steps after it still have to run (the user's state above all)
                log.exception("encerramento: %s falhou", step.name)
                finished = False
            if step.own_budget:
                free += self._clock() - began
            if finished:
                ok.append(step.name)
            else:
                late.append(step.name)
                log.warning("encerramento: %s não terminou em %d ms", step.name, ms)
        elapsed = int((self._clock() - start) * 1000)
        log.info("encerramento: %d ms; ok: %s; estouros: %s", elapsed, ok, late or "nenhum")
        return ShutdownReport(elapsed, ok, late)


def steps_for(window: MainWindow) -> list[Step]:
    """The steps of closing ``window``, in order (cancel, sync, exports, ``.plot``, state, workers)."""

    def cancel(_ms: int) -> None:
        window.plot_workflow.cancel_loads()
        window.workspace.cancel_loads()
        window.grids.loader.cancel_all()
        window.derive.cancel()
        window.command_palette.cancel()
        window.project.cancel()

    def save_state(_ms: int) -> None:
        window.navigation.shutdown()
        window.settings.setValue("explorer/last_folder", str(window.current_folder()))
        window.settings.setValue("ui/theme", window.theme.mode)
        window.settings.sync()

    return [
        Step("cancelar", cancel),
        Step("sync", window.sync.shutdown, cap_ms=SYNC_MS),
        Step("exportações", window.plot_workflow.shutdown, cap_ms=EXPORT_WAIT_MS, own_budget=True),
        Step(".plot", window.plot_settings.close),
        Step("estado", save_state),
        Step("detecção", window.service.shutdown, cap_ms=DETECTION_MS),
        # last: the panels' filters stop (``current_folder`` needs them above)
        Step("grade", window.files.shutdown, cap_ms=GRID_MS),
        Step("árvore", lambda _ms: window.explorer.shutdown()),
    ]


def close_dialogs(window: MainWindow) -> bool:
    """Close the non-modal dialogs before anything is shut down; False when one stays open.

    The one that can refuse comes first: when the user keeps it, the others are not touched.
    """
    return all(c.close_dialog() for c in (window.calc_create, window.grids, window.help))


def run_shutdown(window: MainWindow) -> ShutdownReport:
    """Save the layout, hide the window and run the steps; the report is what did not finish."""
    window.panel_layout.save()  # the geometry is read while the window is still on screen
    window.hide()  # nothing looks frozen while the steps wait
    return ShutdownSequence(steps_for(window)).run()
