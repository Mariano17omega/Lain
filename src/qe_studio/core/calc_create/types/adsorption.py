"""Molécula na superfície: a molecule on one surface atom or between two, as a relax (spec 42).

Stage 3 of the user's scripts (``qe_slab_adsorb``): the SCF is a relaxed surface's (step 1 refuses a
bulk's: ``check_scf``) and a second SCF gives the molecule. The geometry is ``surface/`` (``candidates``
for the table, ``adsorb`` for the site, the H removed and the placement, ``merge`` for the species and
namelists, ``fixed_atoms`` on the surface atoms only); this module reads the fields, writes the input
(``relax_<prefix>.in``, ``prefix = '<surface>-<formula>-<site>'``) and ``geracao.md``. The plan always
has its three files: when the structure cannot be built, the input is the surface's SCF with the relax
edits and the report says why.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from ...qe.input_edit import InputEditor
from ..edits import put_number, put_text
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.adsorb import Adsorbed, SiteError, SiteRequest, adsorb
from ..surface.candidates import candidates_for
from ..surface.fixing import apply_fix
from ..surface.geometry import surface_problem
from ..surface.kmesh import mesh_text
from ..surface.merge import (
    adsorbed_prefix,
    difference_notes,
    formula,
    merge_namelists,
    merge_species,
)
from ..surface.model import Model, model_of, species_rows
from ..surface.molecule import Molecule, molecule_of
from ..surface.report import decimal, report_file
from ..surface.write import put_structure, structure_problem
from .adsorption_fields import (
    BIDENTATE,
    COORDS,
    FROM_COORDS,
    SITE,
    default_rule,
    input_tab_fields,
    molecule_fields,
    site_fields,
    site_rows,
)
from .base import FormField, PlannedFile, Work
from .relax import RelaxType
from .surface_fields import (
    BOND_SCALE,
    FIX_RULE,
    MOLECULE,
    check_positive,
    counts,
    fixed_fact,
    fixed_for,
    labels_of,
)

__all__ = ["AdsorptionType"]

FIELD_OF_ROLE = {  # the field a ``SiteError`` marks
    "selection": SITE,
    "first": COORDS[0],
    "second": COORDS[1],
    "deprotonation": "remove_h",
    "distance": "ads_distance",
    "molecule": MOLECULE,
    "anchor": "anchor",
}
NOT_BUILT = "Estrutura não gerada"
NO_MOLECULE = "falta o SCF da molécula"
FIX_FIELDS = "corrija os campos marcados"
Facts = list[tuple[str, str]]  # the lines of geracao.md


class AdsorptionType(RelaxType):
    id: ClassVar[str] = "adsorption"
    label: ClassVar[str] = "Molécula na superfície"
    folder_prefix: ClassVar[str] = "Adsorption"
    script_stem: ClassVar[str] = "adsorption"
    script_template: ClassVar[str] = "qsub/relax.qsub.j2"
    scf_label: ClassVar[str] = "SCF da superfície"
    writes_report: ClassVar[bool] = True

    def check_scf(self, scf: ScfInfo) -> str | None:
        return surface_problem(scf, scf.name)

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        relax = super().input_fields(scf)
        return [
            *molecule_fields(),
            *site_fields(scf),
            *input_tab_fields(scf, self.calculation, relax),
        ]

    def field_data(self, field_id: str, scf: ScfInfo, values: Mapping[str, Any]) -> Any:
        if field_id == SITE:
            return site_rows(scf, values)
        return super().field_data(field_id, scf, values)

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        facts: Facts = [("SCF da superfície", scf.name)]
        editor = work.editor()
        other = values.get(MOLECULE)
        placed: Adsorbed | None = None
        if isinstance(other, ScfInfo):
            try:
                placed = self._structure(work, editor, other, facts)
            except SiteError as exc:
                work.problem(FIELD_OF_ROLE.get(exc.role, SITE), str(exc))
                facts.append((NOT_BUILT, str(exc)))
            except SurfaceError as exc:
                work.errors.append(str(exc))
                facts.append((NOT_BUILT, str(exc)))
        else:
            facts.append((NOT_BUILT, NO_MOLECULE))
        work.notes.extend(merge_namelists(editor, other if isinstance(other, ScfInfo) else None))
        self.edit(editor, work)
        if values["etot_conv_thr"] is not None:
            put_number(editor, "control", "etot_conv_thr", values["etot_conv_thr"])
        if placed is not None:
            surface = model_of(scf)
            sites = [(surface.labels[n - 1], n) for n in placed.sites]
            labels = placed.model.labels[placed.n_slab :]
            put_text(editor, "control", "prefix", adsorbed_prefix(scf.prefix, labels, sites))
        facts.append(self._kpoints(work))
        return [work.pw_file(self.calculation, editor), report_file(facts)]

    # -- the pieces of ``inputs`` ------------------------------------------------------------------
    def _request(self, work: Work) -> SiteRequest | None:
        """The site asked for, or None with the bad numbers marked on their fields."""
        values = work.values
        tol = check_positive(work, "site_tol", "A tolerância das coordenadas")
        window = check_positive(work, "height_window", "A janela da superfície")
        species = labels_of(values["site_species"])
        if not species:
            work.problem("site_species", "Preencha Espécies candidatas")
        if tol is None or window is None or not species:
            return None
        coords = None
        if values["site_from"] == FROM_COORDS:
            coords = tuple(values[field_id] or "" for field_id in COORDS)
        marked = tuple(values[SITE] or ())
        return SiteRequest(values["mode"] == BIDENTATE, marked, coords, tol, window, species)

    def _molecule(self, work: Work, other: ScfInfo) -> Molecule:
        anchor = work.values["anchor"]
        try:
            return molecule_of(other, anchor)
        except SurfaceError as exc:
            raise SiteError(f"SCF da molécula: {exc}", "anchor" if anchor else "molecule") from exc

    def _structure(
        self, work: Work, editor: InputEditor, other: ScfInfo, facts: Facts
    ) -> Adsorbed | None:
        scf, values = work.scf, work.values
        molecule = self._molecule(work, other)
        facts.append(("SCF da molécula", _molecule_fact(other, molecule)))
        request = self._request(work)
        distance = check_positive(work, "ads_distance", "A distância de adsorção")
        clearance = check_positive(work, "h_clearance", "A folga mínima", True)
        vacuum = check_positive(work, "vacuum_min", "O vácuo mínimo", True)
        scale = check_positive(work, BOND_SCALE, "A tolerância de ligação")
        check_positive(work, "symprec", "A tolerância de simetria")
        if request is None or distance is None or clearance is None or vacuum is None:
            facts.append((NOT_BUILT, FIX_FIELDS))
            return None
        surface = model_of(scf)
        placed = adsorb(
            surface,
            request,
            molecule,
            remove_h=bool(values["remove_h"]),
            distance=distance,
            h_clearance=clearance,
            vacuum_min=vacuum,
            bond_scale=scale or 1.0,
        )
        work.notes.extend(placed.notes)
        rule = values[FIX_RULE] or default_rule(scf)
        fix = fixed_for(work, placed.unwrapped, rule, scale or 1.0, n_slab=placed.n_slab)
        model = apply_fix(placed.model, fix, rule) if fix is not None else placed.model
        merged = merge_species(species_rows(scf.text), species_rows(other.text))
        problem = structure_problem(editor, model, merged.rows)
        if problem is not None:  # before the species card changes: the text stays the SCF's
            raise SurfaceError(problem)
        editor.replace_card_rows("ATOMIC_SPECIES", list(merged.rows))
        work.notes.extend(merged.notes)
        work.notes.extend(put_structure(editor, model, merged.rows))
        work.notes.extend(difference_notes(scf, other, merged.added, bool(work.jobs.pseudo_dir)))
        facts += self._facts(work, surface, request, placed, model)
        if fix is not None:
            facts.append(fixed_fact(model.labels[: placed.n_slab], fix, rule))
        return placed

    def _facts(
        self,
        work: Work,
        surface: Model,
        request: SiteRequest,
        placed: Adsorbed,
        model: Model,
    ) -> Facts:
        """The lines of ``geracao.md`` about the site and the placement (atoms numbered from 1, the
        surface's SCF numbering)."""
        values = work.values
        groups = _groups(work, request)
        sites = []
        for number in placed.sites:
            frac = " ".join(decimal(float(v), 5) for v in surface.frac[number - 1])
            group = f"; grupo {groups[number]}" if number in groups else ""
            sites.append(f"{surface.labels[number - 1]} {number} ({frac}{group})")
        anchor_label = model.labels[placed.anchor]
        distances = "; ".join(
            f"{anchor_label}–{surface.labels[n - 1]} {n} {decimal(d)} Å"
            for n, d in zip(placed.sites, placed.site_distances, strict=True)
        )
        position = ", ".join(decimal(float(v), 3) for v in model.cart[placed.anchor])
        molecule_atoms = len(model) - placed.n_slab
        how = "coordenadas" if request.coords is not None else "lista de candidatos"
        facts: Facts = [
            ("Coordenação", f"{values['mode']} (sítio pela {how})"),
            ("Átomo âncora" if len(sites) == 1 else "Átomos âncora", ", ".join(sites)),
            (
                "H removidos",
                ", ".join(f"H {n}" for n in placed.removed) if placed.removed else "nenhum",
            ),
            (
                "Átomos",
                f"{len(model)} ({placed.n_slab} da superfície + {molecule_atoms} da molécula: "
                f"{counts(model.labels)})",
            ),
            (
                "Posição do âncora",
                f"{position} Å (erguido {decimal(placed.lift)} Å)",
            ),
            ("Distâncias âncora–sítio", distances),
        ]
        clear = [
            f"{text} {decimal(value)} Å"
            for text, value in (
                ("âncora···H", placed.anchor_h),
                ("molécula–superfície", placed.clearance),
            )
            if value is not None
        ]
        if clear:
            facts.append(("Folgas", "; ".join(clear)))
        facts.append(("Vácuo acima da molécula", f"{decimal(placed.vacuum)} Å"))
        return facts

    def _kpoints(self, work: Work) -> tuple[str, str]:
        scf, typed = work.scf, work.values.get("kmesh")
        if typed is not None and typed != scf.kmesh:
            return ("k-points", f"{mesh_text(typed)} (digitada)")
        if scf.kmesh is not None:
            return ("k-points", f"{mesh_text(scf.kmesh)} (da superfície: a célula não muda)")
        return ("k-points", f"K_POINTS {scf.kpoints_option or '?'} da superfície mantido")


def _groups(work: Work, request: SiteRequest) -> dict[int, str]:
    """The symmetry group of each candidate (1-based), for the report; {} when it cannot say."""
    values = work.values
    symprec, scale = values["symprec"], values[BOND_SCALE]
    if not symprec or symprec <= 0 or not scale or scale <= 0:
        return {}
    try:
        found = candidates_for(work.scf, request.species, request.window, symprec, scale)
    except SurfaceError:
        return {}
    return {c.index: c.group for c in found}


def _molecule_fact(other: ScfInfo, molecule: Molecule) -> str:
    anchor = f"{molecule.labels[molecule.anchor]}{molecule.anchor + 1}"
    turned = "; girada para o eixo ficar na normal" if molecule.rotated else ""
    return (
        f"{other.name}: {formula(molecule.labels)} ({counts(molecule.labels)}), altura "
        f"{decimal(molecule.extent)} Å, "
        f"âncora {anchor}{turned}"
    )
