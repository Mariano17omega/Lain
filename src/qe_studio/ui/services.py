"""Background calculation detection feeding the explorer badges."""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from ..core.calculations import DetectionResult
from ..core.detection import FolderMemory, detect_folder
from ..core.sniff import FileSniff, SniffCache


class _Signals(QObject):
    done = pyqtSignal(str, object)


class _DetectTask(QRunnable):
    def __init__(self, folder: Path, sniff: SniffCache, memory: FolderMemory | None):
        super().__init__()
        self.folder, self.sniff, self.memory = folder, sniff, memory
        self.signals = _Signals()

    def run(self) -> None:
        try:
            results = detect_folder(self.folder, sniff=self.sniff.sniff, memory=self.memory)
        except Exception:  # never let a worker exception take the app down
            results = []
        self.signals.done.emit(str(self.folder), results)


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
        self._pending: dict[str, _DetectTask] = {}
        self._finished: list[_DetectTask] = []

    def results(self, folder: Path) -> list[DetectionResult] | None:
        """Cached results, scheduling detection on a miss (returns None meanwhile)."""
        key = str(folder)
        with self._lock:
            if key in self._results:
                return self._results[key]
        self.request(Path(folder))
        return None

    def request(self, folder: Path) -> None:
        key = str(folder)
        if key in self._pending:
            return
        task = _DetectTask(Path(folder), self.sniff_cache, self.memory)
        task.signals.done.connect(self._on_done)
        self._pending[key] = task
        self._pool.start(task)

    def detect_now(self, folder: Path) -> list[DetectionResult]:
        """Synchronous detection (explicit user action), refreshing the cache."""
        results = detect_folder(Path(folder), sniff=self.sniff_cache.sniff, memory=self.memory)
        with self._lock:
            self._results[str(folder)] = results
        self.detected.emit(str(folder))
        return results

    def file_sniff(self, path: Path) -> FileSniff | None:
        return self.sniff_cache.peek(Path(path))

    def invalidate(self, folder: Path | None = None) -> None:
        with self._lock:
            if folder is None:
                self._results.clear()
            else:
                prefix = str(folder)
                for key in [k for k in self._results if k == prefix or k.startswith(prefix + "/")]:
                    del self._results[key]
        if folder is None:
            self.sniff_cache.clear()
        else:
            self.sniff_cache.invalidate(Path(folder))

    def wait(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)

    def _on_done(self, folder: str, results: list[DetectionResult]) -> None:
        # Drop the task on the next loop turn: this slot runs on its own signal object.
        task = self._pending.pop(folder, None)
        if task is not None:
            self._finished.append(task)
            QTimer.singleShot(0, self._finished.clear)
        with self._lock:
            self._results[folder] = results
        self.detected.emit(folder)
