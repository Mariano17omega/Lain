"""Projects (spec 31): the first-level folders of ``paths.local_root``.

A project is a plain folder; the simulation units live in it at any depth and need no mark. This
module lists the projects (worker), says which project a path belongs to, checks the name of a new
one and creates it (worker). The UI keeps the one selected (``ui/project_controller.py``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .fuzzy import fold
from .paths import is_hidden, normalize_patterns

__all__ = [
    "EXPORTS_DIR",
    "Project",
    "ProjectError",
    "create_project",
    "list_projects",
    "project_of",
    "validate_project_name",
]

EXPORTS_DIR = "plots"  # the grids' exports (``<local_root>/plots``): never a project
_NAME = re.compile(r"[A-Za-z0-9._-]+")


class ProjectError(Exception):
    """Why a project was not created (Portuguese); nothing was left behind."""


@dataclass(frozen=True)
class Project:
    name: str
    path: Path


def list_projects(
    root: Path,
    hidden_dirs: list[str],
    cancelled: Callable[[], bool] = lambda: False,
) -> list[Project]:
    """The first-level folders of ``root``, sorted by name without case or accents.

    Same visibility rule as the panels and the palette's index (``core/folder_index``): dotted
    names, ``hidden_dirs`` matches and symlinks are skipped; ``plots`` too. An unreadable ``root``
    has no projects. ``cancelled`` is polled between entries; a cancelled scan returns what it has.
    """
    patterns = normalize_patterns(hidden_dirs)
    found: list[Project] = []
    try:
        with os.scandir(root) as scan:
            for entry in scan:
                if cancelled():
                    break
                name = entry.name
                if name.startswith(".") or name == EXPORTS_DIR or is_hidden(name, patterns):
                    continue
                try:
                    if entry.is_symlink() or not entry.is_dir():
                        continue
                except OSError:
                    continue
                found.append(Project(name, Path(entry.path)))
    except OSError:
        return []
    return sorted(found, key=lambda project: (fold(project.name), project.name))


def project_of(path: Path, root: Path) -> str | None:
    """The project ``path`` belongs to (its first component below ``root``); ``None`` for ``root``
    itself and for a path outside it. Pure: nothing is resolved or read."""
    try:
        parts = Path(path).relative_to(root).parts
    except ValueError:
        return None
    return parts[0] if parts else None


def validate_project_name(
    name: str, existing: list[str], hidden_dirs: list[str] | tuple[str, ...] = ()
) -> list[str]:
    """What is wrong with the name typed for a new project ([] = nothing), in Portuguese.

    An existing name is refused whatever its case ("Ilita" and "ilita" would be confusing and
    collide on a case-insensitive file system), and so is one the panels would hide."""
    name = name.strip()
    if not name:
        return ["Digite um nome para o projeto"]
    if not _NAME.fullmatch(name):
        return ["Use só letras sem acento, números, ponto, hífen e sublinhado no nome"]
    if name.startswith("."):
        return ["O nome não pode começar com ponto"]
    if name.casefold() == EXPORTS_DIR or is_hidden(name, normalize_patterns(list(hidden_dirs))):
        return ["Este nome é reservado: a pasta não apareceria como projeto"]
    if name.casefold() in {other.casefold() for other in existing}:
        return ["Já existe um projeto com esse nome"]
    return []


def create_project(root: Path, name: str, hidden_dirs: list[str] | tuple[str, ...] = ()) -> Path:
    """Make the folder ``root/name`` and nothing else. Never reuses a folder: one that exists is a
    ``ProjectError``, also when it appeared after the name was checked."""
    problems = validate_project_name(name, [], hidden_dirs)
    if problems:
        raise ProjectError(problems[0])
    path = Path(root) / name.strip()
    try:
        path.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise ProjectError("Já existe uma pasta com esse nome") from exc
    except OSError as exc:
        raise ProjectError(f"Não foi possível criar a pasta {path}: {exc.strerror or exc}") from exc
    return path
