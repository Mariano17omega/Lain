"""Which atoms a surface input keeps fixed, ``if_pos = 0 0 0`` (spec 40 R4, port of ``fixed_indices``).

The rules (``FIX_RULES``):

- "camada inferior": the atoms below ``min + fraction × thickness`` along the normal (0.5 is the
  script's middle plane, its (010) rule);
- "espécies e vizinhos": the atoms of ``species`` plus those of ``neighbors`` bonded to one of them
  (distance ``<`` the bond cutoff, the script's (001) rule: every Si and the O bonded to a Si);
- "do SCF": the flags the structure already has; "nenhum": none.

Only the first ``n_slab`` atoms count (a molecule appended later stays free). A fixed atom is written
with ``0 0 0`` and a free one with nothing, as the scripts do; "do SCF" writes the flags as they were.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ....i18n import N_, _
from . import SurfaceError
from .elements import covalent_radius
from .geometry import pair_images
from .model import Flags, Model

__all__ = [
    "ALL_FIXED",
    "BOTTOM",
    "FIX_RULES",
    "FROM_SCF",
    "NONE",
    "SPECIES",
    "FixResult",
    "apply_fix",
    "fixed_atoms",
]

# The values of the "fix" choice: data, shown through ``_()`` by the form.
BOTTOM = N_("camada inferior")
SPECIES = N_("espécies e vizinhos")
FROM_SCF = N_("do SCF")
NONE = N_("nenhum")
FIX_RULES = (BOTTOM, SPECIES, FROM_SCF, NONE)
ALL_FIXED = _("Todos os átomos ficariam fixos")
FIXED: Flags = (0, 0, 0)


@dataclass(frozen=True)
class FixResult:
    indices: tuple[int, ...]  # 0-based, ascending
    notes: tuple[str, ...] = ()


def _normal(cell: np.ndarray) -> np.ndarray:
    normal = np.cross(cell[0], cell[1])
    return normal / np.linalg.norm(normal)


def _by_species(
    model: Model,
    heights: np.ndarray,
    species: Sequence[str],
    neighbors: Sequence[str],
    bond_scale: float,
    count: int,
) -> tuple[list[int], list[str]]:
    chosen = [i for i in range(count) if model.labels[i] in species]
    around = [i for i in range(count) if model.labels[i] in neighbors]
    notes = []
    fixed = set(chosen)
    if chosen and around:
        distances, __ = pair_images(model.frac, model.cell, chosen, around)
        radii = np.array([covalent_radius(label) for label in model.labels])
        cutoffs = bond_scale * (radii[chosen][:, None] + radii[around][None, :])
        fixed |= {around[j] for j in np.flatnonzero((distances < cutoffs).any(axis=0))}
    middle = heights.min() + 0.5 * (heights.max() - heights.min())
    if chosen and heights[chosen].mean() > middle:
        names = ", ".join(dict.fromkeys(model.labels[i] for i in chosen))
        notes.append(
            _(
                "Os átomos de {names} ficam, em média, acima do plano médio: a parte fixa não é a de baixo"
            ).format(names=names)
        )
    return sorted(fixed), notes


def fixed_atoms(
    model: Model,
    rule: str,
    *,
    fraction: float = 0.5,
    species: Sequence[str] = (),
    neighbors: Sequence[str] = (),
    bond_scale: float = 1.15,
    n_slab: int | None = None,
) -> FixResult:
    """The atoms ``rule`` fixes. Raises ``SurfaceError`` when it would fix them all."""
    count = len(model) if n_slab is None else min(n_slab, len(model))
    heights = model.cart[:count] @ _normal(model.cell)
    notes: list[str] = []
    if rule == BOTTOM:
        cut = heights.min() + fraction * (heights.max() - heights.min())
        indices = np.flatnonzero(heights < cut).tolist()
    elif rule == SPECIES:
        indices, notes = _by_species(model, heights, species, neighbors, bond_scale, count)
    elif rule == FROM_SCF:
        indices = [i for i in range(count) if (flag := model.flag(i)) is not None and 0 in flag]
    elif rule == NONE:
        indices = []
    else:
        raise SurfaceError(_("Regra de átomos fixos desconhecida: {rule}").format(rule=rule))
    if count and len(indices) >= count:
        raise SurfaceError(ALL_FIXED)
    if not indices and rule != NONE:
        notes.append(_("Nenhum átomo ficou fixo pela regra '{rule}'").format(rule=_(rule)))
    return FixResult(tuple(int(i) for i in indices), tuple(notes))


def apply_fix(model: Model, result: FixResult, rule: str) -> Model:
    """``model`` with the flags to write: ``0 0 0`` on the fixed atoms and none on the rest, or the
    structure's own flags for "do SCF"."""
    if rule == FROM_SCF:
        return model
    fixed = set(result.indices)
    return model.replace(flags=tuple(FIXED if i in fixed else None for i in range(len(model))))
