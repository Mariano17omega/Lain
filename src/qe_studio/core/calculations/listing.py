"""The files of a simulation folder (detection's input): its own and the PDOS files one level down."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from ..qe import projwfc

# Folders never scanned below the simulation folder itself.
IGNORED_SUBDIRS = re.compile(r"^(tmp|plots|out|.*\.save|\..*)$", re.I)


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


def is_pdos_name(name: str) -> bool:
    return projwfc.parse_atm_name(name) is not None or projwfc.is_pdos_tot_name(name)


def _pdos_files(subdir: Path) -> list[Path]:
    try:
        names = sorted(e.name for e in os.scandir(subdir) if e.is_file())
    except OSError:
        return []
    return [subdir / n for n in names if is_pdos_name(n)]
