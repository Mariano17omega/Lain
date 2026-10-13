"""Slab: the bulk's SCF with one axis stretched to open vacuum, as a vc-relax (spec 40).

Stage 1 of the user's scripts (``qe_slab_surface.generate_surface``): no Miller plane is cut, the bulk
cell keeps its layer and one axis grows until the vacuum above it is the one asked for (the minimum,
plus the height of a molecule and the adsorption distance when the molecule's SCF is given). The
geometry is ``surface/`` (``make_slab``, ``fixed_atoms``, ``rescale_mesh``); this module reads the
fields, writes the input (``vc-relax_<prefix>.in``, ``prefix = '<prefix>-slab-<hkl>'``,
``cell_dofree``) and ``geracao.md``. The plan always has its three files: when the structure cannot be
built, the input is the SCF with the vc-relax edits and the report says why.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from ...qe.input_edit import InputEditor
from ..edits import put_mesh, put_string, put_text
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.fixing import BOTTOM, FixResult, apply_fix
from ..surface.geometry import MIN_SURFACE_GAP, vacuum_gaps
from ..surface.kmesh import mesh_text, rescale_mesh
from ..surface.model import Model, model_of, species_rows
from ..surface.molecule import Molecule, molecule_of
from ..surface.report import decimal, report_file
from ..surface.slab import AXES, HKL, NEED_O_H, NO_BULK_H, SlabOptions, SlabResult, make_slab
from ..surface.write import put_structure
from .base import FormField, PlannedFile, Work
from .slab_fields import (
    AXIS_OF,
    COMPLETE_LABEL,
    DEFAULT_CELL_DOFREE,
    METALS_LABEL,
    dofree_field,
    mesh_field,
    non_orthogonal_notes,
    surface_fields,
)
from .surface_fields import (
    BOND_SCALE,
    FIX_RULE,
    MOLECULE,
    check_labels,
    check_positive,
    counts,
    fixed_fact,
    fixed_for,
    labels_of,
)
from .vc_relax import VcRelaxType

__all__ = ["SlabType"]

NO_MOLECULE_NOTE = "Sem molécula: o vácuo é o mínimo"
NO_MESH = "Preencha a rede de k-points: o SCF não tem K_POINTS automatic"
GAMMA_NOTE = "K_POINTS gamma do SCF mantido: confira se basta para a célula do slab"
FIELD_OF_ERROR = {NEED_O_H: "complete", NO_BULK_H: "complete"}  # the field a SurfaceError marks
Facts = list[tuple[str, str]]  # the lines of geracao.md


class SlabType(VcRelaxType):
    id: ClassVar[str] = "slab"
    label: ClassVar[str] = "Slab"
    folder_prefix: ClassVar[str] = "Slab"
    script_stem: ClassVar[str] = "slab"
    script_template: ClassVar[str] = "qsub/vc-relax.qsub.j2"
    scf_label: ClassVar[str] = "SCF do bulk"
    writes_report: ClassVar[bool] = True

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        group = self.calculation
        relax = [form_field for form_field in super().input_fields(scf) if form_field.id != "kmesh"]
        return [*surface_fields(), mesh_field(group), *relax, dofree_field(group)]

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        axis = AXIS_OF.get(values["axis"] or "", "c")
        facts: Facts = [("SCF de origem", scf.name)]
        options = self._options(work, axis, facts)
        editor = work.editor()
        try:
            self._structure(work, editor, options, facts)
        except SurfaceError as exc:
            field_id = FIELD_OF_ERROR.get(str(exc))
            if field_id is not None:
                work.problem(field_id, str(exc))
            else:
                work.errors.append(str(exc))
            facts.append(("Estrutura não gerada", str(exc)))
        self.edit(editor, work)
        put_string(editor, "cell", "cell_dofree", values["cell_dofree"] or DEFAULT_CELL_DOFREE)
        put_text(editor, "control", "prefix", f"{scf.prefix}-slab-{HKL[axis]}")
        self._kpoints(work, editor, axis, facts)
        return [work.pw_file(self.calculation, editor), report_file(facts)]

    # -- the pieces of ``inputs`` ------------------------------------------------------------------
    def _options(self, work: Work, axis: str, facts: Facts) -> SlabOptions:
        values = work.values
        minimum = check_positive(work, "vacuum_min", "O vácuo mínimo") or 0.0
        distance = check_positive(work, "ads_distance", "A distância de adsorção", True) or 0.0
        scale = check_positive(work, BOND_SCALE, "A tolerância de ligação") or 1.0
        molecule = self._molecule(work, facts)
        if molecule is None:
            vacuum = minimum
            work.notes.append(NO_MOLECULE_NOTE)
            asked = f"{decimal(vacuum)} Å (o vácuo mínimo; sem molécula)"
        else:
            vacuum = minimum + molecule.extent + distance
            asked = (
                f"{decimal(vacuum)} Å = {decimal(minimum)} + molécula {decimal(molecule.extent)} "
                f"+ adsorção {decimal(distance)}"
            )
        facts.append(("Vácuo pedido", asked))
        complete = bool(values["complete"])
        if complete:
            metals = check_labels(work, work.scf, "metals", METALS_LABEL)
        else:
            metals = labels_of(values["metals"])
        return SlabOptions(
            axis=axis,
            flip=bool(values["flip"]),
            vacuum=vacuum,
            heal=bool(values["heal"]),
            complete=complete,
            metals=metals,
            bond_scale=scale,
        )

    def _molecule(self, work: Work, facts: Facts) -> Molecule | None:
        other = work.values.get(MOLECULE)
        if not isinstance(other, ScfInfo):
            return None
        try:
            molecule = molecule_of(other)
        except SurfaceError as exc:
            work.problem(MOLECULE, f"SCF da molécula: {exc}")
            return None
        if other.crystal is not None:
            gap = min(vacuum_gaps(other.crystal.cell, other.crystal.frac))
            if gap < MIN_SURFACE_GAP:
                work.notes.append(
                    f"A molécula de {other.name} não parece isolada: só {decimal(gap, 1)} Å de "
                    "vácuo na caixa dela"
                )
        anchor = f"{molecule.labels[molecule.anchor]}{molecule.anchor + 1}"
        turned = "; girada para o eixo ficar em +z" if molecule.rotated else ""
        facts.append(
            (
                "Molécula",
                f"{other.name}: {counts(molecule.labels)}, altura {decimal(molecule.extent)} Å, "
                f"âncora {anchor}{turned}",
            )
        )
        return molecule

    def _structure(
        self, work: Work, editor: InputEditor, options: SlabOptions, facts: Facts
    ) -> None:
        scf = work.scf
        bulk = model_of(scf)
        stack = AXES[options.axis][1]
        gap = vacuum_gaps(bulk.cell, bulk.frac)[stack]
        if gap >= MIN_SURFACE_GAP:
            work.notes.append(
                f"O SCF já tem {decimal(gap, 1)} Å de vácuo ao longo de {options.axis}: parece uma "
                "superfície"
            )
        result = make_slab(bulk, options, scf.species)
        work.notes.extend(result.notes)
        rule = work.values[FIX_RULE] or BOTTOM
        fix = fixed_for(work, result.model, rule, options.bond_scale)
        model = apply_fix(result.model, fix, rule) if fix is not None else result.model
        work.notes.extend(put_structure(editor, model, species_rows(scf.text)))
        dofree = work.values["cell_dofree"] or DEFAULT_CELL_DOFREE
        work.notes.extend(non_orthogonal_notes(dofree, model.cell))
        work.notes.extend(bond_notes(result, options))
        facts += structure_facts(model, result, options, rule, fix)

    def _kpoints(self, work: Work, editor: InputEditor, axis: str, facts: Facts) -> None:
        scf, typed = work.scf, work.values.get("kmesh")
        if typed is not None:  # written by ``edit``
            facts.append(("k-points", f"{mesh_text(typed)} (digitada)"))
        elif scf.kmesh is not None:
            (first, second), _stack = AXES[axis]
            mesh = rescale_mesh(scf.kmesh, {0: first, 1: second})
            put_mesh(editor, mesh)
            facts.append(
                ("k-points", f"{mesh_text(mesh)} (do SCF {mesh_text(scf.kmesh)}; vácuo 1)")
            )
        elif scf.kpoints_option == "gamma":
            work.notes.append(GAMMA_NOTE)
            facts.append(("k-points", "gamma (do SCF)"))
        else:
            work.problem("kmesh", NO_MESH)


def bond_notes(result: SlabResult, options: SlabOptions) -> list[str]:
    """What the cut leaves open: bonds to O no one closed (none when the cut breaks no bond)."""
    cut = result.cut_bonds
    if not cut:
        return []
    if not options.complete:
        total = sum(cut.values())
        noun = "ligação metal–O cortada" if total == 1 else "ligações metal–O cortadas"
        return [
            f"{total} {noun} na borda ({bond_text(cut)}); marque '{COMPLETE_LABEL}' para fechá-las "
            "com OH"
        ]
    left = [label for label in cut if label not in options.metals]
    if not left:
        return []
    bonds = ", ".join(f"{label}–O" for label in left)
    verb = "não está" if len(left) == 1 else "não estão"
    return [
        f"Ligações {bonds} cortadas não foram completadas: {', '.join(left)} {verb} em "
        f"'{METALS_LABEL}'"
    ]


def structure_facts(
    model: Model, result: SlabResult, options: SlabOptions, rule: str, fix: FixResult | None
) -> Facts:
    """The lines of ``geracao.md`` about the slab; atoms are numbered from 1."""
    labels, cell = model.labels, model.cell
    heights = model.cart[:, 2]
    flip = "invertida" if options.flip else "não invertida"
    lengths = "; ".join(decimal(float(np.linalg.norm(row)), 3) for row in cell)
    facts: Facts = [
        ("Superfície", f"eixo {options.axis} empilhado ({HKL[options.axis]}), {flip}"),
        ("Átomos", f"{len(labels)} ({counts(labels)})"),
        ("|a|, |b|, |c|", f"{lengths} Å"),
        ("Fator f", f"{decimal(result.f, 4)} × eixo {options.axis} do bulk"),
        ("Vácuo medido", f"{decimal(float(cell[2, 2] - np.ptp(heights)))} Å"),
    ]
    if fix is not None:
        facts.append(fixed_fact(labels, fix, rule))
    if result.healed:
        pairs = [
            f"{labels[h.h]}{h.h + 1}–{labels[h.partner]}{h.partner + 1} ({decimal(h.distance, 3)} Å)"
            for h in result.healed
        ]
        facts.append(("H reconectados", ", ".join(pairs)))
    if result.added:
        added = [
            f"{labels[a.metal]}{a.metal + 1}: O{a.oxygen + 1} + H{a.hydrogen + 1} "
            f"({labels[a.metal]}–O {decimal(a.distance, 3)} Å)"
            for a in result.added
        ]
        facts.append(("O + H adicionados", ", ".join(added)))
    if result.cut_bonds:
        facts.append(("Ligações a O cortadas", bond_text(result.cut_bonds)))
    return facts


def bond_text(cut: dict[str, int]) -> str:
    return ", ".join(f"{label} {n}" for label, n in cut.items())
