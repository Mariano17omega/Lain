"""Favorite and recent folders of each project (spec 16 R4).

Stored in the root's settings folder (``navigation.json``, spec 48: ``core/project_data.py``), where
the root's entry is keyed ``"."``, so the file is right wherever the root is copied to. A store given a
path (the tests) keeps one file for every root, keyed by the resolved ``paths.local_root``. Folders are
kept by their path relative to the root, like ``FolderMemory`` (spec 14 R7); folders outside it are
not kept (Lain never shows one).

The store never touches the disk about folders (existence checks are passed in); it reads the
JSON once and writes it on a change: favorites at once, recents when ``flush`` is called (every
visit changes them, the window flushes after a pause and on exit).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from .appdirs import atomic_write_text, set_aside_corrupt
from .project_data import NAVIGATION_FILE, StoreFile

log = logging.getLogger(__name__)

FORMAT_VERSION = 1  # {"version": 1, "projects": {root: {"favorites": [rel], "recents": [rel]}}}
RECENT_LIMIT = 10
ROOT_KEY = "."  # the root's entry in its own file (spec 48)


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def legacy_navigation(data: object, key: str) -> dict:
    """The entry of the root ``key`` (its resolved path) in an old per-user ``navigation.json``, as
    the root's own file holds it: under ``"."`` (spec 48 R3). Nothing for another format."""
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        return {}
    projects = data.get("projects")
    entry = projects.get(key) if isinstance(projects, dict) else None
    if not isinstance(entry, dict):
        return {}
    return {"version": FORMAT_VERSION, "projects": {ROOT_KEY: entry}}


class NavigationStore:
    def __init__(self, path: Path | None = None, root: Path | None = None):
        self._file = StoreFile(NAVIGATION_FILE, path)
        self._root: Path | None = None  # as given: what the visited folders are under
        self._key = ""  # its resolved path: the project's key in the file
        self._projects: dict[str, dict] | None = None
        self._warning: str | None = None
        self._read_only = False  # unreadable and could not be set aside: never overwrite it
        self._dirty = False
        if root is not None:
            self.set_root(root)

    @property
    def path(self) -> Path:
        return self._file.path

    # -- project ---------------------------------------------------------------------------------
    def set_root(self, root: Path) -> None:
        """The project whose favorites and recents are asked for (set again on a config reload).
        What is pending goes to the old file first; another file is read afresh (spec 48 R2.3)."""
        self.flush()
        if self._file.follow(root):
            self._projects, self._warning, self._read_only = None, None, False
        self._root = Path(os.path.abspath(Path(root).expanduser()))
        self._key = str(self._root.resolve()) if self._file.fixed else ROOT_KEY

    def load_warning(self) -> str | None:
        """Read the file now; the message to show if it was corrupt (and set aside)."""
        self._load()
        return self._warning

    def _rel(self, folder: Path) -> str | None:
        """``folder`` relative to the root (POSIX), None when it is outside it."""
        if self._root is None:
            return None
        folder = Path(os.path.abspath(folder))
        return (
            folder.relative_to(self._root).as_posix() if folder.is_relative_to(self._root) else None
        )

    def _abs(self, rel: str) -> Path:
        assert self._root is not None
        return Path(os.path.normpath(self._root / rel))

    # -- file ------------------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if self._projects is not None:
            return self._projects
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = self._imported()
        except (OSError, ValueError) as exc:
            data = self._set_aside(exc)
        if not isinstance(data, dict):
            data = self._set_aside("o conteúdo não é um objeto JSON")
        projects = data.get("projects")
        if data and (data.get("version") != FORMAT_VERSION or not isinstance(projects, dict)):
            self._set_aside(f"versão de formato desconhecida: {data.get('version')!r}")
            projects = None
        self._projects = projects if isinstance(projects, dict) else {}
        return self._projects

    def _imported(self) -> dict:
        """This root's favorites and recents in the old per-user file (spec 48 R3); not written
        until something changes."""
        legacy = self._file.read_legacy()
        if legacy is None or self._root is None:
            return {}
        data = legacy_navigation(legacy, str(self._root.resolve()))
        self._file.log_import(len(data.get("projects", {})))
        return data

    def _set_aside(self, problem: object) -> dict:
        try:
            copy = set_aside_corrupt(self.path)
        except OSError as exc:
            self._read_only = True
            self._warning = (
                f"{self.path.name} ilegível e não pôde ser copiado ({exc.strerror or exc}): "
                "favoritos e recentes desta sessão não serão salvos"
            )
        else:
            self._warning = f"{self.path.name} estava corrompido; cópia salva em {copy}"
        log.warning("%s (%s)", self._warning, problem)
        return {}

    def _entry(self) -> dict:
        assert self._root is not None, "set_root first"
        entry = self._load().setdefault(self._key, {})
        entry["favorites"] = _strings(entry.get("favorites"))
        entry["recents"] = _strings(entry.get("recents"))
        return entry

    def _save(self) -> None:
        self._dirty = False
        if self._read_only:
            return
        data = {"version": FORMAT_VERSION, "projects": self._load()}
        atomic_write_text(self.path, json.dumps(data, indent=1, ensure_ascii=False))

    def flush(self) -> None:
        """Write what changed since the last save (the recents)."""
        if self._dirty:
            self._save()

    # -- favorites -------------------------------------------------------------------------------
    def favorites(self) -> list[Path]:
        return [self._abs(rel) for rel in self._entry()["favorites"]] if self._root else []

    def is_favorite(self, folder: Path) -> bool:
        rel = self._rel(folder)
        return rel is not None and rel in self._entry()["favorites"]

    def add_favorite(self, folder: Path) -> bool:
        """Saved at once. False when it already was one, or is outside the project."""
        rel = self._rel(folder)
        if rel is None or rel in (favorites := self._entry()["favorites"]):
            return False
        favorites.append(rel)
        self._save()
        return True

    def remove_favorite(self, folder: Path) -> bool:
        rel = self._rel(folder)
        if rel is None or rel not in (favorites := self._entry()["favorites"]):
            return False
        favorites.remove(rel)
        self._save()
        return True

    # -- recents ---------------------------------------------------------------------------------
    def recents(self) -> list[Path]:
        """The last visited folders, newest first."""
        return [self._abs(rel) for rel in self._entry()["recents"]] if self._root else []

    def touch_recent(self, folder: Path) -> bool:
        """``folder`` was visited: it goes first. The project root is not a recent folder. Written
        by the next ``flush``."""
        rel = self._rel(folder)
        if rel is None or rel == ".":
            return False
        recents = self._entry()["recents"]
        if recents and recents[0] == rel:
            return False
        if rel in recents:
            recents.remove(rel)
        recents.insert(0, rel)
        del recents[RECENT_LIMIT:]
        self._dirty = True
        return True

    def prune_missing_recents(self, exists: Callable[[Path], bool] = os.path.isdir) -> bool:
        """Drop the recent folders that no longer ``exist`` (once per session, at the start).
        Favorites stay until the user removes them."""
        entry = self._entry()
        kept = [rel for rel in entry["recents"] if exists(self._abs(rel))]
        if kept == entry["recents"]:
            return False
        entry["recents"] = kept
        self._dirty = True
        return True

    # -- rename ----------------------------------------------------------------------------------
    def rename(self, old: Path, new: Path) -> bool:
        """Follow a renamed folder (call after the move): favorites and recents inside ``old``
        move under ``new``, or go away when ``new`` is outside the project. Saved at once."""
        if self._root is None:
            return False
        old_rel, new_rel = self._rel(old), self._rel(new)
        if old_rel is None or old_rel == ".":  # the project root is never renamed from here
            return False
        entry = self._entry()
        changed = False
        for name in ("favorites", "recents"):
            moved: list[str] = []
            for rel in entry[name]:
                if rel == old_rel or rel.startswith(old_rel + "/"):
                    changed = True
                    if new_rel is None:
                        continue
                    rel = new_rel + rel[len(old_rel) :]
                moved.append(rel)
            entry[name] = list(dict.fromkeys(moved))
        if changed:
            self._save()
        return changed
