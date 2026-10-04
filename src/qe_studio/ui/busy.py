"""Local busy indicator (spec 15 R2): the status bar spinner instead of a global busy cursor."""

from __future__ import annotations

import itertools

from .widgets.bars import StatusBar


class BusyTracker:
    """What runs now, by name. The spinner shows the latest label while any is left and hides
    when none is: no set/restore pairs to keep balanced, and ending a name twice is harmless."""

    def __init__(self, status: StatusBar):
        self.status = status
        self._running: dict[str, tuple[int, str]] = {}  # name → (order, label)
        self._order = itertools.count()

    @property
    def labels(self) -> list[str]:
        """Labels of what runs, oldest first."""
        return [label for _order, label in sorted(self._running.values())]

    def begin(self, name: str, label: str) -> None:
        self._running[name] = (next(self._order), label)
        self.status.set_busy(label)

    def end(self, name: str) -> None:
        if self._running.pop(name, None) is not None:
            labels = self.labels
            self.status.set_busy(labels[-1] if labels else None)
