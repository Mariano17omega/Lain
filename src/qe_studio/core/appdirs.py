"""Per-user application directories (no Qt dependency so core stays testable headless)."""

from __future__ import annotations

import os
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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
