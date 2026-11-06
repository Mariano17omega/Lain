"""Cooperative cancellation of background work (spec 27-4 R1).

``core/tasks.py`` binds the running task to its worker thread; a long loop in ``core`` calls
``check()`` every so often and a task that was cancelled stops there with ``Cancelled``, which
the task runner treats as a cancellation (no callback, no error). Outside a task ``check()`` does
nothing, so the parsers stay plain functions that scripts and tests call directly.

Qt-free on purpose: ``core/qe`` parsers import this, never ``core/tasks.py``.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from itertools import islice
from typing import Protocol, TypeVar

T = TypeVar("T")

CHECK_EVERY_LINES = 10_000  # how often a line loop looks at the flag: never per line


class Cancelled(Exception):
    """The running task was cancelled; raised by ``check()`` to unwind its work."""


class Token(Protocol):
    @property
    def cancelled(self) -> bool: ...


_state = threading.local()


@contextmanager
def bind(token: Token) -> Iterator[None]:
    """Make ``token`` the current task of this thread (``core/tasks.py`` only)."""
    previous = getattr(_state, "token", None)
    _state.token = token
    try:
        yield
    finally:
        _state.token = previous


def is_cancelled() -> bool:
    token: Token | None = getattr(_state, "token", None)
    return token is not None and token.cancelled


def check() -> None:
    """Raise ``Cancelled`` if the task running in this thread was cancelled; else do nothing."""
    if is_cancelled():
        raise Cancelled


def checked(items: Iterable[T], every: int = CHECK_EVERY_LINES) -> Iterator[T]:
    """``items``, calling ``check()`` before each batch of ``every`` of them (and so at the start).

    Batches rather than a counter: a line loop pays for the check once per batch, not a modulo
    per line (the parse of a big relax output is 10 % slower this way, 30 % with a counter).
    """
    iterator = iter(items)
    while batch := list(islice(iterator, every)):
        check()
        yield from batch
