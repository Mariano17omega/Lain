"""PDOS: SCF, NSCF on a mesh and projwfc.x, whose PDOS files go to ``orbitals/`` (PRD §3).

In the ``padrao`` mode only ``Emin`` / ``Emax`` are asked for, and both start empty: projwfc.x then
takes the whole range of the bands (L-10). The NSCF takes the SCF's mesh (asked only when the SCF has
no automatic one), ``nbnd`` and ``occupations`` follow the SCF, and ``&PROJWFC`` has ``DeltaE = 0.01``,
``filpdos = '<prefix>.dat'`` and, unless the NSCF uses tetrahedra (spec 27-1), ``ngauss = 0``,
``degauss = 0.000735`` Ry (≈ 0.01 eV), which replace the smearing of pw.x.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any, ClassVar

from ....i18n import _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..edits import ensure_disk_io, ensure_smearing, put_mesh, put_number, put_string
from ..render import render
from ..scf_info import ScfInfo
from ..unit import UNIT_OUTDIR
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field, nbnd_field
from .files import InputFile, pw_input
from .scf import KEY as SCF_KEY
from .scf import scf_input

NSCF = "nscf"  # key
PROJWFC = "projwfc"  # key
PROJWFC_TEMPLATE = "qe/pdos/projwfc.in.j2"
DEFAULT_DELTA_E = 0.01
DEFAULT_DEGAUSS = 0.000735  # Ry, ≈ 0.01 eV (spec 28 R3.4)
DEFAULT_NGAUSS = 0
OCCUPATIONS = ("smearing", "tetrahedra", "tetrahedra_opt", "tetrahedra_lin", "fixed")
DEFAULT_OCCUPATIONS = "tetrahedra"
NO_BROADENING_NOTE = _(
    "projwfc.in sem ngauss/degauss: com tetraedros o projwfc.x usa o método dos tetraedros "
    "(um degauss no input o desligaria)"
)
ENERGY_WINDOW_HINT = _(
    "Emin/Emax são energias absolutas em eV (em branco: toda a faixa das bandas calculadas); "
    "acima da energia da última banda calculada (nbnd) a DOS é zero. Aumente nbnd ou reduza Emax"
)
WHOLE_RANGE_HINT = _("vazio = toda a faixa das bandas")  # the placeholder of Emin / Emax
TETRA_OPT_DEGAUSS = _(
    "projwfc.in com degauss e NSCF com occupations = 'tetrahedra_opt': o projwfc.x segue pelo ramo "
    "dos tetraedros sem tê-los inicializado. Tire o degauss ou troque as ocupações"
)


def _occupations(scf: ScfInfo) -> str:
    if scf.occupations is None:
        return "fixed"  # pw.x's default, kept as the SCF has it
    return scf.occupations if scf.occupations in OCCUPATIONS else DEFAULT_OCCUPATIONS


def _projwfc(
    key: str, label: str, kind, default, tooltip: str, standard: bool = False, hint: str = ""
) -> FormField:
    return FormField(
        key,
        label,
        kind,
        default,
        group=PROJWFC,
        tooltip=f"&PROJWFC {tooltip}",
        standard=standard,
        hint=hint,
    )


class PdosType(CalcType):
    id: ClassVar[str] = "pdos"
    label: ClassVar[str] = "PDOS"
    folder_prefix: ClassVar[str] = "PDOS"
    script_stem: ClassVar[str] = "pdos"
    script_template: ClassVar[str] = "qsub/pdos.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PROJWFC_TEMPLATE,)

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        return [
            scf_input(scf),
            pw_input(NSCF, "nscf", scf, "NSCF"),
            InputFile(PROJWFC, "projwfc.in"),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {"pw_runs": [work.run(SCF_KEY), work.run(NSCF)], "projwfc": work.run(PROJWFC)}

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        # The NSCF's mesh is the SCF's; asked in the "padrao" mode only when the SCF has none.
        mesh = dataclasses.replace(
            kmesh_field(scf, NSCF, required=True), standard=scf.kmesh is None
        )
        return [
            nbnd_field(scf, NSCF, ENERGY_WINDOW_HINT),
            FormField(
                "occupations",
                _("Ocupações (occupations)"),
                "choice",
                _occupations(scf),
                group=NSCF,
                choices=OCCUPATIONS,
                tooltip=(
                    _(
                        "&SYSTEM occupations do NSCF (tetraedros dão uma DOS mais limpa; com "
                        "tetraedros o projwfc.in sai sem ngauss/degauss, e o projwfc.x usa o "
                        "método dos tetraedros)"
                    )
                ),
            ),
            mesh,
            _projwfc(
                "delta_e", _("Passo de energia (DeltaE, eV)"), "float", DEFAULT_DELTA_E, "DeltaE"
            ),
            _projwfc(
                "e_min",
                _("Energia mínima (Emin, eV)"),
                "float",
                None,
                "Emin",
                standard=True,
                hint=WHOLE_RANGE_HINT,
            ),
            _projwfc(
                "e_max",
                _("Energia máxima (Emax, eV)"),
                "float",
                None,
                f"Emax: {ENERGY_WINDOW_HINT}",
                standard=True,
                hint=WHOLE_RANGE_HINT,
            ),
            _projwfc(
                "degauss",
                _("Alargamento (degauss, Ry)"),
                "float",
                DEFAULT_DEGAUSS,
                _(
                    "degauss (em Ry; 0.000735 Ry ≈ 0.01 eV): substitui o smearing do pw.x; "
                    "ignorado com tetraedros"
                ),
            ),
            _projwfc(
                "ngauss",
                _("Tipo de alargamento (ngauss)"),
                "int",
                DEFAULT_NGAUSS,
                _("ngauss: substitui o do pw.x; ignorado com tetraedros"),
            ),
            _projwfc(
                "filpdos",
                _("Prefixo dos arquivos PDOS (filpdos)"),
                "text",
                f"{scf.prefix}.dat",
                _("filpdos: os arquivos são <filpdos>.pdos_atm#…"),
            ),
        ]

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        editor = work.editor()
        put_string(editor, "control", "calculation", "nscf")
        occupations = values["occupations"]
        if occupations is not None and not (occupations == "fixed" and scf.occupations is None):
            put_string(editor, "system", "occupations", occupations)
        if occupations == "smearing":
            work.notes.extend(
                f"{work.name(NSCF)}: {note}"
                for note in ensure_smearing(editor, replace_tetrahedra=False)
            )
        if values["nbnd"] is not None:
            put_number(editor, "system", "nbnd", values["nbnd"])
        nscf = work.name(NSCF)
        work.notes.extend(f"{nscf}: {note}" for note in ensure_disk_io(editor, "projwfc.x"))
        scf_editor = work.editor()
        scf_name = work.name(SCF_KEY)
        work.notes.extend(f"{scf_name}: {note}" for note in ensure_disk_io(scf_editor))
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        e_min, e_max = values["e_min"], values["e_max"]
        if e_min is not None and e_max is not None and e_min >= e_max:
            work.errors.append(_("Emin deve ser menor que Emax"))
        broadening = not (occupations or "").startswith("tetrahedra")
        if not broadening:
            work.notes.append(NO_BROADENING_NOTE)
        projwfc = render(
            PROJWFC_TEMPLATE,
            {
                "prefix": scf.prefix,
                "outdir": UNIT_OUTDIR,
                "delta_e": _or(values["delta_e"], DEFAULT_DELTA_E),
                "filpdos": values["filpdos"] or f"{scf.prefix}.dat",
                "e_min": e_min,
                "e_max": e_max,
                "broadening": broadening,
                "ngauss": _or(values["ngauss"], DEFAULT_NGAUSS),
                "degauss": _or(values["degauss"], DEFAULT_DEGAUSS),
            },
        )
        return [
            work.pw_file(SCF_KEY, scf_editor),
            work.pw_file(NSCF, editor),
            work.planned(PROJWFC, "qe_input", projwfc),
        ]

    def text_errors(self, files: Sequence[PlannedFile]) -> list[str]:
        """``tetrahedra_opt`` in the NSCF and a ``degauss`` in the projwfc.in, as written (an edit by
        hand: the form never makes it): ``partialdos.f90:84`` takes the tetrahedron branch whatever
        ``degauss`` is, and ``projwfc.f90`` has not set the tetrahedra up (L-10)."""
        by_key = {planned.key: planned for planned in files}
        nscf, projwfc = by_key.get(NSCF), by_key.get(PROJWFC)
        if nscf is None or projwfc is None:
            return []
        occupations = InputEditor.from_text(nscf.text).get("system", "occupations") or ""
        degauss = fortran_float(InputEditor.from_text(projwfc.text).get("projwfc", "degauss") or "")
        if occupations.strip().lower() == "tetrahedra_opt" and degauss:
            return [TETRA_OPT_DEGAUSS]
        return []


def _or(value: Any, default: Any) -> Any:
    return value if value is not None else default
