"""Projects (spec 31): the first-level folders of ``paths.local_root``.

A project is a plain folder; the simulation units live in it at any depth and need no mark. This
module lists the projects (worker), says which project a path belongs to, checks the name of a new
one and creates it (worker). The UI keeps the one selected (``ui/files/project_controller.py``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...i18n import _
from ..files.paths import is_hidden, normalize_patterns, real_path
from ..remote.trash_dir import TRASH_DIR
from ..search.fuzzy import fold

__all__ = [
    "EXPORTS_DIR",
    "Project",
    "ProjectError",
    "create_project",
    "list_projects",
    "project_of",
    "root_name_error",
    "validate_project_name",
]

EXPORTS_DIR = "plots"  # the grids' exports (``<local_root>/plots``): never a project
_NAME = re.compile(r"[A-Za-z0-9._-]+")
# ``<remote_root>/trash`` is the cluster's trash (spec 84): a project of that name would mix with it.
TRASH_RESERVED = _("Este nome é reservado: é a lixeira do cluster")


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

    Same visibility rule as the panels and the palette's index (``core/search/folder_index``):
    dotted names, ``hidden_dirs`` matches and symlinks are skipped; ``plots`` too, and ``trash``, the
    mirror of the cluster's trash (spec 84: as a project, syncing it would pull it whole). An unreadable
    ``root`` has no projects. ``cancelled`` is polled between entries; a cancelled scan returns what
    it has.
    """
    patterns = normalize_patterns(hidden_dirs)
    found: list[Project] = []
    try:
        with os.scandir(root) as scan:
            for entry in scan:
                if cancelled():
                    break
                name = entry.name
                if name.startswith(".") or name in (EXPORTS_DIR, TRASH_DIR):
                    continue
                if is_hidden(name, patterns):
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
        return [_("Digite um nome para o projeto")]
    if not _NAME.fullmatch(name):
        return [_("Use só letras sem acento, números, ponto, hífen e sublinhado no nome")]
    if name.startswith("."):
        return [_("O nome não pode começar com ponto")]
    if name.casefold() == EXPORTS_DIR or is_hidden(name, normalize_patterns(list(hidden_dirs))):
        return [_("Este nome é reservado: a pasta não apareceria como projeto")]
    if name.casefold() == TRASH_DIR:
        return [TRASH_RESERVED]
    if name.casefold() in {other.casefold() for other in existing}:
        return [_("Já existe um projeto com esse nome")]
    return []


def root_name_error(path: Path, name: str, root: Path) -> str | None:
    """Why an item of ``root`` cannot be renamed to ``name`` (spec 84: the cluster's trash); None
    for any other name, and for an item below the root. The item's folder and ``root`` are compared
    with their links followed (the item itself may be a link: its own target does not count); only
    when the name is the reserved one is anything resolved."""
    if name.strip().casefold() != TRASH_DIR:
        return None
    return TRASH_RESERVED if real_path(Path(path).parent) == real_path(Path(root)) else None


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
        raise ProjectError(_("Já existe uma pasta com esse nome")) from exc
    except OSError as exc:
        raise ProjectError(
            _("Não foi possível criar a pasta {path}: {value}").format(
                path=path, value=exc.strerror or exc
            )
        ) from exc
    return path
