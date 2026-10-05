"""Per-user application directories (no Qt dependency so core stays testable headless)."""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = "qe-studio"


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_DIR


def cache_dir() -> Path:
    if sys.platform == "win32":
        return data_dir() / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_DIR


def log_path() -> Path:
    """The rotating application log (``setup_logging``; "Ajuda ▸ Abrir log" opens it)."""
    return cache_dir() / "qe_studio.log"


def lock_path() -> Path:
    """The file the running app locks, so a second instance can tell (``ui/app.py``)."""
    return data_dir() / "lain.lock"


def _new_temp(path: Path) -> tuple[int, Path]:
    """Create ``.<name>.<pid>.<token>.tmp`` next to ``path`` (never an existing file) and open it.
    ``0o666`` leaves the mode to the umask, like ``write_text`` did: a ``mkstemp`` file is ``0600``
    and ``os.replace`` would carry that into every ``.plot`` and store file."""
    while True:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            return os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666), tmp
        except FileExistsError:
            continue


def _sync_dir(folder: Path) -> None:
    """Best effort: make the rename itself durable. Not on Windows (a folder cannot be opened)."""
    if sys.platform == "win32":
        return
    with contextlib.suppress(OSError):
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so a reader (or a crash) sees the old file or the whole new one.

    The temporary file is unique (two threads or two instances writing the same target never share
    it), is flushed to disk before ``os.replace`` and is removed when anything fails (spec 27-3 R4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = _new_temp(path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _sync_dir(path.parent)


def set_aside_corrupt(path: Path) -> Path:
    """Rename an unreadable data file to ``<name>.corrompido-<date>`` (a counter when that exists)
    and return the copy. OSError when it cannot be renamed: the caller must then not overwrite it."""
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    copy = path.with_name(f"{path.name}.corrompido-{stamp}")
    n = 1
    while copy.exists():
        n += 1
        copy = path.with_name(f"{path.name}.corrompido-{stamp}-{n}")
    path.rename(copy)
    return copy
