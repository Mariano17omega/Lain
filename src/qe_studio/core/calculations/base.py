"""Calculation modules: what files a calculation type needs and how to plot it.

Each module declares file *roles*. Detection fills roles in three passes (PRD §3):
PRD naming globs verified by content → content only → neighbours (for the SCF output, which
sometimes lives in a sibling ``*scf*`` folder). New calculation types are added by writing a
module and registering it in :mod:`qe_studio.core.calculations`.
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar

from ..compounds import AtomChoices, CompoundStore
from ..qe import projwfc
from ..sniff import FileKind, FileSniff
from .load_cache import CACHE
from .params import CommonParams, ParamField, RenderInfo

if TYPE_CHECKING:
    from matplotlib.figure import Figure, FigureBase

    from ..config import AppConfig
    from ..folder_memory import FolderMemory
    from ..grid_store import GridStore
    from ..plotting.session import PlotSession
    from ..plotting.style import PlotStyle

D = TypeVar("D")  # dataset a module loads (``None`` for detection-only modules)
P = TypeVar("P", bound=CommonParams)  # the module's plot parameters
AxesLimits = list[tuple[tuple[float, float], tuple[float, float]]]  # (xlim, ylim) per figure axes

SniffFn = Callable[[Path], FileSniff]

# Folders never scanned below the simulation folder itself.
IGNORED_SUBDIRS = re.compile(r"^(tmp|plots|out|.*\.save|\..*)$", re.I)


@dataclass(frozen=True)
class Stores:
    """The per-user stores a module may read and write (``CalculationModule.stored_params`` /
    ``save_stored``). They live in the app data dir, never in the (synced) simulation folder."""

    compounds: CompoundStore
    grids: GridStore | None = None  # the saved grids and their settings (spec 23)

    def pop_warnings(self) -> list[str]:
        """Messages about stores that were corrupt, once each."""
        grids = self.grids.pop_warning() if self.grids is not None else None
        return [w for w in (self.compounds.pop_warning(), grids) if w]


class Dataset(Protocol):
    """What the UI reads from any loaded dataset."""

    folder: Path
    warnings: list[str]


class LoadError(Exception):
    """A detected calculation cannot be loaded for plotting (message shown to the user)."""


class Method(StrEnum):
    NAME = "nome"
    CONTENT = "conteúdo"
    INFERRED = "inferido"
    MANUAL = "manual"


@dataclass(frozen=True)
class FileRole:
    id: str
    label: str
    accepts: Callable[[FileSniff], bool]
    globs: tuple[str, ...] = ()
    required: bool = False
    multiple: bool = False
    anchor: bool = False


def output_of(kind: FileKind, *calculations: str) -> Callable[[FileSniff], bool]:
    def accepts(s: FileSniff) -> bool:
        return s.kind is kind and (not calculations or s.calculation in calculations)

    return accepts


@dataclass(frozen=True)
class FolderListing:
    """Files of a simulation folder plus PDOS files in its immediate subfolders."""

    folder: Path
    files: tuple[Path, ...]

    @classmethod
    def scan(cls, folder: Path) -> FolderListing:
        files: list[Path] = []
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            return cls(folder, ())
        for entry in entries:
            try:
                if entry.is_file():
                    files.append(Path(entry.path))
                elif entry.is_dir() and not IGNORED_SUBDIRS.match(entry.name):
                    files.extend(_pdos_files(Path(entry.path)))
            except OSError:
                continue
        return cls(folder, tuple(files))

    def relative(self, path: Path) -> str:
        if (name := self._relatives.get(path)) is not None:
            return name
        try:
            return path.relative_to(self.folder).as_posix()
        except ValueError:
            return path.as_posix()

    @cached_property
    def _relatives(self) -> dict[Path, str]:
        """Relative name of every listed file, computed once: every role of every module matches
        its globs against them."""
        return {path: path.relative_to(self.folder).as_posix() for path in self.files}


def _pdos_files(subdir: Path) -> list[Path]:
    try:
        names = sorted(e.name for e in os.scandir(subdir) if e.is_file())
    except OSError:
        return []
    return [
        subdir / n
        for n in names
        if projwfc.parse_atm_name(n) is not None or projwfc.is_pdos_tot_name(n)
    ]


@dataclass
class DetectionResult:
    module: CalculationModule[Any, Any]
    folder: Path
    files: dict[str, list[Path]] = field(default_factory=dict)
    methods: dict[str, Method] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Results of other folders plotted together in one figure (bands + DOS, spec 22), in order.
    parts: tuple[DetectionResult, ...] = ()
    # A figure that belongs to no folder names itself (a grid, spec 23): the name keys its tab.
    plot_name: str = ""

    @property
    def kind(self) -> str:
        return self.module.kind

    @property
    def badge(self) -> str:
        return self.module.badge

    @property
    def badge_token(self) -> str | None:
        return self.module.badge_token

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def plottable(self) -> bool:
        return self.module.plottable and self.complete

    @property
    def plot_target(self) -> Path:
        """What a plot of this result shows (see ``CalculationModule.plot_target``)."""
        return self.module.plot_target(self.folder, self.files)

    @property
    def targets(self) -> tuple[Path, ...]:
        """Every folder (or file) the plot shows: its parts' (theirs too), or its own target."""
        return tuple(t for part in self.parts for t in part.targets) or (self.plot_target,)

    @property
    def plot_id(self) -> str:
        """What keys the plot's tab: its name, its target, or the targets of its parts joined by
        ``|``."""
        if self.plot_name:
            return self.plot_name
        if self.parts:
            return "|".join(str(part.plot_target) for part in self.parts)
        return str(self.plot_target)

    @property
    def method(self) -> Method:
        """Least certain method used for any role (manual > inferred > content > name).

        Roles without PRD naming globs can only be found by content and do not count.
        """
        used = {
            method
            for role_id, method in self.methods.items()
            if method is not Method.CONTENT or self.module.role(role_id).globs
        }
        for method in (Method.MANUAL, Method.INFERRED, Method.CONTENT):
            if method in used:
                return method
        return Method.NAME

    def file(self, role: str) -> Path | None:
        paths = self.files.get(role)
        return paths[0] if paths else None

    def role_label(self, role_id: str) -> str:
        return self.module.role(role_id).label


class CalculationModule(Generic[D, P]):
    kind: ClassVar[str]
    badge: ClassVar[str]
    display_name: ClassVar[str]
    # One short sentence for the badge tooltip (spec 18 R3); the UI never keeps its own table.
    description: ClassVar[str] = ""
    roles: ClassVar[tuple[FileRole, ...]]
    plottable: ClassVar[bool] = False
    fallback: ClassVar[bool] = False  # informational badge, only when no primary kind matched
    # Theme token family ``badge_<token>_{bg,fg,border}``; None = the generic ``other`` colors.
    badge_token: ClassVar[str | None] = None
    # Parameters the plot toolbar's Reset restores from the defaults (axis limits).
    view_fields: ClassVar[tuple[str, ...]] = ()
    # Own sections of the tuning panel as (name, section to insert before); see ``ordered_sections``.
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = ()
    # Role whose single file can be plotted on its own (right-click "Plotar"); see ``module_for_file``.
    single_file_role: ClassVar[str | None] = None
    # Offered in the manual mapping dialog. False for figures built from other results (spec 22).
    selectable: ClassVar[bool] = True
    # Parameters kept in ``<folder>/<kind>.plot``. False: every edit goes to ``save_stored`` (a grid).
    plot_file: ClassVar[bool] = True
    # Can be a cell of a grid (spec 23); a grid cannot.
    grid_cell: ClassVar[bool] = True

    def role(self, role_id: str) -> FileRole:
        return next(r for r in self.roles if r.id == role_id)

    def badge_tooltip(self) -> str:
        """The name and the sentence the badge tooltip shows (two lines)."""
        return f"{self.display_name}\n{self.description}" if self.description else self.display_name

    # -- detection -----------------------------------------------------------------------
    def match(
        self,
        listing: FolderListing,
        sniffs: dict[Path, FileSniff],
        sniff: SniffFn,
        forced: dict[str, list[Path]] | None = None,
    ) -> DetectionResult | None:
        """Fill roles from ``listing``; None when no anchor role is present.

        ``sniffs`` holds the sniff of every file of ``listing``, computed once for all modules
        (``detection.detect_folder``); ``sniff`` answers for other files (neighbour folders,
        mapped files). ``forced`` holds user-mapped files (manual mapping), which take precedence.
        """
        if not forced and not any(r.anchor for r in self.roles):
            return None  # never detected on its own: skip the scan
        result = DetectionResult(self, listing.folder)
        for role_id, paths in (forced or {}).items():
            existing = [p for p in paths if p.is_file()]
            if existing and any(r.id == role_id for r in self.roles):
                result.files[role_id] = existing
                result.methods[role_id] = Method.MANUAL
        for role in self.roles:
            if role.id in result.files:
                continue
            named = [
                p
                for p in listing.files
                if role.accepts(sniffs[p]) and _glob_match(listing.relative(p), role.globs)
            ]
            candidates, method = (named, Method.NAME)
            if not named:
                candidates = [p for p in listing.files if role.accepts(sniffs[p])]
                method = Method.CONTENT
            if candidates:
                chosen = self.select(role, candidates, sniffs, result)
                if chosen:
                    result.files[role.id] = chosen
                    result.methods[role.id] = method
        if not forced and not any(r.anchor and r.id in result.files for r in self.roles):
            return None
        self.finalize(result, listing, sniffs, sniff)
        result.missing = [r.id for r in self.roles if r.required and r.id not in result.files] + [
            m for m in result.missing if m not in result.files
        ]
        result.missing = list(dict.fromkeys(result.missing))
        for paths in result.files.values():
            for path in paths:
                s = sniffs.get(path) or sniff(path)
                result.warnings.extend(f"{path.name}: {w}" for w in s.warnings)
        result.warnings = list(dict.fromkeys(result.warnings))
        return result

    def select(
        self,
        role: FileRole,
        candidates: list[Path],
        sniffs: dict[Path, FileSniff],
        result: DetectionResult,
    ) -> list[Path]:
        """Pick the file(s) for ``role``; default = most complete, newest, shortest name."""
        if role.multiple:
            return sorted(candidates)
        return [max(candidates, key=lambda p: _rank(p, sniffs[p]))]

    def finalize(
        self,
        result: DetectionResult,
        listing: FolderListing,
        sniffs: dict[Path, FileSniff],
        sniff: SniffFn,
    ) -> None:
        """Hook for cross-role logic (inferred files, extra requirements, warnings)."""

    def infer_from_neighbours(
        self, result: DetectionResult, role_id: str, sniff: SniffFn, pattern: str = "*scf*"
    ) -> None:
        """Look for ``role_id`` in the parent folder and sibling folders matching ``pattern``."""
        if role_id in result.files:
            return
        role = self.role(role_id)
        parent = result.folder.parent
        places = [parent]
        try:
            places += sorted(
                p
                for p in parent.iterdir()
                if p.is_dir() and p != result.folder and fnmatch.fnmatch(p.name.lower(), pattern)
            )
        except OSError:
            return
        candidates = []
        for place in places:
            try:
                candidates += [p for p in place.iterdir() if p.is_file() and role.accepts(sniff(p))]
            except OSError:
                continue
        if candidates:
            result.files[role_id] = [max(candidates, key=lambda p: _rank(p, sniff(p)))]
            result.methods[role_id] = Method.INFERRED

    # -- plotting (implemented by plottable modules) ------------------------------------------
    def default_params(self, config: AppConfig, dataset: D) -> P:
        raise NotImplementedError

    def param_schema(self, dataset: D) -> list[ParamField]:
        raise NotImplementedError

    def param_changed(self, dataset: D, params: P, name: str, old: Any) -> None:
        """Hook to adjust dependent parameters after the user edits ``name``."""

    def plot_target(self, folder: Path, files: dict[str, list[Path]]) -> Path:
        """What one plot shows, and so what keys its tab: the folder, or one file for modules
        that plot a single output (several of them can then be open from the same folder)."""
        return folder

    def plot_title(self, target: Path, dataset: D) -> str:
        """The title of the plot's tab."""
        return f"{self.display_name} · {target.name}"

    def export_stem(self, params: P) -> str:
        """File name (without extension) of the exported figure in ``plots/``."""
        return self.kind

    def load(self, result: DetectionResult, sniff: SniffFn) -> D:
        """Read the dataset of ``result``. ``sniff`` is the caller's cache (the detection
        service's in the app), which already holds the sniffs of the detected files."""
        raise NotImplementedError

    def render(self, figure: FigureBase, dataset: D, params: P, style: PlotStyle) -> RenderInfo:
        raise NotImplementedError

    # -- view hooks: keep the UI free of per-module knowledge ----------------------------------
    def apply_limits(self, params: P, axes_limits: AxesLimits) -> None:
        """Store the toolbar pan/zoom in ``params`` so edits and exports keep it.

        ``axes_limits`` holds ``(xlim, ylim)`` of every axes of the figure, in ``figure.axes``
        order. Default: the view is not stored.
        """

    def legacy_params(self, params: P, folder: Path, memory: FolderMemory) -> None:
        """Apply older ``FolderMemory`` data when there is no ``<kind>.plot`` yet."""

    def format_coordinates(self, x: float, y: float, axes_index: int, dataset: D, params: P) -> str:
        """Cursor readout over axes number ``axes_index``."""
        return f"x = {x:.4g} · y = {y:.4g}"

    def axes_routes(self, figure: Figure, dataset: D) -> list[tuple[PlotSession, int]] | None:
        """For a figure made of other plots (a grid): the session and the index there of every axes
        of ``figure`` (readout, pan/zoom and Reset go to them). None: the axes are this plot's own."""
        return None

    def series_colors(self, dataset: D, params: P, style: PlotStyle) -> dict[str, str]:
        """Color of every series, for modules with a ``"series"`` parameter field."""
        return {}

    def default_labels(self, dataset: D) -> list[str]:
        """Labels shown as the placeholder of a ``"labels"`` parameter field."""
        return []

    def atoms_of(self, dataset: D) -> AtomChoices | None:
        """The atoms a plot can be restricted to (spec 21) or None for a module without atoms. An
        empty ``sites`` means they could not be read: the picker is offered but disabled."""
        return None

    def stored_params(self, dataset: D, stores: Stores) -> dict[str, Any]:
        """Parameter values kept in ``stores`` instead of ``<kind>.plot`` (fields declared with
        ``metadata={"store": ...}``); applied over the defaults, before the ``.plot``."""
        return {}

    def save_stored(self, dataset: D, params: P, name: str, stores: Stores) -> None:
        """The user edited ``name``, a parameter kept in ``stores``: save it there."""

    def load_cached(self, result: DetectionResult, sniff: SniffFn) -> D:
        """``load`` memoized on the files' (mtime, size), within a memory budget and loaded once
        per key (``load_cache``); safe to call from worker threads."""
        key = (
            self.kind,
            tuple(
                sorted(
                    (role, tuple(_stamp(p) for p in paths)) for role, paths in result.files.items()
                )
            ),
        )
        files = [p for paths in result.files.values() for p in paths]
        return CACHE.get_or_load(key, files, lambda: self.load(result, sniff))


def _stamp(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (str(path), 0, 0)
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _glob_match(relative: str, globs: Sequence[str]) -> bool:
    lowered = relative.lower()
    return any(fnmatch.fnmatch(lowered, g.lower()) for g in globs)


def _rank(path: Path, s: FileSniff) -> tuple[bool, float, int]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (s.job_done is not False, mtime, -len(path.name))
