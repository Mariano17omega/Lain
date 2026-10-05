"""One way to run work off the GUI thread (spec 15 R1).

``run_task(fn, *args, on_done=..., on_error=...)`` runs ``fn`` in a ``QThreadPool`` (the global one
unless given) and calls back on the GUI thread. ``TaskGroup`` keys tasks: a new task for a key
supersedes the previous one, whose result is then dropped.

Every result goes through one dispatcher object that lives on the GUI thread: the worker emits its
signal with the task handle and the queued connection delivers it on a later turn of the event loop.
There is no signal object per task, so nothing must be kept alive until its slot returns, and the
runnables are deleted by their pool (``autoDelete``; PyQt hands their ownership to the pool).

Callbacks should be bound methods (CLAUDE.md). When the receiver is a ``QObject`` only a weak
reference to it is kept and its destruction cancels the task: a closed tab is neither kept alive by
its read nor called back with the result.

Exception: ``core/sync/monitor.py`` probes in daemon threads, not here. A probe can block in a DNS
lookup far beyond its connect timeout, and a pool waits for its running tasks, without a time limit,
when it is destroyed.

Private pools (a ``QThreadPool`` of the caller's, for a thread limit or an order) have no Qt
parent. A child pool is destroyed inside its parent's C++ destructor, which may run with the GIL
held (the parent's wrapper collected by Python), and the pool's destructor waits for its running
tasks, which need the GIL to finish: a deadlock. A parentless pool goes with its Python wrapper,
whose destructor releases the GIL. Owners still call ``TaskGroup.shutdown`` when they close.

This module and the sync controller and monitor are the only ``core`` modules that use Qt.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import weakref
from collections.abc import Callable, Hashable
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, pyqtSignal

from . import cancel

log = logging.getLogger(__name__)


class _Callback:
    """A callback, held weakly when it is a bound method of a ``QObject``."""

    def __init__(self, fn: Callable):
        receiver = getattr(fn, "__self__", None)
        if isinstance(receiver, QObject):
            self._weak: weakref.WeakMethod | None = weakref.WeakMethod(fn)  # type: ignore[arg-type]
            self._strong: Callable | None = None
            self._receiver = weakref.ref(receiver)
        else:
            self._weak, self._strong, self._receiver = None, fn, None

    def receiver_alive(self) -> QObject | None:
        receiver = self._receiver() if self._receiver is not None else None
        return None if receiver is None or sip.isdeleted(receiver) else receiver

    def resolve(self) -> Callable | None:
        if self._strong is not None:
            return self._strong
        fn = self._weak() if self._weak is not None else None
        return fn if fn is not None and self.receiver_alive() is not None else None


class TaskHandle:
    """A submitted task. ``fn`` may stop early with ``core.cancel.check()`` (it sees this handle
    through a thread-local); its result is dropped anyway."""

    def __init__(self, key: Hashable | None = None):
        self.key = key
        self._cancelled = False
        self._started = False
        self._finished = threading.Event()  # set by the worker once run() is over
        self._result: Any = None
        self._error: Exception | None = None
        self._on_done: _Callback | None = None
        self._on_error: _Callback | None = None
        self._group: TaskGroup | None = None
        self._watched: list[weakref.ref[QObject]] = []  # weak: the task must not keep them alive

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def started(self) -> bool:
        return self._started

    @property
    def done(self) -> bool:
        """The worker is over: ``fn`` returned, raised, or was skipped because cancelled."""
        return self._finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the worker is over (scripts, tests and shutdown only); False on timeout."""
        return self._finished.wait(timeout)

    # -- GUI thread ------------------------------------------------------------------------------
    def _watch(self) -> None:
        """A receiver that is destroyed cancels the task."""
        for callback in (self._on_done, self._on_error):
            receiver = callback.receiver_alive() if callback is not None else None
            if receiver is not None and all(ref() is not receiver for ref in self._watched):
                receiver.destroyed.connect(self.cancel)
                self._watched.append(weakref.ref(receiver, self._on_receiver_collected))

    def _on_receiver_collected(self, _ref: weakref.ref) -> None:
        # A receiver without a C++ parent dies with its Python wrapper: same as destroyed.
        self._cancelled = True

    def _unwatch(self) -> None:
        for ref in self._watched:
            receiver = ref()
            if receiver is not None and not sip.isdeleted(receiver):
                with contextlib.suppress(TypeError):  # already disconnected
                    receiver.destroyed.disconnect(self.cancel)
        self._watched = []

    def _deliver(self) -> None:
        group, self._group = self._group, None
        if group is not None:
            group._release(self)
        self._unwatch()
        result, error = self._result, self._error
        self._result = self._error = None  # the handle may outlive its result (a widget's _task)
        if self._cancelled:
            return
        keyed = group is not None
        if error is not None:
            callback = self._on_error.resolve() if self._on_error is not None else None
            if callback is not None:
                callback(*((self.key, error) if keyed else (error,)))
            elif self._on_error is None:
                log.error("background task failed", exc_info=error)
            return
        callback = self._on_done.resolve() if self._on_done is not None else None
        if callback is not None:
            callback(*((self.key, result) if keyed else (result,)))


class _Dispatcher(QObject):
    """Lives on the GUI thread; workers emit ``deliver`` and the slot runs there."""

    deliver = pyqtSignal(object)  # TaskHandle

    def __init__(self) -> None:
        super().__init__()
        self.deliver.connect(self._on_deliver)

    def _on_deliver(self, handle: TaskHandle) -> None:
        handle._deliver()


_DISPATCHER: _Dispatcher | None = None


def _dispatcher() -> _Dispatcher:
    global _DISPATCHER
    if QCoreApplication.instance() is None:
        raise RuntimeError("background tasks need a QApplication")
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("background tasks are started from the GUI thread")
    if _DISPATCHER is None or sip.isdeleted(_DISPATCHER):
        _DISPATCHER = _Dispatcher()
    return _DISPATCHER


class _Runnable(QRunnable):
    def __init__(
        self, handle: TaskHandle, fn: Callable, args: tuple, kwargs: dict, dispatcher: _Dispatcher
    ):
        super().__init__()
        self.handle, self.dispatcher = handle, dispatcher
        self.fn: Callable | None = fn
        self.args, self.kwargs = args, kwargs

    def run(self) -> None:
        handle = self.handle
        try:
            handle._started = True  # before reading the flag: see TaskGroup.shutdown
            if not handle._cancelled and self.fn is not None:
                try:
                    with cancel.bind(handle):
                        handle._result = self.fn(*self.args, **self.kwargs)
                except cancel.Cancelled:  # the task saw its own cancellation (``cancel.check()``)
                    handle._cancelled = True  # never a result or an error
                except Exception as exc:  # reported on the GUI thread, never lost in the worker
                    handle._error = exc
        finally:
            self.fn, self.args, self.kwargs = None, (), {}
            # RuntimeError: the interpreter is exiting and nobody is left to call back.
            with contextlib.suppress(RuntimeError):
                self.dispatcher.deliver.emit(handle)
            handle._finished.set()


def _start(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    on_done: Callable | None,
    on_error: Callable | None,
    pool: QThreadPool | None,
    priority: int,
    key: Hashable | None = None,
    group: TaskGroup | None = None,
) -> TaskHandle:
    dispatcher = _dispatcher()
    handle = TaskHandle(key)
    handle._group = group
    handle._on_done = _Callback(on_done) if on_done is not None else None
    handle._on_error = _Callback(on_error) if on_error is not None else None
    handle._watch()
    target = pool if pool is not None else QThreadPool.globalInstance()
    assert target is not None
    target.start(_Runnable(handle, fn, args, kwargs, dispatcher), priority)
    return handle


def run_task(
    fn: Callable,
    *args: Any,
    on_done: Callable | None = None,
    on_error: Callable | None = None,
    pool: QThreadPool | None = None,
    priority: int = 0,
    **kwargs: Any,
) -> TaskHandle:
    """Run ``fn(*args, **kwargs)`` in ``pool``; then ``on_done(result)`` or ``on_error(exc)`` on
    the GUI thread, unless the task was cancelled or the callback's receiver is gone. Without
    ``on_error`` the exception is logged."""
    return _start(fn, args, kwargs, on_done, on_error, pool, priority)


class TaskGroup:
    """Tasks by key: submitting for a key cancels the task already there.

    Callbacks get the key first: ``on_done(key, result)``, ``on_error(key, exc)``. A pool passed
    in is the group's own: ``shutdown`` also drops its queued tasks.
    """

    def __init__(self, pool: QThreadPool | None = None):
        self._pool = pool
        self._handles: dict[Hashable, TaskHandle] = {}  # the task whose result counts, per key
        self._live: set[TaskHandle] = set()  # every task whose worker has not reported yet

    def submit(
        self,
        key: Hashable,
        fn: Callable,
        *args: Any,
        on_done: Callable | None = None,
        on_error: Callable | None = None,
        priority: int = 0,
        **kwargs: Any,
    ) -> TaskHandle:
        self.cancel(key)
        handle = _start(fn, args, kwargs, on_done, on_error, self._pool, priority, key, self)
        self._handles[key] = handle
        self._live.add(handle)
        return handle

    def active(self, key: Hashable) -> TaskHandle | None:
        """The task of ``key`` that has not been delivered or cancelled yet."""
        return self._handles.get(key)

    def active_keys(self) -> list[Hashable]:
        return list(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def cancel(self, key: Hashable) -> None:
        handle = self._handles.pop(key, None)
        if handle is not None:
            handle.cancel()

    def cancel_all(self) -> None:
        for key in list(self._handles):
            self.cancel(key)

    def wait(self, timeout_ms: int = 2000) -> bool:
        """Block until every task that was not cancelled is over, queued ones too (their results
        still arrive); False on timeout. For the rare step that must not overlap them, like
        renaming the folder an export writes into, or closing the window."""
        deadline = time.monotonic() + timeout_ms / 1000
        for handle in list(self._live):
            if not handle.cancelled and not handle.wait(max(0.0, deadline - time.monotonic())):
                return False
        return True

    def shutdown(self, timeout_ms: int = 2000) -> bool:
        """Cancel every task and wait for those already running (window close).

        A pool's destructor waits for all its tasks without a time limit, so the queued ones of the
        group's own pool are dropped; queued ones of the global pool skip their work when they start.
        """
        self.cancel_all()
        for handle in self._live:
            handle.cancel()
        if self._pool is not None:
            self._pool.clear()
        deadline = time.monotonic() + timeout_ms / 1000
        for handle in list(self._live):
            # cancel() came first: a task that was not started yet skips its work when it starts
            if handle.started and not handle.wait(max(0.0, deadline - time.monotonic())):
                return False
        return True

    def _release(self, handle: TaskHandle) -> None:
        self._live.discard(handle)
        if self._handles.get(handle.key) is handle:
            del self._handles[handle.key]


__all__ = ["TaskGroup", "TaskHandle", "run_task"]
