"""The saved grids of plots (spec 23), by name, with the settings of each grid figure.

Stored in the app data dir (``grids.json``), never inside a simulation folder (they get synced), like
``FolderMemory`` and ``CompoundStore``. Plot paths are kept relative to ``paths.local_root`` (outside
it: absolute, prefixed ``abs:``) and resolved against the root in force when a grid is read, so a
moved project keeps its grids and another project shows them with its own folders; a grid whose
folders do not exist there is only unavailable, never removed.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from .appdirs import atomic_write_text, data_dir, set_aside_corrupt
from .plotting.grid import GridCell, GridSpec, PlotRef

log = logging.getLogger(__name__)

# {"version": 1, "grids": {name: {"rows", "cols", "cells": [{"row", "col", "path", "kind",
# "partner", "title"}], "params": {...}}}}
FORMAT_VERSION = 1
OUTSIDE = "abs:"  # a path outside the root


class GridStore:
    """The file is read once, on first use, and written on every change (atomically). An unreadable
    file is renamed ``grids.json.corrompido-<date>`` and never overwritten; if it cannot be renamed
    the store keeps working in memory and writes nothing."""

    def __init__(self, path: Path | None = None, root: Path | None = None):
        self.path = path or data_dir() / "grids.json"
        self._lock = threading.RLock()
        self._grids: dict[str, dict] | None = None
        self._root: Path | None = None  # as given: the paths the app shows are under it
        self._real_root: Path | None = None  # resolved: a path reached through a symlink
        self._warning: str | None = None
        self._read_only = False
        if root is not None:
            self.set_root(root)

    # -- paths -----------------------------------------------------------------------------------
    def set_root(self, root: Path | None) -> None:
        """The project root stored paths are relative to (set again when the project changes)."""
        with self._lock:
            self._root = Path(os.path.abspath(Path(root).expanduser())) if root else None
            self._real_root = self._root.resolve() if self._root is not None else None

    def _value(self, path: Path) -> str:
        path = Path(os.path.abspath(path))
        if self._root is not None and self._real_root is not None:
            if path.is_relative_to(self._root):
                return path.relative_to(self._root).as_posix()
            real = path.resolve()
            if real.is_relative_to(self._real_root):
                return real.relative_to(self._real_root).as_posix()
        return OUTSIDE + str(path)

    def _path(self, value: str) -> Path:
        if value.startswith(OUTSIDE):
            return Path(value.removeprefix(OUTSIDE))
        base = self._root if self._root is not None else Path.cwd()
        return Path(os.path.normpath(base / value))

    # -- queries ---------------------------------------------------------------------------------
    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._load(), key=str.casefold)

    def get(self, name: str) -> GridSpec | None:
        """The grid saved as ``name`` with its paths in the current root; None when there is none
        (or its entry cannot be read)."""
        with self._lock:
            entry = self._load().get(name)
            try:
                return self._spec(name, entry) if isinstance(entry, dict) else None
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("grids.json: grade %r ilegível (%s)", name, exc)
                return None

    def params(self, name: str) -> dict[str, Any]:
        """The settings of the grid figure saved with ``name`` (empty: the defaults)."""
        with self._lock:
            entry = self._load().get(name)
            params = entry.get("params") if isinstance(entry, dict) else None
            return dict(params) if isinstance(params, dict) else {}

    def pop_warning(self) -> str | None:
        """The message about a corrupt file, once (None afterwards or when it was fine)."""
        with self._lock:
            self._load()
            warning, self._warning = self._warning, None
            return warning

    # -- changes ---------------------------------------------------------------------------------
    def save(self, spec: GridSpec) -> None:
        """Save the definition under ``spec.name``, keeping the settings saved with it."""
        with self._lock:
            grids = self._load()
            old = grids.get(spec.name)
            entry = self._entry(spec)
            if isinstance(old, dict) and isinstance(old.get("params"), dict):
                entry["params"] = old["params"]
            grids[spec.name] = entry
            self._write()

    def save_params(self, name: str, values: dict[str, Any]) -> None:
        """The settings of the grid ``name``; nothing for a grid that is not saved."""
        with self._lock:
            entry = self._load().get(name)
            if not isinstance(entry, dict) or entry.get("params") == values:
                return
            entry["params"] = dict(values)
            self._write()

    def delete(self, name: str) -> None:
        with self._lock:
            if self._load().pop(name, None) is not None:
                self._write()

    def rename(self, old: Path, new: Path) -> None:
        """Follow a renamed file or folder (after the move): the plots inside it move to ``new``."""
        old, new = Path(os.path.abspath(old)), Path(os.path.abspath(new))
        pairs = [(old, new), (old.resolve(), new.resolve())]

        def moved(path: Path) -> Path:
            for before, after in pairs:
                if path.is_relative_to(before):
                    return after / path.relative_to(before)
            return path

        with self._lock:
            changed = False
            for entry in self._load().values():
                for cell in entry.get("cells", []) if isinstance(entry, dict) else []:
                    for key in ("path", "partner"):
                        value = cell.get(key) if isinstance(cell, dict) else None
                        if not isinstance(value, str):
                            continue
                        updated = self._value(moved(self._path(value)))
                        if updated != value:
                            cell[key] = updated
                            changed = True
            if changed:
                self._write()

    # -- entries ---------------------------------------------------------------------------------
    def _entry(self, spec: GridSpec) -> dict[str, Any]:
        cells = []
        for cell in spec.cells:
            if cell.ref is None:
                continue
            ref = cell.ref
            cells.append(
                {
                    "row": cell.row,
                    "col": cell.col,
                    "path": self._value(ref.path),
                    "kind": ref.kind,
                    "partner": self._value(ref.partner) if ref.partner is not None else None,
                    "title": cell.title,
                }
            )
        return {"rows": spec.rows, "cols": spec.cols, "cells": cells}

    def _spec(self, name: str, entry: dict) -> GridSpec:
        cells = []
        for raw in entry["cells"]:
            partner = raw.get("partner")
            ref = PlotRef(
                self._path(str(raw["path"])),
                str(raw["kind"]),
                self._path(partner) if isinstance(partner, str) else None,
            )
            cells.append(GridCell(int(raw["row"]), int(raw["col"]), ref, str(raw.get("title", ""))))
        return GridSpec(name, int(entry["rows"]), int(entry["cols"]), cells)

    # -- file ------------------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if self._grids is not None:
            return self._grids
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            data = self._set_aside(exc)
        if not isinstance(data, dict):
            data = self._set_aside("o conteúdo não é um objeto JSON")
        grids = data.get("grids")
        if data and (data.get("version") != FORMAT_VERSION or not isinstance(grids, dict)):
            self._set_aside(f"versão de formato desconhecida: {data.get('version')!r}")
            grids = None
        self._grids = grids if isinstance(grids, dict) else {}
        return self._grids

    def _set_aside(self, problem: object) -> dict:
        try:
            copy = set_aside_corrupt(self.path)
        except OSError as exc:
            self._read_only = True
            self._warning = (
                f"{self.path.name} ilegível e não pôde ser copiado ({exc.strerror or exc}): "
                "as grades desta sessão não serão salvas"
            )
        else:
            self._warning = f"{self.path.name} estava corrompido; cópia salva em {copy}"
        log.warning("%s (%s)", self._warning, problem)
        return {}

    def _write(self) -> None:
        if self._read_only:
            return
        data = {"version": FORMAT_VERSION, "grids": self._load()}
        atomic_write_text(self.path, json.dumps(data, indent=1, ensure_ascii=False))
