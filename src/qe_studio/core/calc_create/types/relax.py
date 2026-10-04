"""Relax: the SCF with ``calculation = 'relax'``, ``nstep``, ``forc_conv_thr`` and ``&IONS``."""

from __future__ import annotations

from typing import ClassVar

from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..edits import put_mesh, put_number, put_string
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field

DEFAULT_NSTEP = 50  # pw.x's for relaxations
DEFAULT_FORC_CONV_THR = 1.0e-3  # Ry/Bohr, pw.x's
ION_DYNAMICS = ("bfgs", "damp")


def _number(scf: ScfInfo, namelist: str, key: str) -> float | None:
    text = scf.value(namelist, key)
    return fortran_float(text) if text is not None else None


class RelaxType(CalcType):
    id: ClassVar[str] = "relax"
    label: ClassVar[str] = "Relax"
    folder_prefix: ClassVar[str] = "relax"
    script_template: ClassVar[str] = "qsub/relax.qsub.j2"
    calculation: ClassVar[str] = "relax"

    @property
    def input_name(self) -> str:
        return f"{self.calculation}.in"

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        group = self.input_name
        nstep = _number(scf, "control", "nstep")
        forc = _number(scf, "control", "forc_conv_thr")
        dynamics = (scf.value("ions", "ion_dynamics") or "").strip().lower()
        return [
            kmesh_field(scf, group, required=False),
            FormField(
                "nstep",
                "Passos máximos (nstep)",
                "int",
                int(nstep) if nstep is not None else DEFAULT_NSTEP,
                group=group,
                tooltip="&CONTROL nstep: número máximo de passos da otimização",
            ),
            FormField(
                "forc_conv_thr",
                "Convergência das forças (forc_conv_thr)",
                "float",
                forc if forc is not None else DEFAULT_FORC_CONV_THR,
                group=group,
                tooltip="&CONTROL forc_conv_thr, em Ry/Bohr",
            ),
            FormField(
                "ion_dynamics",
                "Dinâmica dos íons (ion_dynamics)",
                "choice",
                dynamics if dynamics in ION_DYNAMICS else ION_DYNAMICS[0],
                group=group,
                choices=ION_DYNAMICS,
                tooltip="&IONS ion_dynamics",
            ),
        ]

    def edit(self, editor: InputEditor, work: Work) -> None:
        """The relax keys; the vc-relax adds ``&CELL``."""
        values = work.values
        put_string(editor, "control", "calculation", self.calculation)
        if values["nstep"] is not None:
            put_number(editor, "control", "nstep", values["nstep"])
        if values["forc_conv_thr"] is not None:
            put_number(editor, "control", "forc_conv_thr", values["forc_conv_thr"])
        if values["ion_dynamics"] is not None:
            put_string(editor, "ions", "ion_dynamics", values["ion_dynamics"])
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)

    def inputs(self, work: Work) -> list[PlannedFile]:
        editor = work.editor()
        self.edit(editor, work)
        name = self.input_name
        return [PlannedFile(name, "pw_input", work.finish(editor, name), f"{self.label} ({name})")]
