"""Form fields and checks the surface types share (specs 40–42): the second SCF, the bond tolerance and
the fixed atoms, plus reading the species typed in a text field."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from ..scf_info import ScfInfo
from ..surface.fixing import BOTTOM, SPECIES
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
        tooltip="Input de SCF da molécula (pw.x, calculation = 'scf'); é lido, nunca alterado",
        standard=True,
        hint=hint,
    )


def bond_scale_field(group: str) -> FormField:
    return FormField(
        BOND_SCALE,
        "Tolerância de ligação (× soma dos raios covalentes)",
        "float",
        DEFAULT_BOND_SCALE,
        group=group,
        tooltip=(
            "Dois átomos estão ligados quando a distância é até esta fração da soma dos raios "
            "covalentes (tabela do ASE, a mesma dos scripts)"
        ),
    )


def fix_fields(
    group: str,
    rules: Sequence[str],
    default_rule: str = BOTTOM,
    species: str = "Si",
    neighbors: str = "O",
) -> list[FormField]:
    return [
        FormField(
            FIX_RULE,
            "Átomos fixos (if_pos 0 0 0)",
            "choice",
            default_rule,
            group=group,
            choices=tuple(rules),
            tooltip=(
                f"'{BOTTOM}': os átomos abaixo da fração da espessura; '{SPECIES}': as espécies "
                "fixas e os vizinhos ligados a elas; 'nenhum': todos livres"
            ),
        ),
        FormField(
            FIX_FRACTION,
            "Fração fixa da espessura",
            "float",
            0.5,
            group=group,
            tooltip=f"'{BOTTOM}': fixa os átomos abaixo desta fração da espessura (0,5 = metade)",
        ),
        FormField(
            FIX_SPECIES,
            "Espécies fixas",
            "text",
            species,
            group=group,
            tooltip=f"'{SPECIES}': rótulos de ATOMIC_SPECIES, separados por espaço",
        ),
        FormField(
            FIX_NEIGHBORS,
            "Vizinhos fixos",
            "text",
            neighbors,
            group=group,
            tooltip=f"'{SPECIES}': rótulos dos vizinhos ligados às espécies fixas que também ficam fixos",
        ),
    ]


def check_positive(work: Work, field_id: str, label: str, allow_zero: bool = False) -> float | None:
    """The number of ``field_id``, or None with a problem marked on it when it is not above zero."""
    value = work.values.get(field_id)
    if value is None:
        return None
    if value < 0 or (value == 0 and not allow_zero):
        limit = "maior ou igual a zero" if allow_zero else "maior que zero"
        work.problem(field_id, f"{label} deve ser {limit}")
        return None
    return float(value)


def check_labels(work: Work, scf: ScfInfo, field_id: str, label: str) -> tuple[str, ...]:
    """The labels typed in ``field_id``; one the SCF's ``ATOMIC_SPECIES`` lacks is a problem."""
    labels = labels_of(work.values.get(field_id))
    unknown = [name for name in labels if name not in scf.species]
    if unknown:
        work.problem(field_id, f"{label}: {', '.join(unknown)} não está em ATOMIC_SPECIES do SCF")
    return labels
