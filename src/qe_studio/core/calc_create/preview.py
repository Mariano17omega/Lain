"""What the "Criar cálculo" window shows (spec 26): the name the folder will get, the lines of a
derived input that differ from the SCF, the rows of the "Arquivos" tab and the notice after the
folder is created. The window only lays these out."""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..file_kinds import human_size
from .kpath import KMesh
from .types.base import CalcType, PlannedFile
from .writer import Created, folder_name, preview_name

__all__ = [
    "FILE_KINDS",
    "OUTSIDE_PROJECT",
    "FileRow",
    "changed_lines",
    "created_notice",
    "field_text",
    "file_rows",
    "mesh_summary",
    "outside_project",
    "target_text",
]

FILE_KINDS = {
    "qsub": "Script SGE",
    "pw_input": "Input do pw.x",
    "qe_input": "Input do QE",
    "notes": "Anotações",
}
OUTSIDE_PROJECT = (
    "Fora da pasta do projeto: a detecção e a sincronização só enxergam pastas dentro dela"
)


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
        return "Vazio: mantém o K_POINTS do SCF"
    n1, n2, n3 = mesh.n
    return f"{n1}×{n2}×{n3} = {mesh.count} k-points na rede (o pw.x reduz pela simetria)"


def file_rows(files: Sequence[PlannedFile]) -> list[FileRow]:
    return [
        FileRow(f.name, FILE_KINDS.get(f.kind, f.kind), human_size(len(f.text.encode("utf-8"))))
        for f in files
    ]


def target_text(parent: Path, type_: CalcType, suffix: str) -> str:
    """ "Será criada: bandas_Al", or the ``_N`` name and why. Only ``stat``s."""
    asked = folder_name(type_, suffix)
    name = preview_name(parent, type_, suffix)
    if name == asked:
        return f"Será criada: {name}"
    return f"Será criada: {name} — já existe {asked}"


def outside_project(parent: Path, root: Path) -> bool:
    try:
        return not parent.resolve().is_relative_to(root.resolve())
    except OSError:
        return True


PUSH_REMINDER = "Use ‘Enviar ao cluster’ para levar a pasta ao cluster"


def created_notice(created: Created, sync: bool = False) -> tuple[str, str]:
    """The toast of a created folder: its text and its "Detalhes". With ``sync`` (sync is
    configured) the text ends reminding of "Enviar ao cluster" (spec 26 R5.3, spec 27)."""
    count = len(created.files)
    noun = "arquivo" if count == 1 else "arquivos"
    text = f"Pasta {created.folder.name} criada com {count} {noun}"
    if sync:
        text += f". {PUSH_REMINDER}"
    details = [str(created.folder), *(f"  {path.name}" for path in created.files)]
    if created.renamed_from:
        details.append(f"{created.renamed_from} já existia: criada como {created.folder.name}")
    return text, "\n".join(details)
