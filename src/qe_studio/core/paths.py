"""Folder rules of the file panels: which folders ``ui.hidden_dirs`` hides, the order of names, and
entry counts."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path


def natural_key(text: str) -> list:
    """``run2`` before ``run10``: digit runs compare as numbers, the rest without case."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def normalize_patterns(patterns: list[str]) -> list[str]:
    """``ui.hidden_dirs`` as matched: lowercase, without a trailing ``/`` (``orbitals/``)."""
    return [pattern.rstrip("/").lower() for pattern in patterns]


def is_hidden(name: str, patterns: list[str]) -> bool:
    """Whether a folder named ``name`` matches one of the normalized ``patterns`` (any case)."""
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in patterns)


def count_entries(folder: Path | str) -> int | None:
    """Entries of ``folder`` that the panels show (not the hidden ``.name`` ones); None when it
    cannot be read. Run off the GUI thread: big folders, slow network mounts."""
    try:
        with os.scandir(folder) as entries:
            return sum(1 for entry in entries if not entry.name.startswith("."))
    except OSError:
        return None
