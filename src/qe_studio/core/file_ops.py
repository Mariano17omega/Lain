"""File operations started from the context menu. Nothing here ever overwrites (PRD §7)."""

from __future__ import annotations

import ctypes
import errno
import os
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


def _same_item(path: Path, target: Path) -> bool:
    """``target`` is ``path`` under another spelling (``a.txt`` / ``A.txt`` on a case-insensitive
    disk). An item created there meanwhile is another one: it must not take this branch."""
    try:
        return target != path and target.samefile(path)
    except OSError:  # no such item (the usual case)
        return False


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


def overlaps(a: Path, b: Path) -> bool:
    """Is one of the two paths the other or inside it (a sync of ``a`` and a rename of ``b``)?"""
    return a.is_relative_to(b) or b.is_relative_to(a)


_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
# What a filesystem or a libc without RENAME_NOREPLACE answers (a missing symbol is AttributeError).
_NO_NOREPLACE = (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP)


def _exists_error(dst: Path) -> OSError:
    return OSError(errno.EEXIST, f"Já existe “{dst.name}” nesta pasta.", str(dst))


def _renameat2(src: Path, dst: Path) -> None:
    """Linux ``renameat2(..., RENAME_NOREPLACE)``: the kernel refuses an existing ``dst`` in the
    same step that moves ``src``, so nothing that appears after the check is overwritten."""
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.renameat2(
        _AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE
    )
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(dst))


def _link_then_unlink(src: Path, dst: Path) -> None:
    """A file moves as ``link`` (fails if ``dst`` exists) + ``unlink``: never overwrites."""
    os.link(src, dst, follow_symlinks=False)  # a symlink moves as the link itself
    try:
        os.unlink(src)
    except OSError:
        os.unlink(dst)  # keep one name, the old one
        raise


def _checked_rename(src: Path, dst: Path) -> None:
    """Check, then ``rename``. A name that shows up between the two is overwritten (POSIX):
    only a directory or a filesystem without hard links gets here."""
    if dst.exists() or dst.is_symlink():
        raise _exists_error(dst)
    src.rename(dst)


def _rename_noreplace(src: Path, dst: Path) -> None:
    """Move ``src`` to ``dst`` without ever replacing an existing item (spec 27-3 R5)."""
    if sys.platform == "win32":
        os.rename(src, dst)  # already refuses an existing destination
        return
    if sys.platform.startswith("linux"):
        try:
            _renameat2(src, dst)
            return
        except AttributeError:  # glibc < 2.28
            pass
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise _exists_error(dst) from exc
            if exc.errno not in _NO_NOREPLACE:
                raise
    if src.is_dir() and not src.is_symlink():
        _checked_rename(src, dst)
        return
    try:
        _link_then_unlink(src, dst)
    except FileExistsError as exc:
        raise _exists_error(dst) from exc
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EMLINK):
            raise
        _checked_rename(src, dst)  # no hard links here (FAT, some network disks)


def rename_item(path: Path, name: str) -> Path:
    """Rename ``path`` in place. Raises ``OSError`` (``FileExistsError`` if the name is taken,
    even when it was taken after the check: the move itself refuses to replace it)."""
    target = path.with_name(name)
    if (error := rename_error(path, name)) is not None:
        code = errno.EEXIST if _taken(path, target) else errno.EINVAL
        raise OSError(code, error, str(target))  # OSError(EEXIST, …) is a FileExistsError
    if _same_item(path, target):
        path.rename(target)  # the case of a name on a case-insensitive disk: nothing to replace
    else:
        _rename_noreplace(path, target)
    return target
