"""Names that never overwrite (spec 24 R2): ``name``, then ``name_1``, ``name_2``…

The figure export keeps its own ``_2``-first versions (``plotting.export.next_free_stem``).
"""

from __future__ import annotations

import os
from itertools import count
from pathlib import Path

_EXCLUSIVE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)


def _taken(path: Path) -> bool:
    return os.path.lexists(path)  # a broken symlink is taken too


def suffixed(path: Path, number: int) -> Path:
    """``a/b.in`` → ``a/b_<number>.in``; a folder (``path`` is one, or has no suffix) gets the
    number at the end of its name."""
    if path.is_dir() or not path.suffix:
        return path.with_name(f"{path.name}_{number}")
    return path.with_name(f"{path.stem}_{number}{path.suffix}")


def next_free(path: Path, first: int = 1) -> Path:
    """``path`` if nothing is there, else the first free ``_N`` version from ``first``. Creates
    nothing: between this and the write another process may take the name (``write_new``)."""
    if not _taken(path):
        return path
    return next(candidate for n in count(first) if not _taken(candidate := suffixed(path, n)))


def write_new(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` or its first free ``_N`` version and return where it went.

    The file is created exclusively (``O_EXCL``, what ``open(…, "x")`` does), so a name taken in
    the meantime moves on to the next one instead of being overwritten. Line ends are written as
    they are in ``text``. A write that fails removes the file it created."""
    while True:
        target = next_free(path)
        try:
            fd = os.open(target, _EXCLUSIVE, 0o666)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
