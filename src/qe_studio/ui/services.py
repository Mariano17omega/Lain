"""Background calculation detection feeding the explorer badges."""

from __future__ import annotations

import itertools
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from ..core.calculations import DetectionResult
from ..core.detection import FolderMemory, detect_folder
from ..core.sniff import FileSniff, SniffCache


class _Signals(QObject):
    done = pyqtSignal(int, object)  # task token, results


class _DetectTask(QRunnable):
    def __init__(self, token: int, folder: Path, sniff: SniffCache, memory: FolderMemory | None):
        super().__init__()
        self.token, self.folder, self.sniff, self.memory = token, folder, sniff, memory
        self.signals = _Signals()

    def run(self) -> None:
        try:
            results = detect_folder(self.folder, sniff=self.sniff.sniff, memory=self.memory)
        except Exception:  # never let a worker exception take the app down
            results = []
        self.signals.done.emit(self.token, results)


def _within(key: str, folder: Path | None) -> bool:
    return folder is None or Path(key).is_relative_to(folder)


class DetectionService(QObject):
    """Caches ``detect_folder`` per folder; computes misses in a small thread pool."""

    detected = pyqtSignal(str)

    def __init__(self, memory: FolderMemory | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.memory = memory
        self.sniff_cache = SniffCache()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._lock = threading.Lock()
        self._results: dict[str, list[DetectionResult]] = {}
        self._tokens = itertools.count()
        self._tasks: dict[int, _DetectTask] = {}  # running tasks (keeps their signals alive)
        self._pending: dict[str, int] = {}  # folder → token of the task whose result counts
        self._finished: list[_DetectTask] = []

    def results(self, folder: Path) -> list[DetectionResult] | None:
        """Cached results, scheduling detection on a miss (returns None meanwhile)."""
        key = str(folder)
        with self._lock:
            if key in self._results:
                return self._results[key]
        self.request(Path(folder))
        return None

    def request(self, folder: Path, fresh: bool = False) -> None:
        """Schedule detection; ``fresh`` jumps the queue and supersedes a task already running."""
        key = str(folder)
        if key in self._pending and not fresh:
            return
        token = next(self._tokens)
        task = _DetectTask(token, Path(folder), self.sniff_cache, self.memory)
        task.signals.done.connect(self._on_done)
        self._tasks[token] = task
        self._pending[key] = token
        self._pool.start(task, 1 if fresh else 0)

    def detect_now(self, folder: Path) -> list[DetectionResult]:
        """Synchronous detection refreshing the cache (blocks: scripts and tests only)."""
        key = str(folder)
        results = detect_folder(Path(folder), sniff=self.sniff_cache.sniff, memory=self.memory)
        self._pending.pop(key, None)  # a task started earlier must not overwrite this
        with self._lock:
            self._results[key] = results
        self.detected.emit(key)
        return results

    def file_sniff(self, path: Path) -> FileSniff | None:
        return self.sniff_cache.peek(Path(path))

    def invalidate(self, folder: Path | None = None) -> None:
        with self._lock:
            for key in [k for k in self._results if _within(k, folder)]:
                del self._results[key]
        if folder is None:
            self.sniff_cache.clear()
        else:
            self.sniff_cache.invalidate(Path(folder))
        # Running tasks may have read the old files: start over, their results are dropped.
        for key in [k for k in self._pending if _within(k, folder)]:
            self.request(Path(key), fresh=True)

    def wait(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)

    def _on_done(self, token: int, results: list[DetectionResult]) -> None:
        # Drop the task on the next loop turn: this slot runs on its own signal object.
        task = self._tasks.pop(token, None)
        if task is None:
            return
        self._finished.append(task)
        QTimer.singleShot(0, self._finished.clear)
        key = str(task.folder)
        if self._pending.get(key) != token:
            return  # superseded (invalidated or refreshed) while it ran
        del self._pending[key]
        with self._lock:
            self._results[key] = results
        self.detected.emit(key)
