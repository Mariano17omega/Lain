"""Folder navigation without widgets: the back/forward history and the breadcrumb's arithmetic
(spec 16 R1, R2). The UI (``ui/navigation_controller.py``) feeds it every folder the user visits.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

HISTORY_LIMIT = 50


class Segment(NamedTuple):
    name: str
    path: Path


def breadcrumb_segments(root: Path, folder: Path) -> list[Segment]:
    """One segment per level, from the project (named after ``root``) down to ``folder``.

    A folder outside the project (Lain never shows one) is a single segment with its path.
    """
    root, folder = Path(root), Path(folder)
    if not folder.is_relative_to(root):
        return [Segment(str(folder), folder)]
    segments = [Segment(root.name or str(root), root)]
    path = root
    for part in folder.relative_to(root).parts:
        path = path / part
        segments.append(Segment(part, path))
    return segments


def collapse_count(widths: list[int], available: int, separator: int = 0, ellipsis: int = 0) -> int:
    """How many middle segments to hide behind the "…" button so the row fits ``available`` px.

    ``widths`` are those of every segment, root first. The root and the last segment always stay;
    hiding starts next to the root, so the levels closest to the current folder stay visible.
    ``separator`` is the width of a "›" and ``ellipsis`` the one of the button. When even that
    does not fit, every middle segment is hidden (the caller elides the rest).
    """
    middle = max(len(widths) - 2, 0)
    for hidden in range(middle + 1):
        shown = widths[:1] + widths[1 + hidden :]
        count = len(shown) + (1 if hidden else 0)
        total = sum(shown) + (ellipsis if hidden else 0) + separator * (count - 1)
        if total <= available:
            return hidden
    return middle


def _moved(path: Path, old: Path, new: Path) -> Path:
    return new / path.relative_to(old) if path.is_relative_to(old) else path


def _collapsed(stack: list[Path]) -> list[Path]:
    """``stack`` without a folder repeated right after itself."""
    out: list[Path] = []
    for path in stack:
        if not out or out[-1] != path:
            out.append(path)
    return out


class NavigationHistory:
    """Folders visited: a "back" stack, the current folder and a "forward" stack (browser style).

    Visiting a new folder pushes the current one on "back" and clears "forward"; going back or
    forward moves between the stacks without pushing again. The same folder is never pushed twice
    in a row, and each stack keeps at most ``limit`` folders (the oldest fall off).
    """

    def __init__(self, limit: int = HISTORY_LIMIT):
        self.limit = limit
        self._back: list[Path] = []
        self._forward: list[Path] = []
        self._current: Path | None = None

    @property
    def current(self) -> Path | None:
        return self._current

    @property
    def back_stack(self) -> list[Path]:
        return list(self._back)

    @property
    def forward_stack(self) -> list[Path]:
        return list(self._forward)

    @property
    def can_back(self) -> bool:
        return bool(self._back)

    @property
    def can_forward(self) -> bool:
        return bool(self._forward)

    def clear(self) -> None:
        self._back.clear()
        self._forward.clear()
        self._current = None

    def visit(self, folder: Path) -> None:
        """The user is in ``folder`` now (a no-op when it already is the current one)."""
        folder = Path(folder)
        if folder == self._current:
            return
        if self._current is not None:
            self._push(self._back, self._current)
        self._current = folder
        self._forward.clear()

    def back(
        self, exists: Callable[[Path], bool] = os.path.isdir
    ) -> tuple[Path | None, list[Path]]:
        """Step back to the last folder that still ``exists``: ``(target, skipped)``. ``skipped``
        are the vanished folders passed over, dropped from the history for good; ``target`` is
        None when nothing is left to go back to."""
        return self._step(self._back, self._forward, exists)

    def forward(
        self, exists: Callable[[Path], bool] = os.path.isdir
    ) -> tuple[Path | None, list[Path]]:
        return self._step(self._forward, self._back, exists)

    def rename(self, old: Path, new: Path) -> None:
        """Follow a renamed file or folder: every entry inside ``old`` moves under ``new``."""
        old, new = Path(old), Path(new)
        self._back = _collapsed([_moved(p, old, new) for p in self._back])
        self._forward = _collapsed([_moved(p, old, new) for p in self._forward])
        if self._current is not None:
            self._current = _moved(self._current, old, new)

    def _push(self, stack: list[Path], folder: Path) -> None:
        if not stack or stack[-1] != folder:
            stack.append(folder)
        del stack[: -self.limit]

    def _step(
        self, source: list[Path], other: list[Path], exists: Callable[[Path], bool]
    ) -> tuple[Path | None, list[Path]]:
        skipped: list[Path] = []
        while source:
            target = source.pop()
            if target == self._current:  # left behind by a drop or a rename
                continue
            if exists(target):
                if self._current is not None:
                    self._push(other, self._current)
                self._current = target
                self._forget(skipped)
                return target, skipped
            skipped.append(target)
        self._forget(skipped)
        return None, skipped

    def _forget(self, gone: list[Path]) -> None:
        """Drop vanished folders from both stacks (they may have been visited more than once)."""
        if gone:
            self._back = _collapsed([p for p in self._back if p not in gone])
            self._forward = _collapsed([p for p in self._forward if p not in gone])
