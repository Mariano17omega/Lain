"""Relaxamento: the SCF with ``calculation = 'relax'`` or ``'vc-relax'`` (spec 95), ``nstep``,
``forc_conv_thr``, ``&IONS`` and, for a vc-relax, ``&CELL``.

One type with a "Cálculo" field: the input is ``relax_<prefix>.in`` or ``vc-relax_<prefix>.in``, as
chosen. Its key (``INPUT_KEY``, also the group of its fields) is ``relax`` either way, in every type
that derives from it (Slab, Supercélula, Molécula na superfície).
"""

from __future__ import annotations

from typing import Any, ClassVar

from ....i18n import _
from ...qe.input_edit import RESTART_COMMENT, InputEditor
from ..edits import put_comment, put_mesh, put_number, put_string
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field, scf_number
from .files import InputFile, pw_input
from .vc_relax import VC_RELAX, cell_fields, put_cell

INPUT_KEY = "relax"  # the key of the input and the group of its fields
CALCULATION = "calculation"  # the id of the "Cálculo" field
DEFAULT_NSTEP = 100  # pw.x's is 50, short for a slab with an adsorbate
DEFAULT_FORC_CONV_THR = 1.0e-3  # Ry/Bohr, pw.x's
ION_DYNAMICS = ("bfgs", "damp")


class RelaxType(CalcType):
    id: ClassVar[str] = "relax"
    label: ClassVar[str] = _("Relaxamento")
    folder_prefix: ClassVar[str] = "Relax"
    script_stem: ClassVar[str] = "relax"
    script_template: ClassVar[str] = "qsub/relax.qsub.j2"
    calculations: ClassVar[tuple[str, ...]] = ("relax", VC_RELAX)  # the first is the fallback
    calculation_tooltip: ClassVar[str] = _(
        "relax: só os átomos se movem e a célula fica a do SCF; vc-relax: a célula também relaxa (&CELL)"
    )

    @property
    def chooses(self) -> bool:
        """Whether the type has the "Cálculo" field (more than one calculation to choose from)."""
        return len(self.calculations) > 1

    def default_calculation(self, scf: ScfInfo) -> str:
        return self.calculations[0]

    def chosen(self, work: Work) -> str:
        return work.values.get(CALCULATION) or self.calculations[0]

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        """``relax_<prefix>.in`` or ``vc-relax_<prefix>.in``, as "Cálculo" says."""
        named_by = CALCULATION if self.chooses else ""
        calculation = self.default_calculation(scf)
        return [pw_input(INPUT_KEY, calculation, scf, self.label, named_by)]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {"pw_runs": [work.run(INPUT_KEY)]}

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [*self.choice_fields(scf), *self.relax_fields(scf)]

    def choice_fields(self, scf: ScfInfo) -> list[FormField]:
        """The "Cálculo" field, first of the input's tab (none when there is nothing to choose)."""
        if not self.chooses:
            return []
        return [
            FormField(
                CALCULATION,
                _("Cálculo (calculation)"),
                "choice",
                self.default_calculation(scf),
                group=INPUT_KEY,
                choices=self.calculations,
                standard=True,
                tooltip=self.calculation_tooltip,
            )
        ]

    def relax_fields(self, scf: ScfInfo) -> list[FormField]:
        """k-points, ``nstep``, ``forc_conv_thr``, ``ion_dynamics`` and, when a vc-relax can be
        chosen, the ``&CELL`` fields (shown only for it)."""
        group = INPUT_KEY
        nstep = scf_number(scf, "control", "nstep")
        forc = scf_number(scf, "control", "forc_conv_thr")
        dynamics = (scf.value("ions", "ion_dynamics") or "").strip().lower()
        ion = dynamics if dynamics in ION_DYNAMICS else ION_DYNAMICS[0]
        fields = [
            kmesh_field(scf, group, required=False),
            FormField(
                "nstep",
                _("Passos máximos (nstep)"),
                "int",
                int(nstep) if nstep is not None else DEFAULT_NSTEP,
                group=group,
                standard=True,
                tooltip=_(
                    "&CONTROL nstep: número máximo de passos da otimização. Se acabar sem convergir, "
                    "descomente a linha restart_mode no input e rode de novo, com os mesmos NP e nk"
                ),
            ),
            FormField(
                "forc_conv_thr",
                _("Convergência das forças (forc_conv_thr)"),
                "float",
                forc if forc is not None else DEFAULT_FORC_CONV_THR,
                group=group,
                tooltip=_("&CONTROL forc_conv_thr, em Ry/Bohr"),
            ),
            FormField(
                "ion_dynamics",
                _("Dinâmica dos íons (ion_dynamics)"),
                "choice",
                ion,
                group=group,
                choices=ION_DYNAMICS,
                tooltip="&IONS ion_dynamics",
            ),
        ]
        if VC_RELAX in self.calculations:
            fields += cell_fields(scf, group, ion)
        return fields

    def edit(self, editor: InputEditor, work: Work) -> None:
        """The relax keys; ``&CELL`` only when the choice is vc-relax (a field ``shown_when`` hides
        resolves to its default, so the choice decides, never a None)."""
        values = work.values
        calculation = self.chosen(work)
        put_string(editor, "control", "calculation", calculation)
        if values["nstep"] is not None:
            put_number(editor, "control", "nstep", values["nstep"])
        put_comment(editor, "control", "restart_mode", RESTART_COMMENT)
        if values["forc_conv_thr"] is not None:
            put_number(editor, "control", "forc_conv_thr", values["forc_conv_thr"])
        if values["ion_dynamics"] is not None:
            put_string(editor, "ions", "ion_dynamics", values["ion_dynamics"])
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        if calculation == VC_RELAX:
            put_cell(editor, work)

    def inputs(self, work: Work) -> list[PlannedFile]:
        editor = work.editor()
        self.edit(editor, work)
        return [work.pw_file(INPUT_KEY, editor)]
