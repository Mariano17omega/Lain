"""VC-Relax: the relax plus ``&CELL`` (``cell_dynamics``, ``press``)."""

from __future__ import annotations

import dataclasses
from typing import ClassVar

from ....i18n import _
from ...qe.input_edit import InputEditor
from ..edits import put_number, put_string
from ..scf_info import ScfInfo
from .base import FormField, Work
from .relax import ION_DYNAMICS, RelaxType, _number

CELL_DYNAMICS = ("bfgs", "damp-pr", "damp-w")
BFGS = "bfgs"
DEFAULT_PRESS = 0.0  # kbar


def dynamics_problem(ion: str, cell: str) -> str | None:
    """Why pw.x refuses this pair (``INPUT_PW``: ``bfgs`` on one side needs it on the other), or None."""
    if (ion == BFGS) == (cell == BFGS):
        return None
    return _(
        "ion_dynamics = '{ion}' não combina com cell_dynamics = '{cell}': o pw.x exige 'bfgs' nos dois ou em nenhum"
    ).format(ion=ion, cell=cell)


class VcRelaxType(RelaxType):
    id: ClassVar[str] = "vc-relax"
    label: ClassVar[str] = "VC-Relax"
    folder_prefix: ClassVar[str] = "VC-Relax"
    script_stem: ClassVar[str] = "vc-relax"
    script_template: ClassVar[str] = "qsub/vc-relax.qsub.j2"
    calculation: ClassVar[str] = "vc-relax"

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        group = self.calculation
        dynamics = (scf.value("cell", "cell_dynamics") or "").strip().lower()
        press = _number(scf, "cell", "press")
        relax = super().input_fields(scf)
        cell = dynamics if dynamics in CELL_DYNAMICS else CELL_DYNAMICS[0]
        ion = next(form_field.default for form_field in relax if form_field.id == "ion_dynamics")
        if dynamics_problem(ion, cell) is not None:
            # A pair of the SCF that does not go together must not block what Padrão hides.
            cell = BFGS
            relax = [
                dataclasses.replace(form_field, default=ION_DYNAMICS[0])
                if form_field.id == "ion_dynamics"
                else form_field
                for form_field in relax
            ]
        return [
            *relax,
            FormField(
                "cell_dynamics",
                _("Dinâmica da célula (cell_dynamics)"),
                "choice",
                cell,
                group=group,
                choices=CELL_DYNAMICS,
                tooltip="&CELL cell_dynamics",
            ),
            FormField(
                "press",
                _("Pressão (press, kbar)"),
                "float",
                press if press is not None else DEFAULT_PRESS,
                group=group,
                tooltip=_("&CELL press: pressão externa alvo, em kbar"),
            ),
        ]

    def edit(self, editor: InputEditor, work: Work) -> None:
        super().edit(editor, work)
        values = work.values
        if values["cell_dynamics"] is not None:
            put_string(editor, "cell", "cell_dynamics", values["cell_dynamics"])
            if values["ion_dynamics"] is not None:
                problem = dynamics_problem(values["ion_dynamics"], values["cell_dynamics"])
                if problem is not None:
                    work.problem("cell_dynamics", problem)
        if values["press"] is not None:
            put_number(editor, "cell", "press", values["press"])
