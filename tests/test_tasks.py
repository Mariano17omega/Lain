"""The one background-task helper (spec 15 R1): callbacks on the GUI thread, cancellation, groups."""

import threading
import time

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QThreadPool

from qe_studio.core.tasks import TaskGroup, run_task


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.results, self.errors, self.threads = [], [], []

    def done(self, *args):
        self.threads.append(threading.current_thread())
        self.results.append(args)

    def failed(self, *args):
        self.errors.append(args)


def gated(gate: threading.Event, value=None):
    """A task that blocks until the test opens ``gate``."""

    def work():
        gate.wait(5)
        return value

    return work


def test_the_callback_runs_on_the_gui_thread(qtbot):
    receiver = Receiver()
    handle = run_task(lambda a, b: a + b, 2, 3, on_done=receiver.done)
    qtbot.waitUntil(lambda: receiver.results == [(5,)], timeout=5000)
    assert receiver.threads == [threading.main_thread()]
    assert handle.done and not handle.cancelled


def test_errors_reach_on_error(qtbot):
    receiver = Receiver()

    def boom():
        raise ValueError("bad file")

    run_task(boom, on_done=receiver.done, on_error=receiver.failed)
    qtbot.waitUntil(lambda: bool(receiver.errors), timeout=5000)
    (error,) = receiver.errors[0]
    assert isinstance(error, ValueError) and receiver.results == []


def test_an_error_without_on_error_is_logged(qtbot, caplog):
    def boom():
        raise RuntimeError("nobody listens")

    handle = run_task(boom)
    assert handle.wait(5)
    qtbot.waitUntil(lambda: "background task failed" in caplog.text, timeout=5000)


def test_a_cancelled_task_never_calls_back(qtbot):
    receiver = Receiver()
    gate = threading.Event()
    handle = run_task(gated(gate, "late"), on_done=receiver.done)
    qtbot.waitUntil(lambda: handle.started, timeout=5000)
    handle.cancel()
    gate.set()
    assert handle.wait(5)
    qtbot.wait(50)
    assert receiver.results == []


def test_a_task_cancelled_before_it_starts_skips_its_work(qtbot):
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    gate = threading.Event()
    ran = []
    first = run_task(gated(gate), pool=pool)
    qtbot.waitUntil(lambda: first.started, timeout=5000)
    queued = run_task(lambda: ran.append(1), pool=pool)
    queued.cancel()
    gate.set()
    assert pool.waitForDone(5000)
    assert ran == [] and queued.done


def test_a_new_task_of_the_same_key_supersedes_the_previous(qtbot):
    receiver = Receiver()
    group = TaskGroup()
    gate = threading.Event()
    old = group.submit("folder", gated(gate, "old"), on_done=receiver.done)
    new = group.submit("folder", lambda: "new", on_done=receiver.done)
    assert old.cancelled and group.active("folder") is new
    qtbot.waitUntil(lambda: receiver.results == [("folder", "new")], timeout=5000)
    gate.set()
    assert old.wait(5)
    qtbot.wait(50)
    assert receiver.results == [("folder", "new")]
    assert group.active("folder") is None and len(group) == 0


def test_shutdown_waits_for_running_tasks_and_drops_queued_ones(qtbot):
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    group = TaskGroup(pool)
    gate = threading.Event()
    calls = []

    def slow():
        calls.append("slow")
        gate.wait(0.3)
        return "slow"

    running = group.submit("a", slow)
    queued = group.submit("b", lambda: calls.append("queued"))
    qtbot.waitUntil(lambda: running.started, timeout=5000)
    assert group.shutdown(5000)
    assert running.done and calls == ["slow"] and not queued.started


def test_shutdown_reports_a_task_that_outlives_the_timeout(qtbot):
    group = TaskGroup()
    gate = threading.Event()
    handle = group.submit("a", gated(gate))
    qtbot.waitUntil(lambda: handle.started, timeout=5000)
    assert not group.shutdown(50)
    gate.set()
    assert handle.wait(5)


def test_a_deleted_receiver_is_not_called_and_cancels_the_task(qtbot):
    receiver = Receiver()
    gate = threading.Event()
    handle = run_task(gated(gate, "late"), on_done=receiver.done)
    receiver.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert handle.cancelled
    gate.set()
    assert handle.wait(5)
    qtbot.wait(50)


def test_the_receiver_is_held_weakly(qtbot):
    import gc
    import weakref

    gate = threading.Event()
    receiver = Receiver()
    ref = weakref.ref(receiver)
    handle = run_task(gated(gate), on_done=receiver.done)
    del receiver
    gc.collect()
    assert ref() is None and handle.cancelled
    gate.set()
    assert handle.wait(5)
    qtbot.wait(50)


def test_tasks_start_only_from_the_gui_thread(qtbot):
    errors = []

    def start_from_worker():
        try:
            run_task(lambda: None)
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=start_from_worker)
    thread.start()
    thread.join(5)
    assert errors == ["background tasks are started from the GUI thread"]


@pytest.mark.parametrize("cancel_first", [False, True])
def test_the_handle_drops_its_result_after_delivery(qtbot, cancel_first):
    receiver = Receiver()
    handle = run_task(lambda: "x" * 1000, on_done=receiver.done)
    if cancel_first:
        handle.cancel()
    assert handle.wait(5)
    qtbot.wait(50)
    assert handle._result is None
    assert receiver.results == ([] if cancel_first else [("x" * 1000,)])


def test_closing_a_text_viewer_with_a_pending_read(qtbot, tmp_path, monkeypatch):
    from qe_studio.core.text_preview import read_preview
    from qe_studio.ui.theme.manager import ThemeManager
    from qe_studio.ui.widgets import text_viewer

    gate = threading.Event()

    def slow(path, full=False):
        gate.wait(5)
        return read_preview(path, full)

    monkeypatch.setattr(text_viewer, "read_preview", slow)
    path = tmp_path / "scf.in"
    path.write_text("&control\n/\n")
    viewer = text_viewer.TextViewer(path, ThemeManager("dark"))
    loaded = []
    viewer.loaded.connect(lambda: loaded.append(1))
    handle = viewer._task
    qtbot.waitUntil(lambda: handle.started, timeout=5000)
    viewer.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert handle.cancelled
    gate.set()
    assert handle.wait(5)
    qtbot.wait(50)
    assert loaded == []


# -- cooperative cancellation (spec 27-4 R1) -----------------------------------------------------
def test_check_outside_a_task_does_nothing():
    from qe_studio.core import cancel

    cancel.check()
    assert not cancel.is_cancelled()
    assert list(cancel.checked(range(25_000))) == list(range(25_000))


def test_a_task_that_checks_stops_when_cancelled_without_any_callback(qtbot, caplog):
    from qe_studio.core import cancel

    receiver, steps, running = Receiver(), [], threading.Event()

    def loop():
        for step in range(10_000):
            steps.append(step)
            running.set()
            cancel.check()
            time.sleep(0.005)
        return "finished"

    handle = run_task(loop, on_done=receiver.done, on_error=receiver.failed)
    assert running.wait(5)
    handle.cancel()
    assert handle.wait(2)  # the loop ended at its next check, long before 50 s
    qtbot.wait(50)
    assert len(steps) < 10_000 and handle.cancelled
    assert receiver.results == [] and receiver.errors == []
    assert "background task failed" not in caplog.text


def test_a_group_task_cancelled_inside_a_check_never_calls_back(qtbot):
    from qe_studio.core import cancel

    receiver, running = Receiver(), threading.Event()

    def wait_for_cancel():
        running.set()
        while True:
            cancel.check()
            time.sleep(0.002)

    group = TaskGroup()
    group.submit("k", wait_for_cancel, on_done=receiver.done, on_error=receiver.failed)
    assert running.wait(5)
    group.cancel("k")
    assert group.shutdown(2000)  # only returns in time because the task sees the flag
    qtbot.wait(50)
    assert receiver.results == [] and receiver.errors == [] and len(group) == 0


def test_shutdown_ends_a_running_task_that_checks(qtbot):
    from qe_studio.core import cancel

    running, group = threading.Event(), TaskGroup()

    def long_work():
        running.set()
        for _ in range(10_000):
            cancel.check()
            time.sleep(0.005)

    group.submit("k", long_work)
    assert running.wait(5)
    started = time.monotonic()
    assert group.shutdown(5000)
    assert time.monotonic() - started < 2


def test_the_token_is_cleared_when_the_task_is_over(qtbot):
    from qe_studio.core import cancel

    seen = []

    def work():
        seen.append(cancel.is_cancelled())

    handle = run_task(work)
    assert handle.wait(5)
    handle.cancel()  # after the end: nothing a later task on that thread may see

    def next_work():
        seen.append(cancel.is_cancelled())

    handle = run_task(next_work)
    assert handle.wait(5)
    assert seen == [False, False]


def test_a_cancelled_exception_with_the_flag_off_is_still_not_a_result(qtbot):
    from qe_studio.core import cancel

    receiver = Receiver()

    def raises():
        raise cancel.Cancelled

    handle = run_task(raises, on_done=receiver.done, on_error=receiver.failed)
    assert handle.wait(5)
    qtbot.wait(50)
    assert receiver.results == [] and receiver.errors == []
