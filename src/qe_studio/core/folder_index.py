"""Folder index of the command palette (spec 18 R2): every project folder, built in a worker.

Same visibility rule as the panels (``fs_model``): dotted names and ``ui.hidden_dirs`` matches are
skipped and not descended into. Symlinked folders are skipped, which also rules out cycles.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable
from pathlib import Path

from .paths import is_hidden, normalize_patterns

MAX_FOLDERS = 20_000


def list_folders(
    root: Path,
    hidden_dirs: list[str],
    limit: int = MAX_FOLDERS,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[Path]:
    """Folders below ``root`` (not ``root`` itself), absolute and sorted, at most ``limit``.

    Walks breadth first so a project cut at ``limit`` keeps its shallow folders. ``cancelled`` is
    polled between directories; a cancelled walk returns what it has.
    """
    patterns = normalize_patterns(hidden_dirs)
    found: list[Path] = []
    pending = deque([root])
    while pending and len(found) < limit and not cancelled():
        folder = pending.popleft()
        try:
            with os.scandir(folder) as scan:
                entries = sorted(scan, key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or is_hidden(entry.name, patterns):
                continue
            try:
                if entry.is_symlink() or not entry.is_dir():
                    continue
            except OSError:
                continue
            found.append(Path(entry.path))
            pending.append(Path(entry.path))
            if len(found) >= limit:
                break
    return sorted(found)
