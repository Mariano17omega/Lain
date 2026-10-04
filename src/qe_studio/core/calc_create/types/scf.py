"""SCF: the SCF itself in a folder of its own (``scf.in`` + ``scf.qsub``)."""

from __future__ import annotations

from typing import ClassVar

from ..edits import put_mesh
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field

INPUT = "scf.in"


class ScfType(CalcType):
    id: ClassVar[str] = "scf"
    label: ClassVar[str] = "SCF"
    folder_prefix: ClassVar[str] = "scf"
    script_template: ClassVar[str] = "qsub/scf.qsub.j2"

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [kmesh_field(scf, INPUT, required=False)]

    def inputs(self, work: Work) -> list[PlannedFile]:
        editor = work.editor()
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        return [PlannedFile(INPUT, "pw_input", work.finish(editor, INPUT), f"SCF ({INPUT})")]
