"""VC-Relax: the relax plus ``&CELL`` (``cell_dynamics``, ``press``)."""

from __future__ import annotations

from typing import ClassVar

from ...qe.input_edit import InputEditor
from ..edits import put_number, put_string
from ..scf_info import ScfInfo
from .base import FormField, Work
from .relax import RelaxType, _number

CELL_DYNAMICS = ("bfgs", "damp-pr", "damp-w")
DEFAULT_PRESS = 0.0  # kbar


class VcRelaxType(RelaxType):
    id: ClassVar[str] = "vc-relax"
    label: ClassVar[str] = "VC-Relax"
    folder_prefix: ClassVar[str] = "vc-relax"
    script_template: ClassVar[str] = "qsub/vc-relax.qsub.j2"
    calculation: ClassVar[str] = "vc-relax"

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        group = self.input_name
        dynamics = (scf.value("cell", "cell_dynamics") or "").strip().lower()
        press = _number(scf, "cell", "press")
        return [
            *super().input_fields(scf),
            FormField(
                "cell_dynamics",
                "Dinâmica da célula (cell_dynamics)",
                "choice",
                dynamics if dynamics in CELL_DYNAMICS else CELL_DYNAMICS[0],
                group=group,
                choices=CELL_DYNAMICS,
                tooltip="&CELL cell_dynamics",
            ),
            FormField(
                "press",
                "Pressão (press, kbar)",
                "float",
                press if press is not None else DEFAULT_PRESS,
                group=group,
                tooltip="&CELL press: pressão externa alvo, em kbar",
            ),
        ]

    def edit(self, editor: InputEditor, work: Work) -> None:
        super().edit(editor, work)
        values = work.values
        if values["cell_dynamics"] is not None:
            put_string(editor, "cell", "cell_dynamics", values["cell_dynamics"])
        if values["press"] is not None:
            put_number(editor, "cell", "press", values["press"])
