"""The k-point mesh of a new cell from the SCF's (spec 40 R4.3, ``rescale_kmesh`` of the scripts).

Each in-plane axis of the new cell takes the subdivision of the SCF axis it comes from, divided by the
supercell multiple along it (spec 41); the vacuum axis gets 1. A shift follows its axis too, and the
vacuum axis has none.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..kpath import KMesh

__all__ = ["rescale_mesh"]


def rescale_mesh(
    mesh: KMesh,
    axis_map: Mapping[int, int],
    mults: Mapping[int, int] | None = None,
    vacuum_axis: int = 2,
) -> KMesh:
    """``axis_map``: new axis → the SCF axis it comes from; ``mults``: new axis → supercell multiple."""
    n, shift = [1, 1, 1], [0, 0, 0]
    for new, old in axis_map.items():
        multiple = (mults or {}).get(new, 1)
        n[new] = max(1, int(round(mesh.n[old] / multiple)))
        shift[new] = mesh.shift[old]
    n[vacuum_axis], shift[vacuum_axis] = 1, 0
    return KMesh((n[0], n[1], n[2]), (shift[0], shift[1], shift[2]))
