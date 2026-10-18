"""What the "Criar cálculo" window shows (spec 26): the name the folder will get, the lines of a
derived input that differ from the SCF, the rows of the "Arquivos" tab and the notice after the
folder is created. The window only lays these out."""

from __future__ import annotations

import difflib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...i18n import _, ngettext
from ..file_kinds import human_size
from .kpath import KMesh
from .types.base import CalcType, PlannedFile
from .writer import Created, preview_names

__all__ = [
    "AT_ROOT",
    "EDITED_MARK",
    "FILE_KINDS",
    "OUTSIDE_PROJECT",
    "FileRow",
    "at_root",
    "changed_lines",
    "created_notice",
    "field_text",
    "file_rows",
    "location_warnings",
    "mesh_summary",
    "outside_project",
    "target_text",
]

FILE_KINDS = {
    "qsub": _("Script SGE"),
    "pw_input": _("Input do pw.x"),
    "qe_input": _("Input do QE"),
    "notes": _("Anotações"),
    "report": _("Relatório"),
}
OUTSIDE_PROJECT = _(
    "Fora da pasta raiz: a detecção e a sincronização só enxergam pastas dentro dela"
)
AT_ROOT = _(
    "A pasta será criada fora de um projeto e aparecerá como um projeto novo."
)  # spec 31 R6.2
# After the tab label and the kind of a file edited by hand (spec 39 R2.4).
EDITED_MARK = " (editado)"


@dataclass(frozen=True)
class FileRow:
    name: str
    kind: str
    size: str


def changed_lines(original: str, text: str) -> list[int]:
    """The lines of ``text`` (0-based) that are not lines of ``original``: replaced or inserted."""
    old, new = original.splitlines(), text.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    lines: list[int] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            lines.extend(range(j1, j2))
    return lines


def field_text(value: Any) -> str:
    """A field's value as its line edit shows it (and its "vazio = …" hint)."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, KMesh):
        return " ".join(str(v) for v in (*value.n, *value.shift))
    if isinstance(value, int | float | str):
        return str(value)
    return ""


def mesh_summary(mesh: KMesh | None) -> str:
    """The size of a mesh, as a rough hint: pw.x keeps only the points symmetry leaves."""
    if mesh is None:
        return _("Vazio: mantém o K_POINTS do SCF")
    n1, n2, n3 = mesh.n
    return _("{n1}×{n2}×{n3} = {count} k-points na rede (o pw.x reduz pela simetria)").format(
        n1=n1, n2=n2, n3=n3, count=mesh.count
    )


def file_rows(files: Sequence[PlannedFile], edited: Collection[str] = ()) -> list[FileRow]:
    """The rows of the "Arquivos" tab; the files whose key is in ``edited`` say so in their kind."""
    return [
        FileRow(
            f.name,
            FILE_KINDS.get(f.kind, f.kind) + (EDITED_MARK if f.key and f.key in edited else ""),
            human_size(len(f.text.encode("utf-8"))),
        )
        for f in files
    ]


def target_text(parent: Path, type_: CalcType, suffix: str, numbered: bool = False) -> str:
    """ "Será criada: Bands_Al" (``2_Bands_Al`` numbered: spec 51), or the ``_N`` name and why.
    Only ``stat``s, and lists ``parent`` when numbered."""
    asked, name = preview_names(parent, type_, suffix, numbered)
    if name == asked:
        return _("Será criada: {name}").format(name=name)
    return _("Será criada: {name} — já existe {asked}").format(name=name, asked=asked)


def outside_project(parent: Path, root: Path) -> bool:
    try:
        return not parent.resolve().is_relative_to(root.resolve())
    except OSError:
        return True


def at_root(parent: Path, root: Path) -> bool:
    """Whether ``parent`` is the root folder itself: a folder made there is a project (spec 31)."""
    try:
        return parent.resolve() == root.resolve()
    except OSError:
        return False


def location_warnings(parent: Path, root: Path) -> tuple[str, ...]:
    """The amber notes of a place for the new folder (it may still be created)."""
    if outside_project(parent, root):
        return (OUTSIDE_PROJECT,)
    return (AT_ROOT,) if at_root(parent, root) else ()


PUSH_REMINDER = _("Use ‘Enviar ao cluster’ para levar a pasta ao cluster")


def created_notice(created: Created, sync: bool = False) -> tuple[str, str]:
    """The toast of a created folder: its text and its "Detalhes". With ``sync`` (sync is
    configured) the text ends reminding of "Enviar ao cluster" (spec 26 R5.3, spec 27)."""
    count = len(created.files)
    text = ngettext(
        "Pasta {name} criada com {count} arquivo", "Pasta {name} criada com {count} arquivos", count
    ).format(name=created.folder.name, count=count)
    if sync:
        text += f". {PUSH_REMINDER}"
    details = [str(created.folder), *(f"  {path.name}" for path in created.files)]
    if created.renamed_from:
        details.append(
            _("{renamed_from} já existia: criada como {name}").format(
                renamed_from=created.renamed_from, name=created.folder.name
            )
        )
    return text, "\n".join(details)
