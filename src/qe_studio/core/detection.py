"""Calculation type detection for a simulation folder (PRD §3)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .calculations import (
    REGISTRY,
    CalculationModule,
    DetectionResult,
    FolderListing,
    describe_plottable,
)
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


@dataclass(frozen=True)
class ManualTarget:
    """A manual mapping (PRD §3.2), matched in the load worker: that sniffs the chosen files,
    which can be big or on a network disk."""

    module: CalculationModule
    folder: Path
    mapping: dict[str, list[Path]]
    sniff: SniffFn

    @property
    def kind(self) -> str:
        return self.module.kind

    @property
    def plot_target(self) -> Path:
        return self.module.plot_target(self.folder, self.mapping)

    def build(self) -> DetectionResult:
        return manual_result(self.module, self.folder, self.mapping, self.sniff)


@dataclass(frozen=True)
class Chosen:
    """One complete plottable result: plot it."""

    result: DetectionResult


@dataclass(frozen=True)
class Ambiguous:
    """Several complete plottable kinds in one folder (e.g. BANDS + PDOS): the user picks one."""

    results: list[DetectionResult]


@dataclass(frozen=True)
class NeedsMapping:
    """Nothing complete to plot: the user maps the files (``message`` says why, or is empty)."""

    message: str


def plot_choice(results: list[DetectionResult]) -> Chosen | Ambiguous | NeedsMapping:
    """What "Gerar gráfico" does with a folder's detection results (PRD §3.2)."""
    complete = [r for r in results if r.module.plottable and r.complete]
    if len(complete) > 1:
        return Ambiguous(complete)
    if complete:
        return Chosen(complete[0])
    return NeedsMapping(mapping_message(results))


def mapping_message(results: list[DetectionResult]) -> str:
    """Why the manual mapping dialog opens, for the user ("" when a plottable kind was found but
    is incomplete: the dialog shows what is missing)."""
    detected = [r.badge for r in results if not r.module.plottable]
    if detected and not any(r.module.plottable for r in results):
        return (
            f"Esta pasta foi identificada como {', '.join(detected)}, que não tem gráfico "
            f"próprio. Para plotar {describe_plottable()}, indique os arquivos."
        )
    if not results:
        return (
            "Nenhum cálculo reconhecido nesta pasta (nomes e conteúdo). "
            "Indique o tipo de cálculo e os arquivos manualmente."
        )
    return ""


def plottable_modules() -> list[CalculationModule]:
    """The kinds the manual mapping dialog offers."""
    return [m for m in REGISTRY if m.plottable]
