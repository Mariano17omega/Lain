"""``view3d.plot``: the views of the 3D windows of one folder, a section per file (spec 47 R1.3).

A member of the ``<kind>.plot`` family (``lain_plot: 1``, ``kind: view3d``, read by
``plot_file.read_plot_file``) whose ``params`` map a file name (``scf.in``) to its section
(``view_state.session_of``). The key is the name, not the path: the file lives in the folder whose
``plots/`` holds the ``view3d.plot``, so a moved or renamed folder takes its views along.

Writing touches only its own section: the others stay as they were read (order and unknown keys), and an
unreadable file or one of another version is replaced, like ``write_plot_file`` does with a ``.plot``. A
folder that is gone is never created again (``atomic_write_text`` would make it and its ``plots/``:
a window closed after its folder was renamed would leave a ghost folder under the old name). Nothing
here raises: what went wrong comes back as a sentence for the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ...i18n import _
from ..appdirs import atomic_write_text
from ..plotting.plot_file import FORMAT_VERSION, plot_file_path, read_plot_file
from .model import Structure
from .source import read_structure

__all__ = [
    "HEADER",
    "VIEW_KIND",
    "LoadedView",
    "load_view",
    "read_session",
    "remove_session",
    "view_file_path",
    "write_session",
]

log = logging.getLogger(__name__)

VIEW_KIND = "view3d"
HEADER = _(
    "# Lain: ajustes da visualização 3D, uma seção por arquivo. "
    "Gerado automaticamente; apague para voltar aos padrões.\n"
)


@dataclass(frozen=True)
class LoadedView:
    """What the worker of a new window reads: the structure and the file's section (None: defaults)."""

    structure: Structure
    session: dict[str, Any] | None
    warnings: list[str]


def view_file_path(folder: str | Path) -> Path:
    return plot_file_path(Path(folder), VIEW_KIND)


def read_session(folder: str | Path, name: str) -> tuple[dict[str, Any] | None, list[str]]:
    """(the section of ``name`` or None, the warnings of ``read_plot_file``). No file, no section or a
    section that is not a mapping is None; only an unreadable file or another version warns."""
    sections, warnings = read_plot_file(Path(folder), VIEW_KIND)
    session = sections.get(name) if sections is not None else None
    return (session if isinstance(session, dict) else None), warnings


def load_view(path: str | Path) -> LoadedView:
    """Worker of ``Structure3DController.open``: the structure (a ``StructureReadError`` goes up as it
    did) and then the section of the file in its folder's ``view3d.plot``."""
    path = Path(path)
    structure = read_structure(path)
    session, warnings = read_session(path.parent, path.name)
    return LoadedView(structure, session, warnings)


def _reason(exc: BaseException) -> str:
    return (exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)) or type(
        exc
    ).__name__


def _dump(sections: dict[Any, Any]) -> str:
    data = {"lain_plot": FORMAT_VERSION, "kind": VIEW_KIND, "params": sections}
    return HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def write_session(folder: str | Path, name: str, session: dict[str, Any]) -> str | None:
    """Put ``session`` as the section of ``name``; None when written, else the warning for the user."""
    folder = Path(folder)
    if not folder.is_dir():
        return _(
            "A pasta {name} não existe mais: a vista de {name_2} não foi salva em {name_3}."
        ).format(name=folder.name, name_2=name, name_3=view_file_path(folder).name)
    sections, _warnings = read_plot_file(folder, VIEW_KIND)  # unreadable: replaced
    sections = dict(sections) if sections is not None else {}
    sections[name] = session  # in place when it was there, else at the end
    path = view_file_path(folder)
    try:
        atomic_write_text(path, _dump(sections))
    except (OSError, yaml.YAMLError) as exc:
        log.warning("writing %s failed: %s", path, exc)
        return _("Não foi possível salvar {name} em {folder}: {reason}").format(
            name=path.name, folder=folder, reason=_reason(exc)
        )
    return None


def remove_session(folder: str | Path, name: str) -> str | None:
    """Take the section of ``name`` out ("Restaurar padrões", spec 47 R3.5); the file goes when it was the
    last one. Nothing to remove (no folder, file or section; an unreadable file) creates or rewrites
    nothing and is None; only a failed rewrite or removal warns."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    sections, _warnings = read_plot_file(folder, VIEW_KIND)
    if sections is None or name not in sections:
        return None
    rest = {key: value for key, value in sections.items() if key != name}
    path = view_file_path(folder)
    try:
        if rest:
            atomic_write_text(path, _dump(rest))
        else:
            path.unlink(missing_ok=True)
    except (OSError, yaml.YAMLError) as exc:
        log.warning("updating %s failed: %s", path, exc)
        return _("Não foi possível atualizar {name} em {folder}: {reason}").format(
            name=path.name, folder=folder, reason=_reason(exc)
        )
    return None
