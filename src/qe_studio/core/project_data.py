"""Where the settings of a project root live (spec 48): ``<local_root>/.lain/``.

The four user stores (``FolderMemory``, ``NavigationStore``, ``GridStore``, ``CompoundStore``) keep one
file each in the root's settings folder, so copying the root takes them along and two roots never share
an entry. The folder is hidden (a leading dot: no list, project dropdown or detection shows it), left out
of every rsync run and made only by the first write. A root that cannot hold it (read-only, or a
``.lain`` that is not a writable folder) uses a folder of its own in the user's data dir instead.

This module is the one place that names the folder. Before spec 48 the files lived in ``data_dir()``,
one per user for every root: a store that follows a root imports what is that root's from there once
(``StoreFile.read_legacy``), and never changes the old file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ..i18n import _
from .appdirs import data_dir

log = logging.getLogger(__name__)

PROJECT_DATA_DIR = ".lain"
PROJECT_DATA_EXCLUDE = (
    PROJECT_DATA_DIR + "/"
)  # the rsync pattern of every dry run (core/sync/rsync.py)
FOLDERS_FILE = "folders.json"
GRIDS_FILE = "grids.json"
COMPOUNDS_FILE = "compounds.json"
NAVIGATION_FILE = "navigation.json"
FALLBACK_DIR = "roots"  # data_dir()/roots/<hash>: a root that cannot hold its own folder

NOT_A_FOLDER = _("{folder} não é uma pasta: as configurações do projeto ficam em {fallback}.")
NOT_WRITABLE = _("{folder} não é gravável: as configurações do projeto ficam em {fallback}.")
NO_ROOT = _("nenhuma")


@dataclass(frozen=True)
class Location:
    """The folder of a root's settings; ``fallback`` when it is the one in the data dir, and then
    ``notice`` says why (None when the root is not a folder at all: the first run says so already)."""

    folder: Path
    fallback: bool
    notice: str | None = None


def _absolute(root: Path) -> Path:
    return Path(os.path.abspath(Path(root).expanduser()))


def fallback_folder(root: Path) -> Path:
    """The data dir's folder for ``root``: one per root, named by a hash of its resolved path."""
    digest = hashlib.sha256(str(_absolute(root).resolve()).encode("utf-8")).hexdigest()
    return data_dir() / FALLBACK_DIR / digest[:16]


def _writable(folder: Path) -> bool:
    return os.access(folder, os.W_OK | os.X_OK)


def locate(root: Path) -> Location:
    """Where the settings of ``root`` are kept. Never raises and creates nothing: a missing
    ``.lain`` in a writable root is born at the first write (``atomic_write_text`` makes it)."""
    root = _absolute(root)
    if not root.is_dir():
        return Location(fallback_folder(root), True)
    folder = root / PROJECT_DATA_DIR
    if os.path.lexists(folder):  # a broken symlink too: it can be neither read nor made
        if folder.is_dir() and _writable(folder):
            return Location(folder, False)
        problem, where = (NOT_WRITABLE if folder.is_dir() else NOT_A_FOLDER), folder
    elif _writable(root):
        return Location(folder, False)
    else:
        problem, where = NOT_WRITABLE, root
    fallback = fallback_folder(root)
    return Location(fallback, True, problem.format(folder=where, fallback=fallback))


def describe(root: Path) -> str:
    """The "Configurações do projeto" line of "Sobre": the folder, or ``nenhuma`` without a root."""
    return str(locate(root).folder) if _absolute(root).is_dir() else NO_ROOT


class StoreFile:
    """The file of one store. Fixed when the caller gave its path (the tests, scripts): ``follow``
    changes nothing. Otherwise it is ``data_dir()/<name>`` until a root is set, then the root's
    settings folder, and ``legacy`` names the old per-user file to import from."""

    def __init__(self, name: str, path: Path | None):
        self.name = name
        self.fixed = path is not None
        self.path = Path(path) if path is not None else data_dir() / name
        self.legacy: Path | None = None
        self.notice: str | None = None  # why the settings are in the fallback folder

    def follow(self, root: Path | None) -> bool:
        """Point at the settings folder of ``root``. True when the file changed: the store must
        forget what it read (and wrote nothing pending to the new one)."""
        if self.fixed or root is None:
            return False
        location = locate(root)
        self.notice = location.notice
        path = location.folder / self.name
        if path == self.path:
            return False
        self.path, self.legacy = path, data_dir() / self.name
        return True

    def read_legacy(self) -> object | None:
        """The old per-user file as JSON; None when there is none or it cannot be read. It is not
        this store's file, so an unreadable one is only logged, never set aside."""
        if self.legacy is None:
            return None
        try:
            return json.loads(self.legacy.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log.warning("%s unreadable; nothing imported (%s)", self.legacy, exc)
            return None

    def log_import(self, count: int) -> None:
        if self.legacy is not None:
            log.info("%s: %d items imported from %s", self.path, count, self.legacy)
