"""Calculation type detection for a simulation folder (PRD §3)."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .calculations import (
    REGISTRY,
    CalculationModule,
    DetectionResult,
    FolderListing,
    describe_plottable,
    module_for,
)
from .calculations.bands_dos import ordered_pair, pair_result
from .calculations.base import LoadError, SniffFn
from .folder_memory import FolderMemory
from .plotting.grid import PlotRef
from .plotting.plot_file import read_plot_file
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

    @property
    def plot_id(self) -> str:
        return str(self.plot_target)

    def build(self) -> DetectionResult:
        return manual_result(self.module, self.folder, self.mapping, self.sniff)


PAIR_KIND = "bands_dos"


@dataclass(frozen=True)
class PairTarget:
    """Bands + DOS of two folders (spec 22), detected and paired in the load worker: the folders
    may have changed (or gone) since the menu that offered the pair."""

    bands: Path
    dos: Path
    sniff: SniffFn
    memory: FolderMemory | None = None

    @property
    def module(self) -> CalculationModule:
        return module_for(PAIR_KIND)

    @property
    def kind(self) -> str:
        return PAIR_KIND

    @property
    def plot_target(self) -> Path:
        return self.bands

    @property
    def plot_id(self) -> str:
        return f"{self.bands}|{self.dos}"

    def build(self) -> DetectionResult:
        """The combined result; ``LoadError`` (for the user) when a folder is gone or the two no
        longer make a pair."""
        for folder, name in ((self.bands, "das bandas"), (self.dos, "da DOS")):
            if not folder.is_dir():
                raise LoadError(f"Pasta {name} não encontrada: {folder}")
        sniff = sniff_once(self.sniff)
        pair = ordered_pair(
            detect_folder(self.bands, sniff, self.memory),
            detect_folder(self.dos, sniff, self.memory),
        )
        if pair is None:
            raise LoadError(
                f"{self.bands.name} e {self.dos.name} não formam um par de bandas e DOS completos."
            )
        return pair_result(pair, self.module)

    @classmethod
    def from_plot_file(
        cls, bands: Path, sniff: SniffFn, memory: FolderMemory | None = None
    ) -> PairTarget | None:
        """The pair saved in ``bands/bands_dos.plot`` (its ``dos_folder``), to reopen the figure
        from the bands folder alone; None without one. Reads a file: worker only."""
        values, _warnings = read_plot_file(bands, PAIR_KIND)
        partner = (values or {}).get("dos_folder")
        if not isinstance(partner, str) or not partner:
            return None
        return cls(bands, Path(os.path.normpath(bands / partner)), sniff, memory)


@dataclass(frozen=True)
class FolderTarget:
    """The plot of one kind in a folder, detected again in the load worker: a grid cell whose tab
    is closed (spec 23). The folder may be gone or no longer hold that kind."""

    folder: Path
    kind: str
    sniff: SniffFn
    memory: FolderMemory | None = None

    @property
    def module(self) -> CalculationModule:
        return module_for(self.kind)

    @property
    def plot_target(self) -> Path:
        return self.folder

    @property
    def plot_id(self) -> str:
        return str(self.folder)

    def build(self) -> DetectionResult:
        if not self.folder.is_dir():
            raise LoadError(f"Pasta não encontrada: {self.folder}")
        results = detect_folder(self.folder, self.sniff, self.memory)
        found = next((r for r in results if r.kind == self.kind and r.plottable), None)
        if found is None:
            name = self.module.display_name.lower()
            raise LoadError(f"Nenhum cálculo de {name} completo em {self.folder.name}.")
        return found


def ref_target(
    ref: PlotRef, sniff: SniffFn, memory: FolderMemory | None = None
) -> ManualTarget | PairTarget | FolderTarget:
    """How to plot a grid cell's ``ref`` again: a figure of two folders, the output file of a
    single-file module, or a folder's detection. Stats the path (worker): a missing output file
    raises ``LoadError`` here, a missing folder in ``build``."""
    module = module_for(ref.kind)
    if ref.partner is not None:
        return PairTarget(ref.path, ref.partner, sniff, memory)
    if module.single_file_role is not None and not ref.path.is_dir():
        if not ref.path.is_file():
            raise LoadError(f"Arquivo não encontrado: {ref.path}")
        return ManualTarget(module, ref.path.parent, {module.single_file_role: [ref.path]}, sniff)
    return FolderTarget(ref.path, ref.kind, sniff, memory)


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


def plottable_modules(
    modules: Iterable[CalculationModule] = REGISTRY,
) -> list[CalculationModule]:
    """The kinds the manual mapping dialog offers (not the figures made from several folders)."""
    return [m for m in modules if m.plottable and m.selectable]
