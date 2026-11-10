"""The "Átomos fixos" table of "Molécula na superfície" (spec 76): the surface atoms, a "Fixo" box each.

The rows are the atoms of the surface's SCF in its order and numbering (``atom_rows``), noted with the
``if_pos`` the SCF writes. The marks start from the rule of the fields (``suggested``: the SCF's own
fixed atoms by default, else the bottom half) and a change of a rule remakes them (``fixed_rows``, the
field's ``depends_on``). In the plan the marks are the fixed atoms (``fix_surface``): a marked atom the
SCF fixed keeps its flags, another one gets ``0 0 0``, the rest and the molecule are free. Without the
window's marks (None) the rule decides, as before (spec 42).
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Collection, Mapping
from typing import Any

from ....i18n import _
from ..fragments import AtomRows, atom_rows
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.adsorb import Adsorbed
from ..surface.candidates import surface_frame
from ..surface.fixing import (
    ALL_FIXED,
    BOTTOM,
    FIX_RULES,
    FIXED,
    FROM_SCF,
    SPECIES,
    FixResult,
    apply_fix,
)
from ..surface.model import Flags, Model, flags_of, model_of, partly_fixed
from .base import Work, resolve
from .surface_fields import (
    BOND_SCALE,
    DEFAULT_BOND_SCALE,
    FIX_FRACTION,
    FIX_NEIGHBORS,
    FIX_RULE,
    FIX_SPECIES,
    bond_scale_field,
    fix_by_rule,
    fix_fields,
    fixed_fact,
    fixed_for,
)

__all__ = [
    "CHECK_HEADER",
    "FIXED_ATOMS",
    "FIXED_HINT",
    "FIXED_PARAMS",
    "NOTE_HEADER",
    "default_rule",
    "fix_surface",
    "fixed_rows",
    "suggested",
    "table_fix",
]

FIXED_ATOMS = "fixed_atoms"
# The fields whose change remakes the marks.
FIXED_PARAMS = (FIX_RULE, FIX_FRACTION, FIX_SPECIES, FIX_NEIGHBORS, BOND_SCALE)
CHECK_HEADER = _("Fixo")
NOTE_HEADER = _("if_pos no SCF")
FIXED_HINT = _(
    "Marcados ficam fixos no relax. Começa com os fixos do SCF (ou a metade de baixo, se ele não fixa "
    "nenhum); as regras do modo Avançado refazem as marcas"
)
Fact = tuple[str, str]  # a line of geracao.md


def _fixes(flag: Flags | None) -> bool:
    return flag is not None and 0 in flag


def default_rule(scf: ScfInfo) -> str:
    """ "do SCF" when the surface fixes some atom but not all, else the bottom half."""
    return FROM_SCF if partly_fixed(scf.text) else BOTTOM


@functools.lru_cache(maxsize=16)  # the window plans on every edit; the text rarely changes
def _listed(text: str) -> AtomRows:
    """The SCF's atoms as written, each noted with the ``if_pos`` it writes ("" when none)."""
    atoms = atom_rows(text)
    if atoms.error:
        return atoms
    flags = flags_of(text)

    def note(index: int) -> str:
        flag = flags[index] if index < len(flags) else None
        return "" if flag is None else " ".join(str(value) for value in flag)

    rows = tuple(dataclasses.replace(row, note=note(i)) for i, row in enumerate(atoms.rows))
    return dataclasses.replace(atoms, rows=rows)


def suggested(
    scf: ScfInfo, values: Mapping[str, Any]
) -> tuple[tuple[int, ...] | None, dict[str, str]]:
    """The atoms (the SCF's numbers, ascending) the rule of the resolved ``values`` fixes on the whole
    surface, or None and the problem of each bad field."""
    rule = values[FIX_RULE] or default_rule(scf)
    scale = values[BOND_SCALE]
    if rule == SPECIES and (scale is None or scale <= 0):
        if scale is None:  # an invalid text, already said on its field
            return None, {}
        problem = _("{label} deve ser {limit}").format(
            label=_("A tolerância de ligação"), limit=_("maior que zero")
        )
        return None, {BOND_SCALE: problem}
    try:
        model = model_of(scf)
    except SurfaceError as exc:
        return None, {FIX_RULE: str(exc)}
    surface = model.replace(frac=surface_frame(model).frac)  # contiguous along c, as in the plan
    scale = float(scale) if scale and scale > 0 else DEFAULT_BOND_SCALE
    fix, problems = fix_by_rule(scf, values, surface, rule, scale)
    if fix is None or problems:
        return None, problems
    return tuple(i + 1 for i in fix.indices), {}


def fixed_rows(scf: ScfInfo, values: Mapping[str, Any]) -> AtomRows:
    """The table's rows and the marks the rule of the values typed (empty: the defaults) suggests. A
    problem of the rule is the table's message, and the table keeps its marks. Never raises."""
    listed = dataclasses.replace(
        _listed(scf.text), check_header=CHECK_HEADER, note_header=NOTE_HEADER
    )
    if listed.error:
        return listed
    params = [*fix_fields("", FIX_RULES, default_rule(scf)), bond_scale_field("")]
    resolved, errors = resolve(params, values)
    if errors:
        return dataclasses.replace(listed, error=errors[0])
    marks, problems = suggested(scf, resolved)
    if marks is None:
        return dataclasses.replace(listed, error=next(iter(problems.values()), ""))
    return dataclasses.replace(listed, marked=marks)


def table_fix(placed: Adsorbed, marked: Collection[int]) -> tuple[Model, FixResult]:
    """``placed`` with the flags of the table's ``marked`` atoms (the SCF's numbers): one the SCF
    fixed keeps its flags, another gets ``0 0 0``; the rest of the surface and the molecule are free.
    A marked H that was removed is not written, so it is not there."""
    model, chosen = placed.model, set(marked)
    indices = [i for i, number in enumerate(placed.numbers) if number in chosen]
    fixed = set(indices)
    flags = tuple(
        (own if _fixes(own := model.flag(i)) else FIXED) if i in fixed else None
        for i in range(len(model))
    )
    return model.replace(flags=flags), FixResult(tuple(indices))


def fix_surface(work: Work, placed: Adsorbed, scale: float) -> tuple[Model, Fact | None]:
    """The structure to write and the report's line on its fixed atoms: the table's marks
    (``values[FIXED_ATOMS]``, what the window sends) or, without them, the rule. Every problem is
    marked on its field: the rule's too, so a bad value never lets the old marks through."""
    values = work.values
    rule = values[FIX_RULE] or default_rule(work.scf)
    labels = placed.model.labels[: placed.n_slab]
    marked = values.get(FIXED_ATOMS)
    if marked is None:
        fix = fixed_for(work, placed.unwrapped, rule, scale, n_slab=placed.n_slab)
        if fix is None:
            return placed.model, None
        return apply_fix(placed.model, fix, rule), fixed_fact(labels, fix, rule)
    model, fix = table_fix(placed, marked)
    suggestion, problems = suggested(work.scf, values)
    for field_id, text in problems.items():
        work.problem(field_id, text)
    if placed.n_slab and len(fix.indices) >= placed.n_slab:
        work.problem(FIXED_ATOMS, ALL_FIXED)
        return placed.model, None
    differ = 0
    if suggestion is not None:
        differ = len((set(suggestion) ^ set(marked)) & set(placed.numbers))
    return model, fixed_fact(labels, fix, rule, table=True, differ=differ)
