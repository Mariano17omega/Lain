"""The structures "Visualizar 3D" shows for a calculation being created (spec 81 R1).

First the SCF the calculation starts from ("SCF base (scf.in)"), or each SCF of step 1's list for a
``multi_scf`` type (spec 79); then each pw.x input of the plan whose structure (cell, labels and
fractions, to 1e-6) differs from all of those before it: the complex of a molecule on a surface, the
slab, the supercell, the ``clean`` and ``isolated`` SCFs of a charge difference. The inputs that keep
the SCF's structure (bands, nscf, relax, the copies of spec 79) are not repeated.

Only texts are read (``structure_of_text``), never a file; the window runs it in a worker. A text that
gives no structure is skipped: the plan says its error, and the button says the SCF's.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ...i18n import _
from ..cancel import check
from ..structure3d.model import Structure
from ..structure3d.source import StructureReadError, structure_of_text
from .scf_info import ScfInfo
from .types import CalcPlan

__all__ = [
    "PlanStructure",
    "default_index",
    "plan_structures",
    "same_cell",
    "same_geometry",
    "same_view",
]

TOLERANCE = 1e-6
BASE_LABEL = _("SCF base ({name})")


@dataclass(frozen=True, eq=False)
class PlanStructure:
    label: str  # the window's combo
    name: str  # the file's name: the SCF's, or the one the new folder will have
    path: Path | None  # the file on disk; None: it is written only by "Criar"
    structure: Structure
    generated: bool = False  # an input of the plan, not one of the SCFs


def same_cell(a: Structure, b: Structure) -> bool:
    return bool(np.allclose(a.cell, b.cell, rtol=0.0, atol=TOLERANCE))


def same_geometry(a: Structure, b: Structure) -> bool:
    """The same cell, and the same atoms (labels, in order) at the same fractions."""
    return (
        a.labels == b.labels
        and a.frac.shape == b.frac.shape
        and same_cell(a, b)
        and bool(np.allclose(a.frac, b.frac, rtol=0.0, atol=TOLERANCE))
    )


def same_view(a: Structure, b: Structure) -> bool:
    """Nothing the window shows differs: the geometry, the ``if_pos`` flags, the species and what the
    input says of itself (the "Célula" section)."""
    return (
        same_geometry(a, b)
        and a.flags == b.flags
        and a.species == b.species
        and a.source == b.source
    )


def default_index(structures: list[PlanStructure]) -> int:
    """The structure the window opens on: the last one generated (the complex, the slab); with none
    generated, the SCF's (the first of a list)."""
    return max((i for i, each in enumerate(structures) if each.generated), default=0)


def plan_structures(
    scf: ScfInfo, plan: CalcPlan | None = None, scfs: tuple[ScfInfo, ...] = ()
) -> list[PlanStructure]:
    """The structures of ``scf`` (or of ``scfs``, step 1's list) and of ``plan``'s new pw.x inputs.
    No two have one label: the window picks a structure by it."""
    taken: set[str] = set()
    found = [
        PlanStructure(_own(label, taken), each.name, each.path, structure)
        for label, each in _bases(scf, scfs)
        if (structure := _parsed(each.text, each.path)) is not None
    ]
    for planned in plan.files if plan is not None else ():
        check()
        if planned.kind != "pw_input":
            continue
        structure = _parsed(planned.text, None)
        if structure is None or any(same_geometry(structure, s.structure) for s in found):
            continue
        label = _own(planned.tab_label, taken)
        found.append(PlanStructure(label, planned.name, None, structure, True))
    return found


def _own(label: str, taken: set[str]) -> str:
    """``label``, or ``label (2)``, ``(3)``… when one before it has that label."""
    candidate, number = label, 1
    while candidate in taken:
        number += 1
        candidate = f"{label} ({number})"
    taken.add(candidate)
    return candidate


def _bases(scf: ScfInfo, scfs: tuple[ScfInfo, ...]) -> Iterable[tuple[str, ScfInfo]]:
    """Each SCF with its label: "SCF base (<name>)", or the list's names (a repeated one with as many
    of its folders as it takes to tell it from the others)."""
    if not scfs:
        return [(BASE_LABEL.format(name=scf.name), scf)]
    labels = [each.name for each in scfs]
    deepest = max((len(each.path.parts) for each in scfs if each.path is not None), default=0)
    for depth in range(2, deepest + 1):
        counts = Counter(labels)
        labels = [
            Path(*each.path.parts[-depth:]).as_posix()
            if counts[label] > 1 and each.path is not None
            else label
            for label, each in zip(labels, scfs, strict=True)
        ]
    return list(zip(labels, scfs, strict=True))


def _parsed(text: str, path: Path | None) -> Structure | None:
    check()
    try:
        structure = structure_of_text(text, path)
    except StructureReadError:
        return None
    return structure if len(structure) else None
