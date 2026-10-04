"""PDOS: SCF, NSCF on a mesh and projwfc.x, whose PDOS files go to ``orbitals/`` (PRD §3)."""

from __future__ import annotations

from typing import ClassVar

from ..edits import ensure_smearing, put_mesh, put_number, put_string
from ..render import render
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import check_mesh, kmesh_field, nbnd_field

SCF = "scf.in"
NSCF = "nscf.in"
PROJWFC = "projwfc.in"
PROJWFC_TEMPLATE = "qe/pdos/projwfc.in.j2"
OCCUPATIONS = ("smearing", "tetrahedra", "tetrahedra_opt", "tetrahedra_lin", "fixed")
DEFAULT_OCCUPATIONS = "tetrahedra"


def _occupations(scf: ScfInfo) -> str:
    if scf.occupations is None:
        return "fixed"  # pw.x's default, kept as the SCF has it
    return scf.occupations if scf.occupations in OCCUPATIONS else DEFAULT_OCCUPATIONS


def _projwfc(group: str, key: str, label: str, kind, default, tooltip: str) -> FormField:
    return FormField(key, label, kind, default, group=group, tooltip=f"&PROJWFC {tooltip}")


class PdosType(CalcType):
    id: ClassVar[str] = "pdos"
    label: ClassVar[str] = "PDOS"
    folder_prefix: ClassVar[str] = "pdos"
    script_template: ClassVar[str] = "qsub/pdos.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PROJWFC_TEMPLATE,)

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [
            nbnd_field(scf, NSCF),
            FormField(
                "occupations",
                "Ocupações (occupations)",
                "choice",
                _occupations(scf),
                group=NSCF,
                choices=OCCUPATIONS,
                tooltip="&SYSTEM occupations do NSCF (tetraedros dão uma DOS mais limpa)",
            ),
            kmesh_field(scf, NSCF, required=True),
            _projwfc(PROJWFC, "delta_e", "Passo de energia (DeltaE, eV)", "float", 0.01, "DeltaE"),
            _projwfc(PROJWFC, "e_min", "Energia mínima (Emin, eV)", "float", -25.0, "Emin"),
            _projwfc(PROJWFC, "e_max", "Energia máxima (Emax, eV)", "float", 25.0, "Emax"),
            _projwfc(PROJWFC, "degauss", "Alargamento (degauss, Ry)", "float", 0.01, "degauss"),
            _projwfc(PROJWFC, "ngauss", "Tipo de alargamento (ngauss)", "int", 0, "ngauss"),
            _projwfc(
                PROJWFC,
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
            work.notes.extend(
                f"{NSCF}: {note}" for note in ensure_smearing(editor, replace_tetrahedra=False)
            )
        if values["nbnd"] is not None:
            put_number(editor, "system", "nbnd", values["nbnd"])
        mesh = check_mesh(work)
        if mesh is not None:
            put_mesh(editor, mesh)
        e_min, e_max = values["e_min"], values["e_max"]
        if e_min is not None and e_max is not None and e_min >= e_max:
            work.errors.append("Emin deve ser menor que Emax")
        projwfc = render(
            PROJWFC_TEMPLATE,
            {
                "prefix": scf.prefix,
                "outdir": scf.outdir,
                "delta_e": values["delta_e"] if values["delta_e"] is not None else 0.01,
                "filpdos": values["filpdos"] or f"{scf.prefix}.dat",
                "e_min": e_min if e_min is not None else -25.0,
                "e_max": e_max if e_max is not None else 25.0,
                "ngauss": values["ngauss"] if values["ngauss"] is not None else 0,
                "degauss": values["degauss"] if values["degauss"] is not None else 0.01,
            },
        )
        return [
            PlannedFile(SCF, "pw_input", scf.text, f"SCF ({SCF})"),
            PlannedFile(NSCF, "pw_input", work.finish(editor, NSCF), f"NSCF ({NSCF})"),
            PlannedFile(PROJWFC, "qe_input", projwfc, PROJWFC),
        ]
