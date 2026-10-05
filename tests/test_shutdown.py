"""Closing the main window (spec 27-5 R1, R2): the sequence and its budget, the dialogs asked first,
and ``app.finish`` leaving when a worker will not stop."""

import logging
import threading
from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThreadPool

from qe_studio.core.tasks import run_task
from qe_studio.ui import app, shutdown
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.shutdown import ShutdownReport, ShutdownSequence, Step

from calc_dialog_helpers import to_files
from calc_helpers import AL_SCF


class Clock:
    """Time that only the steps move: the budget is tested without sleeping."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def spend(self, ms: int) -> None:
        self.now += ms / 1000


def sequence(clock, steps, total_ms=1000):
    return ShutdownSequence(steps, total_ms=total_ms, clock=clock)


# -- the sequence ---------------------------------------------------------------------------------
def test_every_step_gets_what_is_left_of_the_budget():
    clock, given = Clock(), {}

    def step(name, spent):
        def run(ms):
            given[name] = ms
            clock.spend(spent)

        return Step(name, run)

    report = sequence(clock, [step("a", 300), step("b", 200), step("c", 0)]).run()
    assert given == {"a": 1000, "b": 700, "c": 500}
    assert report.ok == ["a", "b", "c"] and report.late == [] and report.elapsed_ms == 500


def test_a_cap_limits_the_share():
    clock, given = Clock(), {}
    steps = [
        Step("capped", lambda ms: given.setdefault("capped", ms), cap_ms=200),
        Step("loose", lambda ms: given.setdefault("loose", ms)),
    ]
    sequence(clock, steps).run()
    assert given == {"capped": 200, "loose": 1000}


def test_a_slow_step_is_logged_and_the_rest_still_runs(caplog):
    clock, ran = Clock(), []

    def slow(ms):
        clock.spend(5000)  # far over the 1000 ms budget
        return False

    steps = [Step("slow", slow), Step("state", lambda ms: ran.append(ms))]
    with caplog.at_level(logging.INFO, logger=shutdown.log.name):
        report = sequence(clock, steps).run()
    assert report.late == ["slow"] and report.ok == ["state"]
    assert ran == [0]  # no budget left: the step runs and does the part that does not wait
    assert "slow não terminou em 1000 ms" in caplog.text
    assert "estouros: ['slow']" in caplog.text


def test_a_step_that_raises_does_not_stop_the_state_from_being_saved(caplog):
    saved = []

    def boom(ms):
        raise RuntimeError("disk gone")

    steps = [Step("boom", boom), Step("state", lambda ms: saved.append(True))]
    with caplog.at_level(logging.WARNING, logger=shutdown.log.name):
        report = sequence(Clock(), steps).run()
    assert saved == [True]
    assert report.late == ["boom"] and "boom falhou" in caplog.text


def test_exports_wait_their_own_time_and_it_is_not_charged_to_the_budget():
    clock, given = Clock(), {}

    def exports(ms):
        given["exportações"] = ms
        clock.spend(6000)  # a big figure: longer than the whole budget

    steps = [
        Step("exportações", exports, cap_ms=10_000, own_budget=True),
        Step(".plot", lambda ms: given.setdefault(".plot", ms)),
    ]
    report = sequence(clock, steps).run()
    assert given == {"exportações": 10_000, ".plot": 1000}
    assert report.late == []


# -- the real window ------------------------------------------------------------------------------
@pytest.fixture
def asked(monkeypatch):
    """The discard question, patched (a real one blocks, even at teardown). Request it before the
    window so it is undone after the window closed."""
    calls = []

    def ask(parent):
        calls.append(parent)
        return ask.answer

    ask.answer = True
    ask.calls = calls
    monkeypatch.setattr(dialog_module, "ask_discard", ask)
    return ask


def open_dirty_dialog(qtbot, window):
    """The "Criar cálculo" window on its second step, with a field edited by the user."""
    window.activity.new_calc.click()
    dialog = window.calc_create.dialog
    assert dialog is not None
    tabs = to_files(qtbot, dialog, "pdos")
    tabs.widget_of("nbnd").setText("")
    qtbot.keyClicks(tabs.widget_of("nbnd"), "42")
    assert tabs.dirty
    return dialog


def test_close_hides_the_window_before_anything_waits(qtbot, main_window, monkeypatch):
    window, seen = main_window, []
    real = shutdown.steps_for

    def probe(ms):
        seen.append(window.isVisible())

    monkeypatch.setattr(shutdown, "steps_for", lambda w: [Step("probe", probe), *real(w)])
    window.close()
    assert seen == [False]
    assert isinstance(window.shutdown_report, ShutdownReport)
    assert window.shutdown_report.late == []


def test_the_state_is_saved_when_a_step_overruns(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    window.explorer.select_path(demo_project / "03_bands")
    real = shutdown.steps_for
    monkeypatch.setattr(
        shutdown, "steps_for", lambda w: [Step("lento", lambda ms: False), *real(w)]
    )
    window.close()
    assert window.shutdown_report.late == ["lento"]
    assert window.settings.value("explorer/last_folder") == str(demo_project / "03_bands")


def test_closing_twice_is_harmless(qtbot, main_window):
    main_window.close()
    main_window.close()
    assert main_window.shutdown_report is not None


def test_keeping_the_dialog_keeps_the_window(qtbot, asked, main_window):
    window = main_window
    dialog = open_dirty_dialog(qtbot, window)
    asked.answer = False
    window.close()
    assert window.isVisible() and window.calc_create.dialog is dialog
    assert window.shutdown_report is None  # nothing was shut down
    assert len(asked.calls) == 1
    asked.answer = True
    window.close()
    assert not window.isVisible()
    assert window.calc_create.dialog is None or sip.isdeleted(dialog)


def test_a_dialog_without_edits_closes_with_the_window(qtbot, asked, main_window):
    window = main_window
    window.activity.new_calc.click()
    assert window.calc_create.dialog is not None
    window.close()
    assert not window.isVisible() and window.shutdown_report is not None
    assert asked.calls == []  # nothing typed: no question


def test_a_folder_being_made_keeps_the_window_open(qtbot, asked, main_window):
    window = main_window
    window.activity.new_calc.click()
    dialog = window.calc_create.dialog
    dialog.set_busy(True)  # "Criar" is writing the folder
    window.close()
    assert window.isVisible() and window.calc_create.dialog is dialog
    assert asked.calls == []
    dialog.set_busy(False)
    window.close()
    assert not window.isVisible()


def test_the_shortcuts_and_grids_windows_close_with_the_window(qtbot, asked, main_window):
    window = main_window
    window.help.show_shortcuts()
    window.grids.open()
    help_dialog, grid_dialog = window.help.dialog, window.grids.dialog
    assert help_dialog is not None and grid_dialog is not None
    window.close()
    assert not window.isVisible()
    assert window.help.dialog is None or sip.isdeleted(help_dialog) or not help_dialog.isVisible()
    assert window.grids.dialog is None or sip.isdeleted(grid_dialog) or not grid_dialog.isVisible()


def test_a_kept_dialog_does_not_close_the_others(qtbot, asked, main_window):
    window = main_window
    open_dirty_dialog(qtbot, window)
    window.help.show_shortcuts()
    help_dialog = window.help.dialog
    asked.answer = False
    window.close()
    assert window.isVisible() and help_dialog.isVisible()  # the user may still change their mind
    asked.answer = True
    window.close()
    assert not window.isVisible() and not help_dialog.isVisible()


@pytest.mark.parametrize("tab", ["text", "summary", "diff"])
def test_closing_cancels_the_reads_of_the_open_tabs(qtbot, main_window, demo_project, tab):
    window, cancelled = main_window, []
    scf = demo_project / "02_scf" / "scf.out"
    if tab == "text":
        window.open_file(scf)
        viewer = window.workspace.widget_for(str(scf)) or window.workspace.current()
    elif tab == "summary":
        window.open_summary(scf)
        viewer = window.workspace.widget_for(f"summary:{scf}")
    else:
        other = demo_project / "02_scf" / "other.in"
        other.write_text(AL_SCF.read_text())
        first = demo_project / "02_scf" / "scf.in"
        first.write_text(AL_SCF.read_text())
        window.compare_inputs(first, other)
        viewer = window.workspace.current()
    assert viewer is not None
    viewer._task = SimpleNamespace(cancel=lambda: cancelled.append(tab))
    window.close()
    assert cancelled == [tab]


def test_closing_stops_the_folder_walk_and_the_derived_scf(qtbot, main_window):
    window, gate = main_window, threading.Event()
    window.command_palette._ensure_index()
    stop = window.command_palette._stop
    assert stop is not None
    window.derive._tasks.submit("scf:x", gate.wait, 10)
    assert window.derive._tasks.active("scf:x") is not None
    try:
        window.close()
        assert stop.is_set() and not window.command_palette.indexing
        assert window.derive._tasks.active("scf:x") is None
    finally:
        gate.set()


# -- the process leaves ---------------------------------------------------------------------------
class FakePool:
    def __init__(self, drained: bool):
        self.drained, self.waited = drained, []

    def waitForDone(self, ms: int) -> bool:
        self.waited.append(ms)
        return self.drained

    def activeThreadCount(self) -> int:
        return 2


class FakeLock:
    def __init__(self, events):
        self.events = events

    def unlock(self) -> None:
        self.events.append("unlock")


def test_finish_returns_the_code_when_the_pool_drains():
    exits = []
    pool = FakePool(True)
    assert app.finish(3, pool, None, None, exit_now=exits.append) == 3
    assert pool.waited == [app.POOL_WAIT_MS] and exits == []


def test_finish_leaves_at_once_when_a_worker_will_not_stop(caplog):
    events = []
    report = ShutdownReport(900, ["sync"], ["exportações"])
    with caplog.at_level(logging.ERROR, logger="qe_studio"):
        code = app.finish(
            0,
            FakePool(False),
            FakeLock(events),
            report,
            exit_now=lambda c: events.append(("exit", c)),
        )
    assert events == ["unlock", ("exit", 0)]  # the lock is released before leaving
    assert code == 0
    assert "2 tarefa(s) ainda rodando" in caplog.text and "exportações" in caplog.text


def test_finish_with_a_real_pool_that_has_a_stuck_task(monkeypatch):
    release, exits = threading.Event(), []
    monkeypatch.setattr(app, "POOL_WAIT_MS", 50)
    pool = QThreadPool()
    run_task(release.wait, 10, pool=pool)
    try:
        app.finish(0, pool, None, None, exit_now=exits.append)
        assert exits == [0]
    finally:
        release.set()
        pool.waitForDone(5000)
