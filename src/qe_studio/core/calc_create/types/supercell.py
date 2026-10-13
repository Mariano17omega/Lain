"""Supercélula: the SCF's structure repeated n1 × n2 × n3, as a vc-relax (spec 41).

Stage 2 of the user's scripts (``qe_slab_supercell.generate_supercell``): the SCF is usually a relaxed
surface's (the vacuum along c), but a bulk's works too; only the defaults change (``cell_dofree``, the
fixed atoms). The geometry is ``surface/`` (``make_supercell``, ``fixed_atoms``, ``rescale_mesh``); this
module reads the fields, writes the input (``vc-relax_<prefix>.in``, ``prefix = '<prefix>-<n1>x<n2>x<n3>'``,
``nbnd`` times the copies) and ``geracao.md``. The plan always has its three files: when the structure
cannot be built, the input is the SCF with the vc-relax edits and the report says why.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from ...qe.input_edit import InputEditor
from ..edits import put_mesh, put_number, put_string, put_text
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.fixing import BOTTOM, FIX_RULES, FROM_SCF, NONE, apply_fix
from ..surface.geometry import MIN_SURFACE_GAP, vacuum_gaps
from ..surface.kmesh import mesh_text, rescale_mesh
from ..surface.model import flags_of, model_of, species_rows
from ..surface.report import decimal, report_file
from ..surface.supercell import AXIS_NAMES, make_supercell, repeat_problem, size_problem
from ..surface.write import put_structure
from .base import FieldKind, FormField, PlannedFile, Work
from .slab import NO_MESH
from .slab_fields import dofree_field, mesh_field, non_orthogonal_notes
from .surface_fields import (
    BOND_SCALE,
    FIX_RULE,
    bond_scale_field,
    check_positive,
    counts,
    fix_fields,
    fixed_fact,
    fixed_for,
)
from .vc_relax import VcRelaxType

__all__ = ["GROUP", "REPEATS", "SupercellType", "has_vacuum"]

GROUP = "Supercélula"  # no file is named so: a tab of its own, before the input's
REPEATS = ("n1", "n2", "n3")
DEFAULT_REPEATS = (2, 1, 1)  # SUPERCELL_MULT = 2 of the scripts, along a
DEFAULT_VACUUM_MIN = 10.5  # Å, VACUUM_MIN of the scripts
MESH_HINT = "Vazio = a do SCF dividida pelas repetições"
GAMMA_NOTE = "K_POINTS gamma do SCF mantido: confira se basta para a supercélula"
STACKED_NOTE = "Repetir ao longo do vácuo (c) empilha slabs: o vácuo entre eles não muda"
LOW_VACUUM = "Vácuo de {} Å ao longo de c, abaixo do mínimo de {} Å"
BULK_NOTE = "SCF sem vácuo: supercélula de bulk, cell_dofree = '{}'"
Facts = list[tuple[str, str]]  # the lines of geracao.md


def has_vacuum(scf: ScfInfo) -> bool:
    """Whether the SCF is a surface: an empty gap of at least ``MIN_SURFACE_GAP`` along c."""
    crystal = scf.crystal
    return crystal is not None and vacuum_gaps(crystal.cell, crystal.frac)[2] >= MIN_SURFACE_GAP


def _default_dofree(scf: ScfInfo) -> str:
    return "2Dxy" if has_vacuum(scf) else "all"


def _default_rule(scf: ScfInfo) -> str:
    """ "do SCF" when the SCF fixes some atom; else the bottom half of a surface; none for a bulk."""
    if any(flag is not None and 0 in flag for flag in flags_of(scf.text)):
        return FROM_SCF
    return BOTTOM if has_vacuum(scf) else NONE


def _field(
    field_id: str,
    label: str,
    kind: FieldKind,
    default: object,
    tooltip: str,
    standard: bool = False,
) -> FormField:
    return FormField(
        field_id, label, kind, default, group=GROUP, tooltip=tooltip, standard=standard
    )


class SupercellType(VcRelaxType):
    id: ClassVar[str] = "supercell"
    label: ClassVar[str] = "Supercélula"
    folder_prefix: ClassVar[str] = "Supercell"
    script_stem: ClassVar[str] = "supercell"
    script_template: ClassVar[str] = "qsub/vc-relax.qsub.j2"
    scf_label: ClassVar[str] = "SCF da superfície (ou do bulk)"
    writes_report: ClassVar[bool] = True

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        group = self.calculation
        relax = [form_field for form_field in super().input_fields(scf) if form_field.id != "kmesh"]
        return [
            *self._supercell_fields(scf),
            mesh_field(group, MESH_HINT, "da supercélula"),
            *relax,
            dofree_field(group, _default_dofree(scf)),
        ]

    def _supercell_fields(self, scf: ScfInfo) -> list[FormField]:
        repeats = [
            _field(
                field_id,
                f"Repetições ao longo de {axis}",
                "int",
                default,
                f"Cópias da célula do SCF ao longo de {axis} (1 a 8)",
                standard=True,
            )
            for field_id, axis, default in zip(REPEATS, AXIS_NAMES, DEFAULT_REPEATS, strict=True)
        ]
        return [
            *repeats,
            *fix_fields(GROUP, FIX_RULES, _default_rule(scf)),
            bond_scale_field(GROUP),
            _field(
                "vacuum_min",
                "Vácuo mínimo (Å)",
                "float",
                DEFAULT_VACUUM_MIN,
                "Só verifica: abaixo dele ao longo de c, o plano avisa (a célula não muda)",
            ),
        ]

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        facts: Facts = [("SCF de origem", scf.name)]
        repeats = self._repeats(work)
        dofree = values["cell_dofree"] or _default_dofree(scf)
        editor = work.editor()
        if repeats is not None:
            facts.append(("Repetições", " × ".join(str(n) for n in repeats)))
            try:
                self._structure(work, editor, repeats, dofree, facts)
            except SurfaceError as exc:
                work.errors.append(str(exc))
                facts.append(("Estrutura não gerada", str(exc)))
        self.edit(editor, work)
        put_string(editor, "cell", "cell_dofree", dofree)
        if repeats is not None:
            put_text(editor, "control", "prefix", f"{scf.prefix}-{'x'.join(map(str, repeats))}")
            self._nbnd(scf, editor, repeats, facts)
            self._kpoints(work, editor, repeats, facts)
        return [work.pw_file(self.calculation, editor), report_file(facts)]

    # -- the pieces of ``inputs`` ------------------------------------------------------------------
    def _repeats(self, work: Work) -> tuple[int, int, int] | None:
        """The three repetitions, or None with the problem marked on its field."""
        values = [work.values[field_id] for field_id in REPEATS]
        valid = True
        for axis, (field_id, value) in enumerate(zip(REPEATS, values, strict=True)):
            problem = repeat_problem(axis, value) if value is not None else None
            if problem is not None:
                work.problem(field_id, problem)
            valid = valid and value is not None and problem is None
        if not valid:
            return None
        repeats = (values[0], values[1], values[2])
        crystal = work.scf.crystal
        problem = size_problem(len(crystal.labels), repeats) if crystal is not None else None
        if problem is not None:
            for field_id, value in zip(REPEATS, repeats, strict=True):
                if value > 1:
                    work.problem(field_id, problem)
            return None
        return repeats

    def _structure(
        self,
        work: Work,
        editor: InputEditor,
        repeats: tuple[int, int, int],
        dofree: str,
        facts: Facts,
    ) -> None:
        scf = work.scf
        vacuum = has_vacuum(scf)
        model = make_supercell(model_of(scf), repeats)
        rule = work.values[FIX_RULE] or _default_rule(scf)
        scale = check_positive(work, BOND_SCALE, "A tolerância de ligação") or 1.0
        fix = fixed_for(work, model, rule, scale)
        model = apply_fix(model, fix, rule) if fix is not None else model
        work.notes.extend(put_structure(editor, model, species_rows(scf.text)))
        gap = vacuum_gaps(model.cell, model.frac)[2]
        if vacuum:
            self._vacuum_notes(work, gap, repeats)
        else:
            work.notes.append(BULK_NOTE.format(dofree))
        work.notes.extend(non_orthogonal_notes(dofree, model.cell))
        lengths = "; ".join(decimal(float(np.linalg.norm(row)), 3) for row in model.cell)
        facts += [
            ("Átomos", f"{len(model)} ({counts(model.labels)})"),
            ("|a|, |b|, |c|", f"{lengths} Å"),
            ("Vácuo medido", f"{decimal(gap)} Å ao longo de c" if vacuum else "sem vácuo (bulk)"),
        ]
        if fix is not None:
            facts.append(fixed_fact(model.labels, fix, rule))

    def _vacuum_notes(self, work: Work, gap: float, repeats: tuple[int, int, int]) -> None:
        minimum = check_positive(work, "vacuum_min", "O vácuo mínimo")
        if minimum is not None and gap < minimum:
            work.notes.append(LOW_VACUUM.format(decimal(gap, 1), decimal(minimum, 1)))
        if repeats[2] > 1:
            work.notes.append(STACKED_NOTE)

    def _nbnd(
        self, scf: ScfInfo, editor: InputEditor, repeats: tuple[int, int, int], facts: Facts
    ) -> None:
        if scf.nbnd is None:
            facts.append(("nbnd", "não definido no SCF (o padrão do pw.x)"))
            return
        nbnd = scf.nbnd * int(np.prod(repeats))
        put_number(editor, "system", "nbnd", nbnd)
        facts.append(("nbnd", f"{scf.nbnd} → {nbnd}"))

    def _kpoints(
        self, work: Work, editor: InputEditor, repeats: tuple[int, int, int], facts: Facts
    ) -> None:
        scf, typed = work.scf, work.values.get("kmesh")
        if typed is not None:  # written by ``edit``
            facts.append(("k-points", f"{mesh_text(typed)} (digitada)"))
        elif scf.kmesh is not None:
            if has_vacuum(scf):
                mesh = rescale_mesh(scf.kmesh, {0: 0, 1: 1}, {0: repeats[0], 1: repeats[1]})
                how = "÷ repetições; vácuo 1"
            else:
                axes = {0: 0, 1: 1, 2: 2}
                mesh = rescale_mesh(scf.kmesh, axes, dict(enumerate(repeats)), vacuum_axis=None)
                how = "÷ repetições"
            put_mesh(editor, mesh)
            facts.append(("k-points", f"{mesh_text(mesh)} (do SCF {mesh_text(scf.kmesh)}, {how})"))
        elif scf.kpoints_option == "gamma":
            work.notes.append(GAMMA_NOTE)
            facts.append(("k-points", "gamma (do SCF)"))
        else:
            work.problem("kmesh", NO_MESH)
