"""The k-point mesh of a new cell from the SCF's (spec 40 R4.3, ``rescale_kmesh`` of the scripts).

Each in-plane axis of the new cell takes the subdivision of the SCF axis it comes from, divided by the
supercell multiple along it (spec 41); the vacuum axis gets 1. A shift follows its axis too, and the
vacuum axis has none. A bulk supercell (spec 41) has no vacuum axis: every axis is divided.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..kpath import KMesh

__all__ = ["mesh_text", "rescale_mesh"]


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
        multiple = (mults or {}).get(new, 1)
        n[new] = max(1, int(round(mesh.n[old] / multiple)))
        shift[new] = mesh.shift[old]
    if vacuum_axis is not None:
        n[vacuum_axis], shift[vacuum_axis] = 1, 0
    return KMesh((n[0], n[1], n[2]), (shift[0], shift[1], shift[2]))


def mesh_text(mesh: KMesh) -> str:
    """``6 4 1 0 0 0``: the mesh as the ``K_POINTS automatic`` row."""
    return " ".join(str(v) for v in (*mesh.n, *mesh.shift))
