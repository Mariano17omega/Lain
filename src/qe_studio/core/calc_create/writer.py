"""Creating the folder of a new calculation (spec 25 R7).

The folder is ``<folder_prefix>_<suffix>`` in the chosen place, or ``…_1``, ``…_2`` when the name is
taken: an existing folder is never reused or touched. Each file is created exclusively, and a write
that fails removes only what this call created. Workers only (``run_task``).
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..unique_names import make_new_dir, next_free_dir
from .types.base import CalcPlan, CalcType, PlannedFile

__all__ = [
    "NOTES_NAME",
    "CreateError",
    "Created",
    "create_folder",
    "files_to_write",
    "folder_name",
    "preview_name",
    "validate_parent",
    "validate_suffix",
    "validate_target",
]

NOTES_NAME = "descricao.md"
_SUFFIX = re.compile(r"[A-Za-z0-9._-]+")


class CreateError(Exception):
    """Why the folder was not created (Portuguese); nothing was left behind."""


@dataclass(frozen=True)
class Created:
    folder: Path
    files: tuple[Path, ...]
    renamed_from: str | None = None  # the name asked for, when it was taken (a ``_N`` was added)


def folder_name(type_: CalcType, suffix: str) -> str:
    return f"{type_.folder_prefix}_{suffix.strip()}"


def validate_suffix(suffix: str) -> list[str]:
    """What is wrong with the name typed for the folder ([] = nothing)."""
    suffix = suffix.strip()
    if not suffix:
        return ["Informe o nome da pasta"]
    if not _SUFFIX.fullmatch(suffix) or suffix in (".", ".."):
        return ["Use só letras sem acento, números, ponto, hífen e sublinhado no nome"]
    return []


def validate_parent(parent: Path) -> list[str]:
    """What keeps the folder from being created in ``parent`` ([] = nothing). Only ``stat``s."""
    if not parent.is_dir():
        return [f"A pasta {parent} não existe"]
    if not os.access(parent, os.W_OK | os.X_OK):
        return [f"Sem permissão de escrita em {parent}"]
    return []


def validate_target(parent: Path, suffix: str) -> list[str]:
    """What keeps the folder from being created ([] = it can be). Only ``stat``s, no reading."""
    return validate_suffix(suffix) + validate_parent(parent)


def preview_name(parent: Path, type_: CalcType, suffix: str) -> str:
    """The name ``create_folder`` would use now (``bandas_Al_1`` if ``bandas_Al`` exists)."""
    return next_free_dir(parent / folder_name(type_, suffix)).name


def files_to_write(plan: CalcPlan, notes: str) -> list[PlannedFile]:
    """The plan's files plus ``descricao.md`` when the notes hold text (the "Arquivos" tab)."""
    files = list(plan.files)
    if notes.strip():
        text = notes if notes.endswith("\n") else notes + "\n"
        files.append(PlannedFile(NOTES_NAME, "notes", text, "Descrição"))
    return files


def _check_names(files: Sequence[PlannedFile]) -> None:
    seen: set[str] = set()
    for planned in files:
        name = planned.name
        if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
            raise CreateError(f"Nome de arquivo inválido: {name!r}")
        if name in seen:
            raise CreateError(f"Arquivo repetido no plano: {name}")
        seen.add(name)


def _remove(created: list[Path], folder: Path) -> None:
    for path in reversed(created):
        with contextlib.suppress(OSError):
            path.unlink()
    with contextlib.suppress(OSError):
        folder.rmdir()  # only if empty: never what someone else put there


def create_folder(
    parent: Path, type_: CalcType, suffix: str, plan: CalcPlan, notes: str = ""
) -> Created:
    """Create the folder and write the plan (and ``descricao.md``) into it. Raises
    ``CreateError``; on failure, removes the files it wrote and the folder it made."""
    problems = validate_target(parent, suffix)
    if problems:
        raise CreateError(problems[0])
    if plan.errors:
        raise CreateError(plan.errors[0])
    files = files_to_write(plan, notes)
    _check_names(files)
    asked = folder_name(type_, suffix)
    try:
        folder = make_new_dir(parent / asked)
    except OSError as exc:
        raise CreateError(f"Não foi possível criar a pasta {asked}: {exc.strerror or exc}") from exc
    written: list[Path] = []
    try:
        for planned in files:
            path = folder / planned.name
            with open(path, "x", encoding="utf-8", newline="") as handle:
                written.append(path)
                handle.write(planned.text)
    except (OSError, UnicodeError) as exc:
        _remove(written, folder)
        name = getattr(exc, "filename", None) or folder.name
        reason = getattr(exc, "strerror", None) or exc
        raise CreateError(f"Não foi possível gravar {Path(name).name}: {reason}") from exc
    except BaseException:
        _remove(written, folder)
        raise
    renamed = asked if folder.name != asked else None
    return Created(folder, tuple(written), renamed)
