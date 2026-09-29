"""Calculation type detection for a simulation folder (PRD §3)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path

from .appdirs import atomic_write_text, data_dir
from .calculations import REGISTRY, CalculationModule, DetectionResult, FolderListing
from .calculations.base import SniffFn
from .sniff import sniff as default_sniff


class FolderMemory:
    """User decisions per folder: manual file mappings and typed k-point labels.

    Stored in the app data dir, never inside simulation folders (they get synced).
    """

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "folders.json"
        self._lock = threading.Lock()
        self._data: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def _entry(self, folder: Path) -> dict:
        return self._load().setdefault(str(Path(folder).resolve()), {})

    def _save(self) -> None:
        atomic_write_text(self.path, json.dumps(self._load(), indent=1, ensure_ascii=False))

    def mapping(self, folder: Path, kind: str) -> dict[str, list[Path]] | None:
        with self._lock:
            stored = self._load().get(str(Path(folder).resolve()), {}).get("mappings", {})
            roles = stored.get(kind)
        return {role: [Path(p) for p in paths] for role, paths in roles.items()} if roles else None

    def set_mapping(self, folder: Path, kind: str, mapping: dict[str, list[Path]]) -> None:
        with self._lock:
            mappings = self._entry(folder).setdefault("mappings", {})
            mappings[kind] = {role: [str(p) for p in paths] for role, paths in mapping.items()}
            self._save()

    def clear_mapping(self, folder: Path, kind: str) -> None:
        with self._lock:
            self._entry(folder).get("mappings", {}).pop(kind, None)
            self._save()

    def labels(self, folder: Path) -> list[str] | None:
        with self._lock:
            return self._load().get(str(Path(folder).resolve()), {}).get("labels")

    def set_labels(self, folder: Path, labels: list[str] | None) -> None:
        with self._lock:
            entry = self._entry(folder)
            if labels:
                entry["labels"] = list(labels)
            else:
                entry.pop("labels", None)
            self._save()


def detect_folder(
    folder: Path,
    sniff: SniffFn = default_sniff,
    memory: FolderMemory | None = None,
    modules: Iterable[CalculationModule] = REGISTRY,
) -> list[DetectionResult]:
    """Detected calculation types in ``folder``: primary kinds first, else one fallback tag."""
    folder = Path(folder)
    listing = FolderListing.scan(folder)
    modules = list(modules)
    results = []
    for module in modules:
        if module.fallback:
            continue
        forced = memory.mapping(folder, module.kind) if memory else None
        result = module.match(listing, sniff, forced)
        if result is not None:
            results.append(result)
    if not results:
        for module in modules:
            if module.fallback and (result := module.match(listing, sniff)) is not None:
                results.append(result)
                break
    return results


def manual_result(
    module: CalculationModule,
    folder: Path,
    mapping: dict[str, list[Path]],
    sniff: SniffFn = default_sniff,
) -> DetectionResult:
    """Result built from a user mapping (manual mapping dialog, PRD §3.2)."""
    result = module.match(FolderListing.scan(folder), sniff, forced=mapping)
    if result is None:  # empty mapping and no anchor file
        missing = [r.id for r in module.roles if r.required]
        result = DetectionResult(module, Path(folder), missing=missing)
    return result
