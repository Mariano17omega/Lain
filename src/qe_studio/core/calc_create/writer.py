"""Creating the folder of a new calculation (spec 25 R7, spec 28 R1).

The folder is ``<folder_prefix>_<suffix>`` (``Bands_Al``), or ``<folder_prefix>`` alone when no name
is given, in the chosen place, or ``…_1``, ``…_2`` when the name is taken: an existing folder is never
reused or touched. Numbered (spec 51), the name gets the place's next number in front (``2_Bands_Al``,
``numbering.next_number``), taken again when the folder is made. Each file is created exclusively, and a write
that fails removes only what this call created. Workers only (``run_task``).
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ...i18n import _
from ..files.unique_names import make_new_dir, next_free_dir
from .fingerprint import FINGERPRINT_NAME, Source, fingerprint_text
from .numbering import next_number
from .types.base import CalcPlan, CalcType, PlannedFile

__all__ = [
    "FINGERPRINT_KEY",
    "NOTES_NAME",
    "CreateError",
    "Created",
    "create_folder",
    "files_to_write",
    "folder_name",
    "preview_name",
    "preview_names",
    "validate_parent",
    "validate_parts",
    "validate_suffix",
    "validate_target",
]

NOTES_NAME = "descricao.md"
FINGERPRINT_KEY = "fingerprint"
_SUFFIX = re.compile(r"[A-Za-z0-9._-]+")


class CreateError(Exception):
    """Why the folder was not created (Portuguese); nothing was left behind."""


@dataclass(frozen=True)
class Created:
    folder: Path
    files: tuple[Path, ...]
    renamed_from: str | None = None  # the name asked for, when it was taken (a ``_N`` was added)


def folder_name(
    type_: CalcType,
    suffix: str,
    number: int | None = None,
    inherited: str = "",
    tag: str = "",
) -> str:
    """``Bands_Al`` (``Bands`` with no name); with ``number``, ``2_Bands_Al`` (spec 51). The SCF
    folder's ``inherited`` suffix and the site ``tag`` come after the name, the tag last (spec 77)."""
    parts = [type_.folder_prefix, suffix.strip(), inherited.strip(), tag.strip()]
    name = "_".join(part for part in parts if part)
    return name if number is None else f"{number}_{name}"


def _asked(
    parent: Path, type_: CalcType, suffix: str, numbered: bool, inherited: str, tag: str
) -> str:
    """The name asked for; ``numbered``, after the folders ``parent`` holds now."""
    return folder_name(type_, suffix, next_number(parent) if numbered else None, inherited, tag)


def validate_suffix(suffix: str) -> list[str]:
    """What is wrong with the name typed for the folder ([] = nothing; it may be empty)."""
    suffix = suffix.strip()
    if suffix and (not _SUFFIX.fullmatch(suffix) or suffix in (".", "..")):
        return [_("Use só letras sem acento, números, ponto, hífen e sublinhado no nome")]
    return []


def validate_parent(parent: Path) -> list[str]:
    """What keeps the folder from being created in ``parent`` ([] = nothing). Only ``stat``s."""
    if not parent.is_dir():
        return [_("A pasta {parent} não existe").format(parent=parent)]
    if not os.access(parent, os.W_OK | os.X_OK):
        return [_("Sem permissão de escrita em {parent}").format(parent=parent)]
    return []


def validate_parts(inherited: str = "", tag: str = "") -> list[str]:
    """What is wrong with the suffix taken from the SCF's folder and the site tag (spec 77)."""
    if inherited.strip() and validate_suffix(inherited):
        return [_("O sufixo da pasta do SCF tem caracteres que o nome da pasta não aceita")]
    return validate_suffix(tag)


def validate_target(parent: Path, suffix: str, inherited: str = "", tag: str = "") -> list[str]:
    """What keeps the folder from being created ([] = it can be). Only ``stat``s, no reading."""
    return validate_suffix(suffix) + validate_parts(inherited, tag) + validate_parent(parent)


def preview_names(
    parent: Path,
    type_: CalcType,
    suffix: str,
    numbered: bool = False,
    inherited: str = "",
    tag: str = "",
) -> tuple[str, str]:
    """The name asked for and the one ``create_folder`` would use now: ``Bands_Al`` and
    ``Bands_Al_1`` if ``Bands_Al`` exists. ``numbered``, both carry the number ``parent`` gives now
    (one listing); the folder takes it again when it is made."""
    asked = _asked(parent, type_, suffix, numbered, inherited, tag)
    return asked, next_free_dir(parent / asked).name


def preview_name(
    parent: Path,
    type_: CalcType,
    suffix: str,
    numbered: bool = False,
    inherited: str = "",
    tag: str = "",
) -> str:
    """The name ``create_folder`` would use now (``Bands_Al_1`` if ``Bands_Al`` exists)."""
    return preview_names(parent, type_, suffix, numbered, inherited, tag)[1]


def files_to_write(plan: CalcPlan, notes: str, fingerprint: str | None = None) -> list[PlannedFile]:
    """The plan's files plus ``descricao.md`` when the notes hold text and ``fingerprint.md`` when
    ``fingerprint`` (its text, spec 80) is given (the "Arquivos" tab)."""
    files = list(plan.files)
    if notes.strip():
        text = notes if notes.endswith("\n") else notes + "\n"
        files.append(PlannedFile(NOTES_NAME, "notes", text, _("Descrição"), "notes"))
    if fingerprint is not None:
        files.append(
            PlannedFile(FINGERPRINT_NAME, "notes", fingerprint, _("Fingerprint"), FINGERPRINT_KEY)
        )
    return files


def _check_names(files: Sequence[PlannedFile]) -> None:
    seen: set[str] = set()
    for planned in files:
        name = planned.name
        if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
            raise CreateError(_("Nome de arquivo inválido: {name!r}").format(name=name))
        if name in seen:
            raise CreateError(_("Arquivo repetido no plano: {name}").format(name=name))
        seen.add(name)


def _remove(created: list[Path], folder: Path) -> None:
    for path in reversed(created):
        with contextlib.suppress(OSError):
            path.unlink()
    with contextlib.suppress(OSError):
        folder.rmdir()  # only if empty: never what someone else put there


def create_folder(
    parent: Path,
    type_: CalcType,
    suffix: str,
    plan: CalcPlan,
    notes: str = "",
    numbered: bool = False,
    inherited: str = "",
    tag: str = "",
    fingerprint: Sequence[Source] | None = None,
    root: Path | None = None,
) -> Created:
    """Create the folder and write the plan (and ``descricao.md``) into it. Raises
    ``CreateError``; on failure, removes the files it wrote and the folder it made. ``numbered``:
    the number is the one ``parent`` gives at this moment, not the one the preview showed.
    ``fingerprint`` (None: no file; spec 80) adds ``fingerprint.md`` with these SCFs, shown
    relative to ``root`` (default ``parent``), written with the folder's final name."""
    problems = validate_target(parent, suffix, inherited, tag)
    if problems:
        raise CreateError(problems[0])
    if plan.errors:
        raise CreateError(plan.errors[0])
    files = files_to_write(plan, notes, "" if fingerprint is not None else None)
    _check_names(files)
    asked = _asked(parent, type_, suffix, numbered, inherited, tag)
    try:
        folder = make_new_dir(parent / asked)
    except OSError as exc:
        raise CreateError(
            _("Não foi possível criar a pasta {asked}: {value}").format(
                asked=asked, value=exc.strerror or exc
            )
        ) from exc
    written: list[Path] = []
    try:
        if fingerprint is not None:  # the final name and now, which only the worker knows
            text = fingerprint_text(type_, folder.name, fingerprint, root or parent, datetime.now())
            files = [
                dataclasses.replace(planned, text=text)
                if planned.key == FINGERPRINT_KEY
                else planned
                for planned in files
            ]
        for planned in files:
            path = folder / planned.name
            with open(path, "x", encoding="utf-8", newline="") as handle:
                written.append(path)
                handle.write(planned.text)
    except (OSError, UnicodeError) as exc:
        _remove(written, folder)
        name = getattr(exc, "filename", None) or folder.name
        reason = getattr(exc, "strerror", None) or exc
        raise CreateError(
            _("Não foi possível gravar {name}: {reason}").format(
                name=Path(name).name, reason=reason
            )
        ) from exc
    except BaseException:
        _remove(written, folder)
        raise
    renamed = asked if folder.name != asked else None
    return Created(folder, tuple(written), renamed)
