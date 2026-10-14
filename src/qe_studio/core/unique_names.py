"""Names that never overwrite (spec 24 R2): ``name``, then ``name_1``, ``name_2``…

Folders (spec 25 R7) always get the number at the end of the name: ``bandas_Al.v2_1``.

The figure export keeps its own ``_2``-first versions (``plotting.export.next_free_stem``).
"""

from __future__ import annotations

import os
from collections.abc import Callable
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


def _create(path: Path, first: int, fill: Callable[[int], None]) -> Path:
    """The loop of ``write_new`` and ``write_new_bytes``: create the first free version of ``path``
    exclusively (``O_EXCL``, what ``open(…, "x")`` does) and let ``fill`` write to its descriptor.
    A write that fails removes the file it created."""
    while True:
        target = next_free(path, first)
        try:
            fd = os.open(target, _EXCLUSIVE, 0o666)
        except FileExistsError:
            continue
        try:
            fill(fd)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target


def write_new(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` or its first free ``_N`` version and return where it went.

    The file is created exclusively (``O_EXCL``, what ``open(…, "x")`` does), so a name taken in
    the meantime moves on to the next one instead of being overwritten. Line ends are written as
    they are in ``text``. A write that fails removes the file it created."""

    def fill(fd: int) -> None:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    return _create(path, 1, fill)


def write_new_bytes(path: Path, data: bytes, first: int = 1) -> Path:
    """``write_new`` for bytes (an image). The numbered versions start at ``_<first>``: the figures
    of the plots use ``first=2`` (``name``, ``name_2``, ``name_3``…)."""

    def fill(fd: int) -> None:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    return _create(path, first, fill)


def next_free_dir(path: Path) -> Path:
    """``path`` or its first free ``<name>_N`` (N from 1), the number always at the end of the
    name. Creates nothing (the preview of ``make_new_dir``)."""
    if not _taken(path):
        return path
    return next(
        candidate for n in count(1) if not _taken(candidate := path.with_name(f"{path.name}_{n}"))
    )


def make_new_dir(path: Path) -> Path:
    """Create ``path`` or its first free ``<name>_N`` and return it. ``mkdir`` with
    ``exist_ok=False`` in a loop: a folder (or file) that appears in the meantime is never reused,
    the next name is tried instead. The parent must exist."""
    while True:
        target = next_free_dir(path)
        try:
            target.mkdir()
        except FileExistsError:
            continue
        return target
