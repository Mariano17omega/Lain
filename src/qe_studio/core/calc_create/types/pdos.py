"""PDOS: SCF, NSCF on a mesh and projwfc.x, whose PDOS files go to ``orbitals/`` (PRD §3).

In the ``padrao`` mode only ``Emin`` / ``Emax`` are asked for: the NSCF takes the SCF's mesh (asked
only when the SCF has no automatic one), ``nbnd`` and ``occupations`` follow the SCF, and
``&PROJWFC`` has ``DeltaE = 0.01``, ``filpdos = '<prefix>.dat'`` and, unless the NSCF uses
tetrahedra (spec 27-1), ``ngauss = 0``, ``degauss = 0.000735`` Ry (≈ 0.01 eV).
"""

from __future__ import annotations

import dataclasses
from typing import Any, ClassVar

from ..edits import ensure_smearing, put_mesh, put_number, put_string
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
DEFAULT_E_MIN, DEFAULT_E_MAX = -25.0, 25.0
DEFAULT_DEGAUSS = 0.000735  # Ry, ≈ 0.01 eV (spec 28 R3.4)
DEFAULT_NGAUSS = 0
OCCUPATIONS = ("smearing", "tetrahedra", "tetrahedra_opt", "tetrahedra_lin", "fixed")
DEFAULT_OCCUPATIONS = "tetrahedra"
NO_BROADENING_NOTE = (
    "projwfc.in sem ngauss/degauss: com tetraedros o projwfc.x usa o método dos tetraedros "
    "(um degauss no input o desligaria)"
)
ENERGY_WINDOW_HINT = (
    "Emin/Emax são energias absolutas em eV; acima da energia da última banda calculada (nbnd) "
    "a DOS é zero. Aumente nbnd ou reduza Emax"
)


def _occupations(scf: ScfInfo) -> str:
    if scf.occupations is None:
        return "fixed"  # pw.x's default, kept as the SCF has it
    return scf.occupations if scf.occupations in OCCUPATIONS else DEFAULT_OCCUPATIONS


def _projwfc(
    key: str, label: str, kind, default, tooltip: str, standard: bool = False
) -> FormField:
    return FormField(
        key, label, kind, default, group=PROJWFC, tooltip=f"&PROJWFC {tooltip}", standard=standard
    )


class PdosType(CalcType):
    id: ClassVar[str] = "pdos"
    label: ClassVar[str] = "PDOS"
    folder_prefix: ClassVar[str] = "PDOS"
    script_stem: ClassVar[str] = "pdos"
    script_template: ClassVar[str] = "qsub/pdos.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PROJWFC_TEMPLATE,)

    def input_files(self, scf: ScfInfo) -> list[InputFile]:
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
                "Ocupações (occupations)",
                "choice",
                _occupations(scf),
                group=NSCF,
                choices=OCCUPATIONS,
                tooltip=(
                    "&SYSTEM occupations do NSCF (tetraedros dão uma DOS mais limpa; com "
                    "tetraedros o projwfc.in sai sem ngauss/degauss, e o projwfc.x usa o "
                    "método dos tetraedros)"
                ),
            ),
            mesh,
            _projwfc(
                "delta_e", "Passo de energia (DeltaE, eV)", "float", DEFAULT_DELTA_E, "DeltaE"
            ),
            _projwfc(
                "e_min",
                "Energia mínima (Emin, eV)",
                "float",
                DEFAULT_E_MIN,
                "Emin",
                standard=True,
            ),
            _projwfc(
                "e_max",
                "Energia máxima (Emax, eV)",
                "float",
                DEFAULT_E_MAX,
                f"Emax: {ENERGY_WINDOW_HINT}",
                standard=True,
            ),
            _projwfc(
                "degauss",
                "Alargamento (degauss, Ry)",
                "float",
                DEFAULT_DEGAUSS,
                "degauss (em Ry; 0.000735 Ry ≈ 0,01 eV): ignorado com tetraedros",
            ),
            _projwfc(
                "ngauss",
                "Tipo de alargamento (ngauss)",
                "int",
                DEFAULT_NGAUSS,
                "ngauss: ignorado com tetraedros",
            ),
            _projwfc(
                "filpdos",
                "Prefixo dos arquivos PDOS (filpdos)",
                "text",
                f"{scf.prefix}.dat",
                "filpdos: os arquivos são <filpdos>.pdos_atm#…",
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
            nscf = work.name(NSCF)
            work.notes.extend(
                f"{nscf}: {note}" for note in ensure_smearing(editor, replace_tetrahedra=False)
            )
        if values["nbnd"] is not None:
            put_number(editor, "system", "nbnd", values["nbnd"])
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        e_min, e_max = values["e_min"], values["e_max"]
        if e_min is not None and e_max is not None and e_min >= e_max:
            work.errors.append("Emin deve ser menor que Emax")
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
                "e_min": _or(e_min, DEFAULT_E_MIN),
                "e_max": _or(e_max, DEFAULT_E_MAX),
                "broadening": broadening,
                "ngauss": _or(values["ngauss"], DEFAULT_NGAUSS),
                "degauss": _or(values["degauss"], DEFAULT_DEGAUSS),
            },
        )
        return [
            work.pw_file(SCF_KEY, work.editor()),
            work.pw_file(NSCF, editor),
            work.planned(PROJWFC, "qe_input", projwfc),
        ]


def _or(value: Any, default: Any) -> Any:
    return value if value is not None else default
