"""User decisions per simulation folder: manual file mappings and typed k-point labels (PRD §3.2).

Stored in the app data dir (``folders.json``), never inside simulation folders (they get synced).
Folders are keyed by their path relative to ``paths.local_root`` and mapped files by their path
relative to the folder (spec 14 R7), so moving the project, or opening a copy of it on another
machine, keeps them. Folders outside the root keep their absolute path, prefixed ``abs:``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from .appdirs import atomic_write_text, data_dir, set_aside_corrupt

log = logging.getLogger(__name__)

FORMAT_VERSION = 2  # {"version": 2, "folders": {key: entry}}; version 1 was {absolute path: entry}
OUTSIDE = "abs:"  # key prefix of a folder outside the root


def _resolved(path: Path | None) -> Path | None:
    return Path(path).expanduser().resolve() if path is not None else None


class FolderMemory:
    def __init__(self, path: Path | None = None, root: Path | None = None):
        self.path = path or data_dir() / "folders.json"
        self._root = _resolved(root)
        self._lock = threading.Lock()
        self._folders: dict[str, dict] | None = None
        self._warning: str | None = None
        self._read_only = False  # the file could neither be read nor set aside: never overwrite it

    # -- keys and stored file names ----------------------------------------------------------------
    def _key(self, folder: Path) -> str:
        folder = Path(folder).resolve()
        if self._root is not None and folder.is_relative_to(self._root):
            return folder.relative_to(self._root).as_posix()  # "." for the root itself
        return OUTSIDE + str(folder)

    def _folder(self, key: str) -> Path | None:
        """The folder a key names (None: a relative key while no root is set)."""
        if key.startswith(OUTSIDE):
            return Path(key.removeprefix(OUTSIDE))
        return self._root / key if self._root is not None else None

    def _inside_root(self, path: Path) -> bool:
        return self._root is not None and path.resolve().is_relative_to(self._root)

    def _file_value(self, folder: Path, file: Path) -> str:
        """``file`` as stored for ``folder``: relative to it (POSIX) when inside it or inside the
        root, else absolute."""
        file, folder = Path(os.path.abspath(file)), Path(os.path.abspath(folder))
        if file.is_relative_to(folder):
            return file.relative_to(folder).as_posix()
        real_file, real_folder = file.resolve(), folder.resolve()
        if real_file.is_relative_to(real_folder):  # reached through a symlink
            return real_file.relative_to(real_folder).as_posix()
        if self._inside_root(file):
            return Path(os.path.relpath(real_file, real_folder)).as_posix()
        return str(file)

    @staticmethod
    def _file_path(folder: Path, value: str) -> Path:
        return Path(os.path.normpath(Path(os.path.abspath(folder)) / value))

    def _normalized(self, folder: Path, entry: dict) -> dict:
        """``entry`` with its mapped files stored as ``_file_value`` says (absolute ones from an
        old file or from outside the root, before it was set, become relative)."""
        for roles in entry.get("mappings", {}).values():
            for role, values in roles.items():
                roles[role] = [self._file_value(folder, self._file_path(folder, v)) for v in values]
        return entry

    # -- file ----------------------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if self._folders is not None:
            return self._folders
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {"version": FORMAT_VERSION, "folders": {}}
        except (OSError, ValueError) as exc:
            data = self._set_aside(exc)
        if not isinstance(data, dict):
            data = self._set_aside("o conteúdo não é um objeto JSON")
        migrated = False
        if "version" not in data:  # version 1: absolute folder paths as keys
            folders = self._migrate(data)
            migrated = True
        elif data.get("version") == FORMAT_VERSION and isinstance(data.get("folders"), dict):
            folders = data["folders"]
        else:
            self._set_aside(f"versão de formato desconhecida: {data.get('version')!r}")
            folders = {}
        self._folders = folders
        rehomed = self._rehome()
        if migrated or rehomed:
            self._save()
        return folders

    def _migrate(self, data: dict) -> dict[str, dict]:
        folders: dict[str, dict] = {}
        for key, entry in data.items():
            if isinstance(entry, dict):
                folder = Path(key)
                folders.setdefault(self._key(folder), self._normalized(folder, entry))
        log.info("folders.json: %d pastas migradas para chaves relativas", len(folders))
        return folders

    def _rehome(self) -> bool:
        """Re-key ``abs:`` folders that are inside the root (set after they were stored); an entry
        already under the relative key wins."""
        folders = self._folders
        if self._root is None or not folders:
            return False
        changed = False
        for key in [k for k in folders if k.startswith(OUTSIDE)]:
            folder = Path(key.removeprefix(OUTSIDE))
            if folder.is_relative_to(self._root):
                entry = folders.pop(key)
                folders.setdefault(self._key(folder), self._normalized(folder, entry))
                changed = True
        return changed

    def _set_aside(self, problem: object) -> dict:
        """Keep an unreadable ``folders.json`` as ``<name>.corrompido-<date>`` and start empty."""
        try:
            copy = set_aside_corrupt(self.path)
        except OSError as exc:
            self._read_only = True
            self._warning = (
                f"{self.path.name} ilegível e não pôde ser copiado ({exc.strerror or exc}): "
                "mapeamentos e rótulos desta sessão não serão salvos"
            )
        else:
            self._warning = f"{self.path.name} estava corrompido; cópia salva em {copy}"
        log.warning("%s (%s)", self._warning, problem)
        return {"version": FORMAT_VERSION, "folders": {}}

    def _save(self) -> None:
        if self._read_only:
            return
        data = {"version": FORMAT_VERSION, "folders": self._load()}
        atomic_write_text(self.path, json.dumps(data, indent=1, ensure_ascii=False))

    # -- public --------------------------------------------------------------------------------------
    def set_root(self, root: Path | None) -> None:
        """The project root (``paths.local_root``) keys are relative to; set again on a config
        reload. Relative keys stay as they are, so a copy of the project keeps its entries."""
        with self._lock:
            self._root = _resolved(root)
            if self._folders is not None and self._rehome():
                self._save()

    def load_warning(self) -> str | None:
        """Read the file now; the message to show if it was corrupt (and set aside)."""
        with self._lock:
            self._load()
            return self._warning

    def mappings(self, folder: Path) -> dict[str, dict[str, list[Path]]]:
        """The mapping of every kind for ``folder`` (one lookup: detection asks for all kinds)."""
        with self._lock:
            kinds = self._load().get(self._key(folder), {}).get("mappings", {})
            return {
                kind: {
                    role: [self._file_path(folder, v) for v in values]
                    for role, values in roles.items()
                }
                for kind, roles in kinds.items()
                if roles
            }

    def mapping(self, folder: Path, kind: str) -> dict[str, list[Path]] | None:
        return self.mappings(folder).get(kind)

    def set_mapping(self, folder: Path, kind: str, mapping: dict[str, list[Path]]) -> None:
        with self._lock:
            mappings = self._entry(folder).setdefault("mappings", {})
            mappings[kind] = {
                role: [self._file_value(folder, p) for p in paths]
                for role, paths in mapping.items()
            }
            self._save()

    def clear_mapping(self, folder: Path, kind: str) -> None:
        with self._lock:
            self._entry(folder).get("mappings", {}).pop(kind, None)
            self._save()

    def labels(self, folder: Path) -> list[str] | None:
        with self._lock:
            return self._load().get(self._key(folder), {}).get("labels")

    def set_labels(self, folder: Path, labels: list[str] | None) -> None:
        with self._lock:
            entry = self._entry(folder)
            if labels:
                entry["labels"] = list(labels)
            else:
                entry.pop("labels", None)
            self._save()

    def rename(self, old: Path, new: Path) -> None:
        """Follow a renamed file or folder (call after the move): the entries of ``old`` and its
        subfolders, and mapped files inside it, move to ``new``."""
        old, new = Path(os.path.abspath(old)), Path(os.path.abspath(new))
        pairs = [(old, new), (old.resolve(), new.resolve())]

        def moved(path: Path) -> Path:
            for before, after in pairs:
                if path.is_relative_to(before):
                    return after / path.relative_to(before)
            return path

        with self._lock:
            folders = self._load()
            changed = False
            for key, entry in list(folders.items()):
                folder = self._folder(key)
                if folder is None:
                    continue
                target = moved(folder)
                for roles in entry.get("mappings", {}).values():
                    for role, values in roles.items():
                        files = [moved(self._file_path(folder, v)) for v in values]
                        updated = [self._file_value(target, f) for f in files]
                        changed |= updated != values
                        roles[role] = updated
                if target != folder:
                    folders[self._key(target)] = folders.pop(key)
                    changed = True
            if changed:
                self._save()

    def _entry(self, folder: Path) -> dict:
        return self._load().setdefault(self._key(folder), {})
