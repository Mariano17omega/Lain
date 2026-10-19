"""Form fields and checks the surface types share (specs 40–42): the second SCF, the bond tolerance and
the fixed atoms (fields, the check of their values and the report line), plus reading the species typed
in a text field."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from ....i18n import _
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
    "fix_fields",
    "fixed_fact",
    "fixed_for",
    "labels_of",
    "molecule_field",
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


def check_labels(work: Work, scf: ScfInfo, field_id: str, label: str) -> tuple[str, ...]:
    """The labels typed in ``field_id``; one the SCF's ``ATOMIC_SPECIES`` lacks is a problem."""
    labels = labels_of(work.values.get(field_id))
    unknown = [name for name in labels if name not in scf.species]
    if unknown:
        work.problem(
            field_id,
            _("{label}: {join} não está em ATOMIC_SPECIES do SCF").format(
                label=label, join=", ".join(unknown)
            ),
        )
    return labels


def fixed_for(
    work: Work, model: Model, rule: str, scale: float, n_slab: int | None = None
) -> FixResult | None:
    """The atoms ``rule`` fixes in ``model`` (only its first ``n_slab``: a molecule added after the
    surface stays free), from the fields' values; a bad value is marked on its field and a rule that
    cannot apply on ``fix_rule`` (None then)."""
    fraction = work.values[FIX_FRACTION]
    if rule == BOTTOM and fraction is not None and not 0 < fraction <= 1:
        work.problem(FIX_FRACTION, _("A fração fixa da espessura vai de 0 (exclusive) a 1"))
        fraction = None
    species: tuple[str, ...] = ()
    neighbors: tuple[str, ...] = ()
    if rule == SPECIES:
        species = check_labels(work, work.scf, FIX_SPECIES, _("Espécies fixas"))
        neighbors = check_labels(work, work.scf, FIX_NEIGHBORS, _("Vizinhos fixos"))
        if not species:
            work.problem(FIX_SPECIES, _("Preencha Espécies fixas"))
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
        work.problem(FIX_RULE, str(exc))
        return None
    work.notes.extend(fix.notes)
    return fix


def fixed_fact(labels: Sequence[str], fix: FixResult, rule: str) -> tuple[str, str]:
    """The "Átomos fixos" line of ``geracao.md``: how many, by species, and the rule."""
    which = f" ({counts([labels[i] for i in fix.indices])})" if fix.indices else ""
    return (
        _("Átomos fixos"),
        _("{count}/{count_2}{which}, regra '{rule}'").format(
            count=len(fix.indices), count_2=len(labels), which=which, rule=_(rule)
        ),
    )
