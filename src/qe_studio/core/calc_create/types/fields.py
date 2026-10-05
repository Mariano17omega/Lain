"""Form fields more than one type asks for (spec 25 R4, R5)."""

from __future__ import annotations

import math

from ..kpath import KMesh
from ..scf_info import ScfInfo
from .base import FormField, Work

__all__ = ["DEFAULT_MESH", "check_mesh", "kmesh_field", "nbnd_default", "nbnd_field"]

DEFAULT_MESH = KMesh((4, 4, 4))
BANDS_MARGIN = 1.2  # nbnd from the SCF's output: 20 % more than the states pw.x used


def kmesh_field(scf: ScfInfo, group: str, required: bool) -> FormField:
    """``K_POINTS automatic`` of ``group``: the SCF's mesh when it has one. Optional (empty keeps
    the SCF's card) unless ``required``, whose fallback is 4 4 4 0 0 0."""
    default = scf.kmesh or (DEFAULT_MESH if required else None)
    keep = "" if required else "; vazio = mantém o K_POINTS do SCF"
    return FormField(
        "kmesh",
        "Rede de k-points",
        "kmesh",
        default,
        required=required,
        group=group,
        tooltip=f"K_POINTS automatic: n1 n2 n3 e os deslocamentos s1 s2 s3 (0 ou 1){keep}",
    )


def check_mesh(work: Work) -> KMesh | None:
    mesh = work.values.get("kmesh")
    if mesh is not None:
        work.errors.extend(mesh.problems())
    return mesh


def nbnd_default(scf: ScfInfo) -> int | None:
    """The SCF's nbnd; else 20 % above the states its output used; else None (typed)."""
    if scf.nbnd is not None:
        return scf.nbnd
    if scf.scf_bands is not None:
        return math.ceil(BANDS_MARGIN * scf.scf_bands)
    return None


def nbnd_field(scf: ScfInfo, group: str, hint: str = "") -> FormField:
    """``hint``: a sentence the type adds to the tooltip."""
    tooltip = "Bandas calculadas: inclua as de condução que quer ver"
    return FormField(
        "nbnd",
        "Número de bandas (nbnd)",
        "int",
        nbnd_default(scf),
        required=True,
        group=group,
        tooltip=f"{tooltip}. {hint}" if hint else tooltip,
    )
