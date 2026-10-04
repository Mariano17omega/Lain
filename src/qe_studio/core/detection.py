"""Calculation type detection for a simulation folder (PRD §3)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .calculations import REGISTRY, CalculationModule, DetectionResult, FolderListing
from .calculations.base import SniffFn
from .folder_memory import FolderMemory
from .sniff import FileSniff
from .sniff import sniff as default_sniff


def sniff_once(sniff: SniffFn) -> SniffFn:
    """``sniff`` memoized for one detection: each file is sniffed (one ``stat`` and a cache lock,
    at best) once, whichever modules and hooks ask, neighbour folders included (spec 14 R3)."""
    seen: dict[Path, FileSniff] = {}

    def memoized(path: Path) -> FileSniff:
        if (found := seen.get(path)) is None:
            found = seen[path] = sniff(path)
        return found

    return memoized


def _sniffs_of(listing: FolderListing, sniff: SniffFn) -> dict[Path, FileSniff]:
    return {path: sniff(path) for path in listing.files}


def detect_folder(
    folder: Path,
    sniff: SniffFn = default_sniff,
    memory: FolderMemory | None = None,
    modules: Iterable[CalculationModule] = REGISTRY,
) -> list[DetectionResult]:
    """Detected calculation types in ``folder``: primary kinds first, else one fallback tag."""
    folder = Path(folder)
    listing = FolderListing.scan(folder)
    sniff = sniff_once(sniff)
    sniffs = _sniffs_of(listing, sniff)
    stored = memory.mappings(folder) if memory else {}
    modules = list(modules)
    results = []
    for module in modules:
        if module.fallback:
            continue
        forced = stored.get(module.kind)
        result = module.match(listing, sniffs, sniff, forced)
        if result is not None:
            results.append(result)
    if not results:
        for module in modules:
            if module.fallback and (result := module.match(listing, sniffs, sniff)) is not None:
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
    listing = FolderListing.scan(folder)
    sniff = sniff_once(sniff)
    result = module.match(listing, _sniffs_of(listing, sniff), sniff, forced=mapping)
    if result is None:  # empty mapping and no anchor file
        missing = [r.id for r in module.roles if r.required]
        result = DetectionResult(module, Path(folder), missing=missing)
    return result
