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
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..qe import projwfc
from ..sniff import FileKind, FileSniff

if TYPE_CHECKING:
    from matplotlib.figure import Figure

SniffFn = Callable[[Path], FileSniff]

# Folders never scanned below the simulation folder itself.
IGNORED_SUBDIRS = re.compile(r"^(tmp|plots|out|.*\.save|\..*)$", re.I)


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
        try:
            return path.relative_to(self.folder).as_posix()
        except ValueError:
            return path.as_posix()


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
    module: CalculationModule
    folder: Path
    files: dict[str, list[Path]] = field(default_factory=dict)
    methods: dict[str, Method] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.module.kind

    @property
    def badge(self) -> str:
        return self.module.badge

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def plottable(self) -> bool:
        return self.module.plottable and self.complete

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


class CalculationModule:
    kind: ClassVar[str]
    badge: ClassVar[str]
    display_name: ClassVar[str]
    roles: ClassVar[tuple[FileRole, ...]]
    plottable: ClassVar[bool] = False
    fallback: ClassVar[bool] = False  # informational badge, only when no primary kind matched

    def role(self, role_id: str) -> FileRole:
        return next(r for r in self.roles if r.id == role_id)

    # -- detection -----------------------------------------------------------------------
    def match(
        self,
        listing: FolderListing,
        sniff: SniffFn,
        forced: dict[str, list[Path]] | None = None,
    ) -> DetectionResult | None:
        """Fill roles from ``listing``; None when no anchor role is present.

        ``forced`` holds user-mapped files (manual mapping), which take precedence.
        """
        sniffs = {path: sniff(path) for path in listing.files}
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
                if _glob_match(listing.relative(p), role.globs) and role.accepts(sniffs[p])
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
    def default_params(self, config: Any) -> Any:
        raise NotImplementedError

    def load(self, result: DetectionResult) -> Any:
        raise NotImplementedError

    def render(self, figure: Figure, dataset: Any, params: Any, style: Any) -> Any:
        raise NotImplementedError


def _glob_match(relative: str, globs: Sequence[str]) -> bool:
    lowered = relative.lower()
    return any(fnmatch.fnmatch(lowered, g.lower()) for g in globs)


def _rank(path: Path, s: FileSniff) -> tuple[bool, float, int]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (s.job_done is not False, mtime, -len(path.name))
