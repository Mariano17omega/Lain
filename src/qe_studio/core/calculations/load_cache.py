"""The datasets ``CalculationModule.load_cached`` keeps (spec 27-4 R2).

Bounded by entry count *and* by bytes (the arrays of a dataset are what is big), loaded once per
key however many threads ask, and emptied by folder: when the project is refreshed, a folder
synced or renamed, and (the big ones) when the tab that shows them closes.

Qt-free; ``cancel.check()`` makes a task that was cancelled stop here instead of loading.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import cancel
from ..sizing import nbytes_of

LOAD_CACHE_SIZE = 8
LOAD_CACHE_BYTES = 256 * 1024 * 1024
CLOSE_DROP_MIN_BYTES = 4 * 1024 * 1024  # a smaller dataset stays: reloading it takes milliseconds
WAIT_POLL_S = 0.1  # how often a thread waiting for another's load looks at its own cancellation


@dataclass
class _Entry:
    dataset: Any
    nbytes: int
    paths: tuple[Path, ...]


@dataclass
class _Flight:
    """A load in progress: the threads that ask for the same key wait for ``done``."""

    done: threading.Event = field(default_factory=threading.Event)


class LoadCache:
    def __init__(self, max_entries: int = LOAD_CACHE_SIZE, max_bytes: int = LOAD_CACHE_BYTES):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._entries: OrderedDict[Hashable, _Entry] = OrderedDict()
        self._flights: dict[Hashable, _Flight] = {}
        self._bytes = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def get_or_load(self, key: Hashable, paths: Iterable[Path], load: Callable[[], Any]) -> Any:
        """The dataset of ``key``, loading it with ``load()`` if it is not here. A second caller
        for a key that is being loaded waits for that load. If it fails or is cancelled, the
        waiter tries on its own (it does not inherit an error that may have been the other's)."""
        while True:
            with self._lock:
                entry = self._entries.get(key)
                if entry is not None:
                    self._entries.move_to_end(key)
                    return entry.dataset
                flight = self._flights.get(key)
                if flight is None:
                    mine = self._flights[key] = _Flight()
            if flight is None:
                return self._load(key, mine, tuple(paths), load)
            while not flight.done.wait(WAIT_POLL_S):
                cancel.check()
            cancel.check()

    def _load(self, key: Hashable, flight: _Flight, paths: tuple[Path, ...], load: Callable) -> Any:
        try:
            cancel.check()
            dataset = load()
            cancel.check()  # the result of a cancelled task is not kept
            self._store(key, _Entry(dataset, nbytes_of(dataset), paths))
            return dataset
        finally:
            with self._lock:
                del self._flights[key]
            flight.done.set()

    def _store(self, key: Hashable, entry: _Entry) -> None:
        if entry.nbytes > self.max_bytes:  # bigger than the whole budget: returned, never kept
            return
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= old.nbytes
            self._entries[key] = entry
            self._bytes += entry.nbytes
            while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                _, oldest = self._entries.popitem(last=False)
                self._bytes -= oldest.nbytes

    def drop(self, under: Path | None = None, *, min_bytes: int = 0) -> int:
        """Forget the entries with a file under ``under`` (all when None) and at least
        ``min_bytes``; how many were dropped."""
        with self._lock:
            doomed = [
                key
                for key, entry in self._entries.items()
                if entry.nbytes >= min_bytes
                and (under is None or any(p.is_relative_to(under) for p in entry.paths))
            ]
            for key in doomed:
                self._bytes -= self._entries.pop(key).nbytes
            return len(doomed)


CACHE = LoadCache()


def drop_cached(under: Path | None = None, *, min_bytes: int = 0) -> int:
    """``LoadCache.drop`` of the app's cache: the datasets of ``CalculationModule.load_cached``."""
    return CACHE.drop(under, min_bytes=min_bytes)
