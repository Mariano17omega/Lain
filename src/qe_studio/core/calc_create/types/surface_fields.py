"""Form fields and checks the surface types share (specs 40–42): the second SCF, the bond tolerance and
the fixed atoms (fields, the check of their values and the report line, which also says when they come
from the table of spec 76), plus reading the species typed in a text field."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ....i18n import _, ngettext
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.fixing import BOTTOM, NONE, SPECIES, FixResult, fixed_atoms
from ..surface.model import Model
from .base import FormField, Work

__all__ = [
    "BOND_SCALE",
    "DEFAULT_BOND_SCALE",
    "FIX_FRACTION",
    "FIX_NEIGHBORS",
    "FIX_RULE",
    "FIX_SPECIES",
    "MOLECULE",
    "bond_scale_field",
    "check_labels",
    "check_positive",
    "counts",
    "fix_by_rule",
    "fix_fields",
    "fixed_fact",
    "fixed_for",
    "labels_of",
    "molecule_field",
    "unknown_labels",
]

MOLECULE = "molecule"
BOND_SCALE = "bond_scale"
FIX_RULE = "fix_rule"
FIX_FRACTION = "fix_fraction"
FIX_SPECIES = "fix_species"
FIX_NEIGHBORS = "fix_neighbors"
DEFAULT_BOND_SCALE = 1.15  # the scripts' tolerance over the sum of the covalent radii
_SEPARATORS = re.compile(r"[\s,;]+")


def labels_of(text: object) -> tuple[str, ...]:
    """The species labels typed in a field (``"Al Si"``, ``"Al, Si"``), in order, without repeats."""
    return tuple(dict.fromkeys(word for word in _SEPARATORS.split(str(text or "")) if word))


def counts(labels: Sequence[str]) -> str:
    """``Al 4, Si 4, O 18``: each label and how many, in the order they first appear."""
    return ", ".join(f"{label} {n}" for label, n in Counter(labels).items())


def molecule_field(group: str, label: str, hint: str, required: bool = False) -> FormField:
    return FormField(
        MOLECULE,
        label,
        "scf_file",
        None,
        required=required,
        group=group,
        tooltip=_("Input de SCF da molécula (pw.x, calculation = 'scf'); é lido, nunca alterado"),
        standard=True,
        hint=hint,
    )


def bond_scale_field(group: str) -> FormField:
    return FormField(
        BOND_SCALE,
        _("Tolerância de ligação (× soma dos raios covalentes)"),
        "float",
        DEFAULT_BOND_SCALE,
        group=group,
        tooltip=(
            _(
                "Dois átomos estão ligados quando a distância é até esta fração da soma dos raios "
                "covalentes (tabela do ASE, a mesma dos scripts)"
            )
        ),
    )


def fix_fields(
    group: str,
    rules: Sequence[str],
    default_rule: str = BOTTOM,
    species: str = "Si",
    neighbors: str = "O",
) -> list[FormField]:
    # The rules as the combo shows them: the tooltips quote its labels, not the tokens.
    bottom, by_species, none = _(BOTTOM), _(SPECIES), _(NONE)
    return [
        FormField(
            FIX_RULE,
            _("Átomos fixos (if_pos 0 0 0)"),
            "choice",
            default_rule,
            group=group,
            choices=tuple(rules),
            tooltip=(
                _(
                    "'{BOTTOM}': os átomos abaixo da fração da espessura; '{SPECIES}': as espécies fixas e os vizinhos ligados a elas; '{NONE}': todos livres"
                ).format(BOTTOM=bottom, SPECIES=by_species, NONE=none)
            ),
        ),
        FormField(
            FIX_FRACTION,
            _("Fração fixa da espessura"),
            "float",
            0.5,
            group=group,
            tooltip=_(
                "'{BOTTOM}': fixa os átomos abaixo desta fração da espessura (0.5 = metade)"
            ).format(BOTTOM=bottom),
        ),
        FormField(
            FIX_SPECIES,
            _("Espécies fixas"),
            "text",
            species,
            group=group,
            tooltip=_("'{SPECIES}': rótulos de ATOMIC_SPECIES, separados por espaço").format(
                SPECIES=by_species
            ),
        ),
        FormField(
            FIX_NEIGHBORS,
            _("Vizinhos fixos"),
            "text",
            neighbors,
            group=group,
            tooltip=_(
                "'{SPECIES}': rótulos dos vizinhos ligados às espécies fixas que também ficam fixos"
            ).format(SPECIES=by_species),
        ),
    ]


def check_positive(work: Work, field_id: str, label: str, allow_zero: bool = False) -> float | None:
    """The number of ``field_id``, or None with a problem marked on it when it is not above zero."""
    value = work.values.get(field_id)
    if value is None:
        return None
    if value < 0 or (value == 0 and not allow_zero):
        limit = _("maior ou igual a zero") if allow_zero else _("maior que zero")
        work.problem(field_id, _("{label} deve ser {limit}").format(label=label, limit=limit))
        return None
    return float(value)


def unknown_labels(scf: ScfInfo, labels: Sequence[str], label: str) -> str | None:
    """The problem of the ``labels`` typed in the field ``label`` that the SCF's ``ATOMIC_SPECIES``
    lacks, or None."""
    unknown = [name for name in labels if name not in scf.species]
    if not unknown:
        return None
    return _("{label}: {join} não está em ATOMIC_SPECIES do SCF").format(
        label=label, join=", ".join(unknown)
    )


def check_labels(work: Work, scf: ScfInfo, field_id: str, label: str) -> tuple[str, ...]:
    """The labels typed in ``field_id``; one the SCF's ``ATOMIC_SPECIES`` lacks is a problem."""
    labels = labels_of(work.values.get(field_id))
    problem = unknown_labels(scf, labels, label)
    if problem is not None:
        work.problem(field_id, problem)
    return labels


def fix_by_rule(
    scf: ScfInfo,
    values: Mapping[str, Any],
    model: Model,
    rule: str,
    scale: float,
    n_slab: int | None = None,
) -> tuple[FixResult | None, dict[str, str]]:
    """The atoms ``rule`` fixes in ``model`` (only its first ``n_slab``) from the fields' resolved
    ``values``, and the problem of each bad field by id. A bad value still gives atoms (a fraction
    out of range counts as 0.5); a rule that cannot apply gives None, its problem on ``fix_rule``."""
    problems: dict[str, str] = {}
    fraction = values[FIX_FRACTION]
    if rule == BOTTOM and fraction is not None and not 0 < fraction <= 1:
        problems[FIX_FRACTION] = _("A fração fixa da espessura vai de 0 (exclusive) a 1")
        fraction = None
    species: tuple[str, ...] = ()
    neighbors: tuple[str, ...] = ()
    if rule == SPECIES:
        species = labels_of(values.get(FIX_SPECIES))
        neighbors = labels_of(values.get(FIX_NEIGHBORS))
        for field_id, label, labels in (
            (FIX_SPECIES, _("Espécies fixas"), species),
            (FIX_NEIGHBORS, _("Vizinhos fixos"), neighbors),
        ):
            if (problem := unknown_labels(scf, labels, label)) is not None:
                problems[field_id] = problem
        if not species:
            problems.setdefault(FIX_SPECIES, _("Preencha Espécies fixas"))
    try:
        fix = fixed_atoms(
            model,
            rule,
            fraction=fraction if fraction is not None else 0.5,
            species=species,
            neighbors=neighbors,
            bond_scale=scale,
            n_slab=n_slab,
        )
    except SurfaceError as exc:
        problems.setdefault(FIX_RULE, str(exc))
        return None, problems
    return fix, problems


def fixed_for(
    work: Work, model: Model, rule: str, scale: float, n_slab: int | None = None
) -> FixResult | None:
    """The atoms ``rule`` fixes in ``model`` (only its first ``n_slab``: a molecule added after the
    surface stays free), from the fields' values; a bad value is marked on its field and a rule that
    cannot apply on ``fix_rule`` (None then)."""
    fix, problems = fix_by_rule(work.scf, work.values, model, rule, scale, n_slab)
    for field_id, text in problems.items():
        work.problem(field_id, text)
    if fix is not None:
        work.notes.extend(fix.notes)
    return fix


def fixed_fact(
    labels: Sequence[str], fix: FixResult, rule: str, table: bool = False, differ: int = 0
) -> tuple[str, str]:
    """The "Átomos fixos" line of ``geracao.md``: how many, by species, and where they come from: the
    rule, or the table's marks (``table``, spec 76) and how many of them ``differ`` from the rule."""
    which = f" ({counts([labels[i] for i in fix.indices])})" if fix.indices else ""
    numbers = {"count": len(fix.indices), "count_2": len(labels), "which": which, "rule": _(rule)}
    if not table:
        text = _("{count}/{count_2}{which}, regra '{rule}'").format(**numbers)
    elif differ:
        text = ngettext(
            "{count}/{count_2}{which}, marcados na tabela ({k} diferente da regra '{rule}')",
            "{count}/{count_2}{which}, marcados na tabela ({k} diferentes da regra '{rule}')",
            differ,
        ).format(k=differ, **numbers)
    else:
        text = _("{count}/{count_2}{which}, marcados na tabela").format(**numbers)
    return (_("Átomos fixos"), text)
