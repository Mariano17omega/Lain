"""The ``&CELL`` of a vc-relax (spec 95 R1.3): ``cell_dynamics`` and ``press``, shown only when the
"Cálculo" of a relaxation is ``vc-relax``, and the pair of dynamics pw.x accepts.

pw.x reads ``&CELL`` only in a ``vc-*`` calculation (``read_namelists.f90``): a relax keeps the
input's cell, so ``&CELL`` is written only for a vc-relax.
"""

from __future__ import annotations

from ....i18n import _
from ...qe.input_edit import InputEditor
from ..edits import put_number, put_string
from ..scf_info import ScfInfo
from .base import FormField, Work
from .fields import scf_number

__all__ = [
    "BFGS",
    "CELL_DYNAMICS",
    "DEFAULT_PRESS",
    "VC_ONLY",
    "VC_RELAX",
    "cell_fields",
    "default_cell",
    "dynamics_problem",
    "put_cell",
]

VC_RELAX = "vc-relax"
CELL_DYNAMICS = ("bfgs", "damp-pr", "damp-w")
BFGS = "bfgs"
DAMPED = "damp-pr"  # the first damped one of INPUT_PW, for a damped ion_dynamics
DEFAULT_PRESS = 0.0  # kbar
VC_ONLY: tuple[tuple[str, tuple[object, ...]], ...] = (("calculation", (VC_RELAX,)),)


def dynamics_problem(ion: str, cell: str) -> str | None:
    """Why pw.x refuses this pair (``INPUT_PW``: ``bfgs`` on one side needs it on the other), or None."""
    if (ion == BFGS) == (cell == BFGS):
        return None
    return _(
        "ion_dynamics = '{ion}' não combina com cell_dynamics = '{cell}': o pw.x exige 'bfgs' nos dois ou em nenhum"
    ).format(ion=ion, cell=cell)


def default_cell(scf: ScfInfo, ion: str) -> str:
    """The SCF's ``cell_dynamics`` when it goes with ``ion`` (the ``ion_dynamics`` default), else the
    one that does: a vc-relax of the ``padrao`` mode, which hides both, never starts blocked."""
    dynamics = (scf.value("cell", "cell_dynamics") or "").strip().lower()
    cell = dynamics if dynamics in CELL_DYNAMICS else CELL_DYNAMICS[0]
    if dynamics_problem(ion, cell) is None:
        return cell
    return BFGS if ion == BFGS else DAMPED


def cell_fields(scf: ScfInfo, group: str, ion_default: str) -> list[FormField]:
    """``cell_dynamics`` and ``press``, shown only for a vc-relax."""
    press = scf_number(scf, "cell", "press")
    return [
        FormField(
            "cell_dynamics",
            _("Dinâmica da célula (cell_dynamics)"),
            "choice",
            default_cell(scf, ion_default),
            group=group,
            choices=CELL_DYNAMICS,
            tooltip="&CELL cell_dynamics",
            shown_when=VC_ONLY,
        ),
        FormField(
            "press",
            _("Pressão (press, kbar)"),
            "float",
            press if press is not None else DEFAULT_PRESS,
            group=group,
            tooltip=_("&CELL press: pressão externa alvo, em kbar"),
            shown_when=VC_ONLY,
        ),
    ]


def put_cell(editor: InputEditor, work: Work) -> None:
    """``&CELL`` of a vc-relax, and the problem of a pair pw.x refuses (marked on ``cell_dynamics``)."""
    values = work.values
    if values["cell_dynamics"] is not None:
        put_string(editor, "cell", "cell_dynamics", values["cell_dynamics"])
        if values["ion_dynamics"] is not None:
            problem = dynamics_problem(values["ion_dynamics"], values["cell_dynamics"])
            if problem is not None:
                work.problem("cell_dynamics", problem)
    if values["press"] is not None:
        put_number(editor, "cell", "press", values["press"])
