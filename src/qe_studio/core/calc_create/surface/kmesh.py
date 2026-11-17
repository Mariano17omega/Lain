"""The k-point mesh of a new cell from the SCF's (spec 40 R4.3, ``rescale_kmesh`` of the scripts).

Each in-plane axis of the new cell takes the subdivision of the SCF axis it comes from, divided by the
supercell multiple along it (spec 41) and rounded up, so the new mesh is never less dense than the SCF's;
the vacuum axis gets 1. A shift follows its axis too, and the vacuum axis has none. A bulk supercell
(spec 41) has no vacuum axis: every axis is divided.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..kpath import KMesh

__all__ = ["UnevenAxis", "mesh_text", "rescale_mesh", "uneven_axes"]


@dataclass(frozen=True)
class UnevenAxis:
    """An axis of the new cell whose SCF subdivision ``n`` does not divide by ``multiple``: the new
    mesh takes ``result`` there, denser than the SCF's."""

    axis: int
    n: int
    multiple: int
    result: int


def _divide(n: int, multiple: int) -> int:
    """``n / multiple`` rounded up (Python's ``round`` goes to the even number: 5 / 2 → 2, a mesh
    sparser than the SCF's)."""
    return -(-n // multiple)


def rescale_mesh(
    mesh: KMesh,
    axis_map: Mapping[int, int],
    mults: Mapping[int, int] | None = None,
    vacuum_axis: int | None = 2,
) -> KMesh:
    """``axis_map``: new axis → the SCF axis it comes from; ``mults``: new axis → supercell multiple;
    ``vacuum_axis`` None: a bulk, no axis is forced to 1."""
    n, shift = [1, 1, 1], [0, 0, 0]
    for new, old in axis_map.items():
        n[new] = _divide(mesh.n[old], (mults or {}).get(new, 1))
        shift[new] = mesh.shift[old]
    if vacuum_axis is not None:
        n[vacuum_axis], shift[vacuum_axis] = 1, 0
    return KMesh((n[0], n[1], n[2]), (shift[0], shift[1], shift[2]))


def uneven_axes(
    mesh: KMesh,
    axis_map: Mapping[int, int],
    mults: Mapping[int, int] | None = None,
    vacuum_axis: int | None = 2,
) -> tuple[UnevenAxis, ...]:
    """The axes ``rescale_mesh`` (same arguments) had to round up: the new mesh there is denser than
    the SCF's, so the energies of the two cells are not equivalent samplings."""
    found = []
    for new, old in axis_map.items():
        multiple = (mults or {}).get(new, 1)
        if new == vacuum_axis or multiple < 2 or mesh.n[old] % multiple == 0:
            continue
        found.append(UnevenAxis(new, mesh.n[old], multiple, _divide(mesh.n[old], multiple)))
    return tuple(found)


def mesh_text(mesh: KMesh) -> str:
    """``6 4 1 0 0 0``: the mesh as the ``K_POINTS automatic`` row."""
    return " ".join(str(v) for v in (*mesh.n, *mesh.shift))
