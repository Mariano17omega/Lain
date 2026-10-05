"""What makes a generated folder a self-contained simulation unit (spec 28 R2).

Every pw.x input of the folder writes its data to ``./tmp/`` inside it (``outdir``), and reads the
pseudopotentials from ``jobs.pseudo_dir`` (the cluster's folder, from ``config.yaml``) when it is set;
otherwise the SCF's ``pseudo_dir`` stays and a note says how to fix it. Paths the folder does not
control are notes, never errors.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..config import JobsConfig
from ..qe.input_edit import InputEditor
from .edits import put_text

if TYPE_CHECKING:
    from .scf_info import ScfInfo

__all__ = [
    "OUTSIDE",
    "PSEUDO_DIR_NOTE",
    "UNIT_OUTDIR",
    "absolute",
    "apply_unit",
    "climbs",
    "unit_notes",
]

UNIT_OUTDIR = "./tmp/"
PSEUDO_DIR_NOTE = "Defina jobs.pseudo_dir no config.yaml para fixar os pseudopotenciais"
OUTSIDE = "O SCF usa um caminho fora da pasta: {}"


def apply_unit(editor: InputEditor, jobs: JobsConfig) -> None:
    """``outdir = './tmp/'`` and, when the config has one, its ``pseudo_dir``."""
    put_text(editor, "control", "outdir", UNIT_OUTDIR)
    if jobs.pseudo_dir is not None:
        put_text(editor, "control", "pseudo_dir", jobs.pseudo_dir)


def absolute(path: str) -> bool:
    """Whether ``path`` starts outside the folder: ``/``, ``~`` or a variable."""
    return PurePosixPath(path).is_absolute() or path.startswith(("~", "$"))


def climbs(path: str) -> bool:
    """Whether ``path`` has a ``..`` part."""
    return ".." in PurePosixPath(path).parts


def unit_notes(scf: ScfInfo, jobs: JobsConfig) -> list[str]:
    """The notes of the paths a generated input keeps from the SCF."""
    notes = []
    pseudo = scf.pseudo_dir
    if jobs.pseudo_dir is None:
        notes.append(PSEUDO_DIR_NOTE)
        if pseudo is None:
            notes.append("sem pseudo_dir: o pw.x procura os pseudopotenciais em $ESPRESSO_PSEUDO")
        elif climbs(pseudo):
            notes.append(OUTSIDE.format(f"pseudo_dir = {pseudo}"))
        elif not absolute(pseudo):
            notes.append(
                f"pseudo_dir relativo ({pseudo}): confira se ele vale a partir da pasta nova"
            )
    wfcdir = (scf.value("control", "wfcdir") or "").strip()
    if wfcdir and (absolute(wfcdir) or climbs(wfcdir)):
        notes.append(OUTSIDE.format(f"wfcdir = {wfcdir}"))
    return notes
