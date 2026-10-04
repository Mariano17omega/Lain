"""Background calculation detection feeding the explorer badges."""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from ..core.calculations import DetectionResult
from ..core.detection import detect_folder
from ..core.folder_memory import FolderMemory
from ..core.sniff import FileSniff, SniffCache
from ..core.tasks import TaskGroup


def _detect(folder: Path, sniff: SniffCache, memory: FolderMemory | None) -> list[DetectionResult]:
    try:
        return detect_folder(folder, sniff=sniff.sniff, memory=memory)
    except Exception:  # never let a worker exception take the app down
        return []


def _within(key: str, folder: Path | None) -> bool:
    return folder is None or Path(key).is_relative_to(folder)


def _affected(key: str, folder: Path | None) -> bool:
    """Detection that may change with ``folder``'s files: inside it, or a sibling folder
    (``infer_from_neighbours`` takes the SCF output from sibling ``*scf*`` folders)."""
    if folder is None:
        return True
    return _within(key, folder) or Path(key).parent == Path(folder).parent


class DetectionService(QObject):
    """Caches ``detect_folder`` per folder; computes misses in a small thread pool."""

    detected = pyqtSignal(str)

    def __init__(self, memory: FolderMemory | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.memory = memory
        self.sniff_cache = SniffCache()
        # F5 drops every sniff, not just those of deleted files (``ui.paranoid_refresh``).
        self.paranoid_refresh = False
        self._pool = QThreadPool()  # no Qt parent: see core/tasks.py, "private pools"
        self._pool.setMaxThreadCount(2)
        self._lock = threading.Lock()
        self._results: dict[str, list[DetectionResult]] = {}
        self._tasks = TaskGroup(self._pool)  # by folder: the task whose result counts

    def results(self, folder: Path) -> list[DetectionResult] | None:
        """Cached results, scheduling detection on a miss (returns None meanwhile)."""
        key = str(folder)
        with self._lock:
            if key in self._results:
                return self._results[key]
        self.request(Path(folder))
        return None

    def peek_results(self, folder: Path) -> list[DetectionResult] | None:
        """Cached results only: never schedules detection (filters run for every row)."""
        with self._lock:
            return self._results.get(str(folder))

    def request(self, folder: Path, fresh: bool = False) -> None:
        """Schedule detection; ``fresh`` jumps the queue and supersedes a task already running."""
        key = str(folder)
        if self._tasks.active(key) is not None and not fresh:
            return
        self._tasks.submit(
            key,
            _detect,
            Path(folder),
            self.sniff_cache,
            self.memory,
            on_done=self._on_done,
            priority=1 if fresh else 0,
        )

    def detect_now(self, folder: Path) -> list[DetectionResult]:
        """Synchronous detection refreshing the cache (blocks: scripts and tests only)."""
        key = str(folder)
        results = detect_folder(Path(folder), sniff=self.sniff_cache.sniff, memory=self.memory)
        self._tasks.cancel(key)  # a task started earlier must not overwrite this
        with self._lock:
            self._results[key] = results
        self.detected.emit(key)
        return results

    def file_sniff(self, path: Path) -> FileSniff | None:
        return self.sniff_cache.peek(Path(path))

    def invalidate(self, folder: Path | None = None) -> None:
        """Forget ``folder``: its sniffs, and the detection of the folders its files can affect.

        For the whole project (None, F5) every detection is redone, but the sniffs of files that
        still exist are kept: each is checked against the file's (mtime, size) when used, so
        unchanged files are not read again (spec 14 R4). ``paranoid_refresh`` drops them all.
        """
        with self._lock:
            for key in [k for k in self._results if _affected(k, folder)]:
                del self._results[key]
        if folder is None and self.paranoid_refresh:
            self.sniff_cache.clear()
        elif folder is None:
            self.sniff_cache.prune()
        else:
            self.sniff_cache.invalidate(Path(folder))
        # Running tasks may have read the old files: start over, their results are dropped.
        for key in [k for k in self._tasks.active_keys() if _affected(str(k), folder)]:
            self.request(Path(str(key)), fresh=True)

    def wait(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)

    def shutdown(self, msecs: int = 2000) -> bool:
        """Skip the queued tasks and wait for the running ones (window close).

        The pool's destructor waits for every task without a time limit, so none may be left
        queued behind a slow network mount.
        """
        return self._tasks.shutdown(msecs)

    def _on_done(self, key: str, results: list[DetectionResult]) -> None:
        with self._lock:
            self._results[key] = results
        self.detected.emit(key)
