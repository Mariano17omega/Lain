"""SCF: the SCF itself in a folder of its own (``scf_<prefix>.in`` + ``scf.qsub``)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..edits import put_mesh
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field
from .files import InputFile, pw_input

KEY = "scf"


def scf_input(scf: ScfInfo) -> InputFile:
    """``scf_<prefix>.in``: the SCF of every type that runs one."""
    return pw_input(KEY, "scf", scf, "SCF")


class ScfType(CalcType):
    id: ClassVar[str] = "scf"
    label: ClassVar[str] = "SCF"
    folder_prefix: ClassVar[str] = "SCF"
    script_stem: ClassVar[str] = "scf"
    script_template: ClassVar[str] = "qsub/scf.qsub.j2"

    def input_files(self, scf: ScfInfo, name: str = "") -> list[InputFile]:
        return [scf_input(scf)]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [kmesh_field(scf, KEY, required=False)]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {"pw_runs": [work.run(KEY)]}

    def inputs(self, work: Work) -> list[PlannedFile]:
        editor = work.editor()
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        return [work.pw_file(KEY, editor)]
