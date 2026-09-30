"""File operations started from the context menu. Nothing here ever overwrites (PRD §7)."""

from __future__ import annotations

import errno
import sys
from pathlib import Path

if sys.platform == "win32":
    _SEPARATORS, _SEPARATOR_ERROR = ("/", "\\"), "O nome não pode conter “/” nem “\\”."
else:
    _SEPARATORS, _SEPARATOR_ERROR = ("/",), "O nome não pode conter “/”."


def _taken(path: Path, target: Path) -> bool:
    """Is ``target`` another item? A case-only rename on a case-insensitive disk is not."""
    if not (target.exists() or target.is_symlink()):
        return False
    try:
        return not (target.name.casefold() == path.name.casefold() and target.samefile(path))
    except OSError:
        return True


def rename_error(path: Path, name: str) -> str | None:
    """Why ``path`` cannot be renamed to ``name`` (None if it can, or if the name is unchanged)."""
    if not name.strip():
        return "Digite um nome."
    if name == path.name:
        return None
    if any(sep in name for sep in _SEPARATORS):
        return _SEPARATOR_ERROR
    if "\0" in name or name in (".", ".."):
        return "Nome inválido."
    if _taken(path, path.with_name(name)):
        return f"Já existe “{name}” nesta pasta."
    return None


def rename_item(path: Path, name: str) -> Path:
    """Rename ``path`` in place. Raises ``OSError`` (``FileExistsError`` if the name is taken)."""
    target = path.with_name(name)
    if (error := rename_error(path, name)) is not None:
        code = errno.EEXIST if _taken(path, target) else errno.EINVAL
        raise OSError(code, error, str(target))  # OSError(EEXIST, …) is a FileExistsError
    path.rename(target)
    return target
