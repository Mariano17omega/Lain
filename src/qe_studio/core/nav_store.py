"""Favorite and recent folders of each project (spec 16 R4).

Stored in the app data dir (``navigation.json``), never inside simulation folders (they get
synced). A project is keyed by its resolved ``paths.local_root`` and its folders by their path
relative to that root, like ``FolderMemory`` (spec 14 R7), so a moved or copied project keeps its
favorites. Folders outside the root are not kept (Lain never shows one).

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

from .appdirs import atomic_write_text, data_dir, set_aside_corrupt

log = logging.getLogger(__name__)

FORMAT_VERSION = 1  # {"version": 1, "projects": {root: {"favorites": [rel], "recents": [rel]}}}
RECENT_LIMIT = 10


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


class NavigationStore:
    def __init__(self, path: Path | None = None, root: Path | None = None):
        self.path = path or data_dir() / "navigation.json"
        self._root: Path | None = None  # as given: what the visited folders are under
        self._key = ""  # its resolved path: the project's key in the file
        self._projects: dict[str, dict] | None = None
        self._warning: str | None = None
        self._read_only = False  # unreadable and could not be set aside: never overwrite it
        self._dirty = False
        if root is not None:
            self.set_root(root)

    # -- project ---------------------------------------------------------------------------------
    def set_root(self, root: Path) -> None:
        """The project whose favorites and recents are asked for (set again on a config reload)."""
        self.flush()
        self._root = Path(os.path.abspath(Path(root).expanduser()))
        self._key = str(self._root.resolve())

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
            data = {}
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
