"""Supercélula: the SCF's structure repeated n1 × n2 × n3, as a relax or a vc-relax (spec 41, 95).

Stage 2 of the user's scripts (``qe_slab_supercell.generate_supercell``): the SCF is usually a relaxed
surface's (the vacuum along c), but a bulk's works too; only the defaults change (``cell_dofree``, the
fixed atoms, and the calculation: a relax for a surface, a vc-relax with ``cell_dofree = 'all'`` for a
bulk). The geometry is ``surface/`` (``make_supercell``, ``fixed_atoms``, ``rescale_mesh``); this module
reads the fields, writes the input (``relax_<prefix>.in`` or ``vc-relax_<prefix>.in``,
``prefix = '<prefix>-<n1>x<n2>x<n3>'``, ``nbnd``, ``tot_charge`` and ``tot_magnetization`` times the
copies) and ``geracao.md``. The plan always has its three files: when the structure cannot be built, the
input is the SCF with the relaxation's edits and the report says why.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from ....i18n import N_, _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import UNSET_MAGNETIZATION, fortran_float
from ..edits import put_mesh, put_number, put_string, put_text
from ..fragments import WHOLE_SYSTEM_KEYS
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.fixing import BOTTOM, FIX_RULES, FROM_SCF, NONE, apply_fix
from ..surface.geometry import MIN_SURFACE_GAP, vacuum_gaps
from ..surface.kmesh import mesh_text, rescale_mesh, uneven_axes
from ..surface.model import Model, model_of, partly_fixed, species_rows
from ..surface.report import decimal, report_file
from ..surface.supercell import AXIS_NAMES, make_supercell, repeat_problem, size_problem
from ..surface.write import put_structure
from .base import FieldKind, FormField, PlannedFile, Work
from .dipole_fields import DIPFIELD, apply_dipole, chosen_edir, corrects, dipole_fields
from .relax import INPUT_KEY, RelaxType
from .slab import NO_MESH
from .slab_fields import (
    SURFACE_CALCULATION_TOOLTIP,
    asks_mesh,
    calculation_fact,
    dofree_field,
    mesh_field,
    non_orthogonal_notes,
)
from .surface_fields import (
    BOND_SCALE,
    BY_SPECIES,
    FIX_RULE,
    bond_scale_field,
    check_positive,
    counts,
    fix_fields,
    fixed_fact,
    fixed_for,
)
from .vc_relax import VC_RELAX

__all__ = ["GROUP", "REPEATS", "SupercellType", "has_vacuum"]

GROUP = N_("Supercélula")  # no file is named so: a tab of its own, before the input's
REPEATS = ("n1", "n2", "n3")
DEFAULT_REPEATS = (2, 1, 1)  # SUPERCELL_MULT = 2 of the scripts, along a
DEFAULT_VACUUM_MIN = 10.5  # Å, VACUUM_MIN of the scripts
MESH_HINT = _("Vazio = a do SCF dividida pelas repetições, arredondada para cima")
UNEVEN_MESH_NOTE = _(
    "Rede de k-points ao longo de {axis}: {n} não divide por {multiple}, "
    "fica {result} (mais densa que a do SCF)"
)
GAMMA_NOTE = _("K_POINTS gamma do SCF mantido: confira se basta para a supercélula")
STACKED_NOTE = _("Repetir ao longo do vácuo (c) empilha slabs: o vácuo entre eles não muda")
LOW_VACUUM = _("Vácuo de {} Å ao longo de c, abaixo do mínimo de {} Å")
BULK_NOTE = _("SCF sem vácuo: supercélula de bulk, cell_dofree = '{}'")
EXTENSIVE_NOTE = _("{key} multiplicado pelas cópias da célula: {change}")
STACKED_DIPOLE = _(
    "Com n{n} = {copies} a célula se repete {copies} vezes ao longo de edir = {n}, e a rampa só corrige um vácuo: desmarque dipfield ou use n{n} = 1"
)
Facts = list[tuple[str, str]]  # the lines of geracao.md


def has_vacuum(scf: ScfInfo) -> bool:
    """Whether the SCF is a surface: an empty gap of at least ``MIN_SURFACE_GAP`` along c."""
    crystal = scf.crystal
    return crystal is not None and vacuum_gaps(crystal.cell, crystal.frac)[2] >= MIN_SURFACE_GAP


def _default_dofree(scf: ScfInfo) -> str:
    return "2Dxy" if has_vacuum(scf) else "all"


def _default_rule(scf: ScfInfo) -> str:
    """ "do SCF" when the SCF fixes some atom but not all; else the bottom half of a surface; none for
    a bulk."""
    if partly_fixed(scf.text):
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


class SupercellType(RelaxType):
    id: ClassVar[str] = "supercell"
    label: ClassVar[str] = _("Supercélula")
    folder_prefix: ClassVar[str] = "Supercell"
    script_stem: ClassVar[str] = "supercell"
    script_template: ClassVar[str] = "qsub/relax.qsub.j2"
    scf_label: ClassVar[str] = _("SCF da superfície (ou do bulk)")
    writes_report: ClassVar[bool] = True
    calculation_tooltip: ClassVar[str] = SURFACE_CALCULATION_TOOLTIP

    def default_calculation(self, scf: ScfInfo) -> str:
        """A surface keeps its plane (relax); a bulk relaxes its cell, as before (spec 95 R4.1)."""
        return "relax" if has_vacuum(scf) else VC_RELAX

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        relax = [form_field for form_field in self.relax_fields(scf) if form_field.id != "kmesh"]
        # A bulk has no vacuum for the ramp: no field, and its text keeps whatever it writes.
        dipole = dipole_fields(scf) if has_vacuum(scf) else []
        return [
            *self._supercell_fields(scf),
            *self.choice_fields(scf),
            *dipole,
            mesh_field(INPUT_KEY, MESH_HINT, _("da supercélula"), standard=asks_mesh(scf)),
            *relax,
            dofree_field(INPUT_KEY, _default_dofree(scf)),
        ]

    def _supercell_fields(self, scf: ScfInfo) -> list[FormField]:
        repeats = [
            _field(
                field_id,
                _("Repetições ao longo de {axis}").format(axis=axis),
                "int",
                default,
                _("Cópias da célula do SCF ao longo de {axis} (1 a 8)").format(axis=axis),
                standard=True,
            )
            for field_id, axis, default in zip(REPEATS, AXIS_NAMES, DEFAULT_REPEATS, strict=True)
        ]
        fields = [
            *repeats,
            *fix_fields(GROUP, FIX_RULES, _default_rule(scf)),
            bond_scale_field(GROUP, BY_SPECIES),  # only that rule reads bonds here
        ]
        if has_vacuum(scf):  # a bulk has no vacuum to check
            fields.append(
                _field(
                    "vacuum_min",
                    _("Vácuo mínimo (Å)"),
                    "float",
                    DEFAULT_VACUUM_MIN,
                    _("Só verifica: abaixo dele ao longo de c, o plano avisa (a célula não muda)"),
                )
            )
        return fields

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        calculation = self.chosen(work)
        dofree = values["cell_dofree"] or _default_dofree(scf)
        vc = calculation == VC_RELAX
        facts: Facts = [(_("SCF de origem"), scf.name), calculation_fact(calculation, dofree)]
        repeats = self._repeats(work)
        editor = work.editor()
        built: tuple[Model, bool] | None = None
        if repeats is not None:
            facts.append((_("Repetições"), " × ".join(str(n) for n in repeats)))
            try:
                built = self._structure(work, editor, repeats, dofree if vc else None, facts)
            except SurfaceError as exc:
                work.errors.append(str(exc))
                facts.append((_("Estrutura não gerada"), str(exc)))
        self.edit(editor, work)
        if vc:
            put_string(editor, "cell", "cell_dofree", dofree)
        if has_vacuum(scf):
            self._dipole(work, editor, repeats, built, facts, vc)
        if repeats is not None:
            put_text(editor, "control", "prefix", f"{scf.prefix}-{'x'.join(map(str, repeats))}")
            self._nbnd(scf, editor, repeats, facts)
            self._extensive(work, editor, repeats, facts)
            self._kpoints(work, editor, repeats, facts)
        return [work.pw_file(INPUT_KEY, editor), report_file(facts)]

    # -- the pieces of ``inputs`` ------------------------------------------------------------------
    def _dipole(
        self,
        work: Work,
        editor: InputEditor,
        repeats: tuple[int, int, int] | None,
        built: tuple[Model, bool] | None,
        facts: Facts,
        vc: bool,
    ) -> None:
        """The correction of the supercell's own vacuum: copies along the field's direction stack
        slabs, each with a vacuum of its own, and one ramp corrects only one of them (spec 98 R4)."""
        edir = chosen_edir(work)
        if corrects(work) and repeats is not None and edir and repeats[edir - 1] > 1:
            work.problem(DIPFIELD, STACKED_DIPOLE.format(n=edir, copies=repeats[edir - 1]))
            return
        model, one_side = built if built is not None else (None, False)
        apply_dipole(work, editor, model, facts, vc=vc, polar=one_side)

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
            grown = [f for f, value in zip(REPEATS, repeats, strict=True) if value > 1]
            for field_id in grown or REPEATS[:1]:  # at 1 × 1 × 1 the SCF alone is too big
                work.problem(field_id, problem)
            return None
        return repeats

    def _structure(
        self,
        work: Work,
        editor: InputEditor,
        repeats: tuple[int, int, int],
        dofree: str | None,
        facts: Facts,
    ) -> tuple[Model, bool]:
        """The repeated structure; ``dofree`` is the vc-relax's ``cell_dofree`` (None: a relax, whose
        cell nothing constrains). Returns it and whether one side is fixed (the bottom half)."""
        scf = work.scf
        vacuum = has_vacuum(scf)
        model = make_supercell(model_of(scf), repeats)
        rule = work.values[FIX_RULE] or _default_rule(scf)
        scale = check_positive(work, BOND_SCALE, _("A tolerância de ligação")) or 1.0
        fix = fixed_for(work, model, rule, scale)
        model = apply_fix(model, fix, rule) if fix is not None else model
        work.notes.extend(put_structure(editor, model, species_rows(scf.text)))
        gap = vacuum_gaps(model.cell, model.frac)[2]
        if vacuum:
            self._vacuum_notes(work, gap, repeats)
        if dofree is not None:
            if not vacuum:
                work.notes.append(BULK_NOTE.format(dofree))
            work.notes.extend(non_orthogonal_notes(dofree, model.cell))
        lengths = "; ".join(decimal(float(np.linalg.norm(row)), 3) for row in model.cell)
        facts += [
            (_("Átomos"), f"{len(model)} ({counts(model.labels)})"),
            ("|a|, |b|, |c|", f"{lengths} Å"),
            (
                _("Vácuo medido"),
                _("{decimal} Å ao longo de c").format(decimal=decimal(gap))
                if vacuum
                else _("sem vácuo (bulk)"),
            ),
        ]
        if fix is not None:
            facts.append(fixed_fact(model.labels, fix, rule))
        return model, rule == BOTTOM and fix is not None and bool(fix.indices)

    def _vacuum_notes(self, work: Work, gap: float, repeats: tuple[int, int, int]) -> None:
        minimum = check_positive(work, "vacuum_min", _("O vácuo mínimo"))
        if minimum is not None and gap < minimum:
            work.notes.append(LOW_VACUUM.format(decimal(gap, 1), decimal(minimum, 1)))
        if repeats[2] > 1:
            work.notes.append(STACKED_NOTE)

    def _nbnd(
        self, scf: ScfInfo, editor: InputEditor, repeats: tuple[int, int, int], facts: Facts
    ) -> None:
        if scf.nbnd is None:
            facts.append(("nbnd", _("não definido no SCF (o padrão do pw.x)")))
            return
        nbnd = scf.nbnd * int(np.prod(repeats))
        put_number(editor, "system", "nbnd", nbnd)
        facts.append(("nbnd", f"{scf.nbnd} → {nbnd}"))

    def _extensive(
        self, work: Work, editor: InputEditor, repeats: tuple[int, int, int], facts: Facts
    ) -> None:
        """What holds for the whole cell grows with the copies; ``tot_magnetization`` at pw.x's
        "not set" (-10000) stays, but any other value, a negative one included, is a constraint."""
        copies = int(np.prod(repeats))
        for key in WHOLE_SYSTEM_KEYS:
            value = fortran_float(editor.get("system", key) or "")
            if (
                copies == 1
                or not value
                or (key == "tot_magnetization" and value <= UNSET_MAGNETIZATION)
            ):
                continue
            put_number(editor, "system", key, value * copies)
            change = f"{value:g} → {value * copies:g}"
            facts.append((key, change))
            work.notes.append(EXTENSIVE_NOTE.format(key=key, change=change))

    def _kpoints(
        self, work: Work, editor: InputEditor, repeats: tuple[int, int, int], facts: Facts
    ) -> None:
        scf, typed = work.scf, work.values.get("kmesh")
        if typed is not None:  # written by ``edit``
            facts.append(("k-points", _("{mesh} (digitada)").format(mesh=mesh_text(typed))))
        elif scf.kmesh is not None:
            if has_vacuum(scf):
                axes, mults, vacuum = {0: 0, 1: 1}, {0: repeats[0], 1: repeats[1]}, 2
                how = _("÷ repetições; vácuo 1")
            else:
                axes, mults, vacuum = {0: 0, 1: 1, 2: 2}, dict(enumerate(repeats)), None
                how = _("÷ repetições")
            mesh = rescale_mesh(scf.kmesh, axes, mults, vacuum_axis=vacuum)
            for uneven in uneven_axes(scf.kmesh, axes, mults, vacuum_axis=vacuum):
                work.notes.append(
                    UNEVEN_MESH_NOTE.format(
                        axis=AXIS_NAMES[uneven.axis],
                        n=uneven.n,
                        multiple=uneven.multiple,
                        result=uneven.result,
                    )
                )
            put_mesh(editor, mesh)
            facts.append(
                (
                    "k-points",
                    _("{mesh} (do SCF {scf}, {how})").format(
                        mesh=mesh_text(mesh), scf=mesh_text(scf.kmesh), how=how
                    ),
                )
            )
        elif scf.kpoints_option == "gamma":
            work.notes.append(GAMMA_NOTE)
            facts.append(("k-points", _("gamma (do SCF)")))
        else:
            work.problem("kmesh", NO_MESH)
