"""The structures of the surface types of "Criar cálculo" (specs 40–42).

A port of the user's scripts (``Documentation/Exemplo-SLAB``) on numpy and ``ase.data`` alone (radii and
symbols, imported on first use: never ``ase.io``):

- ``model``: the ``Model`` a type works on (cell in Å, labels, fractions, ``if_pos`` flags).
- ``elements``: the element of a species label, its covalent radius and atomic number.
- ``geometry``: minimum images, bonds and the empty gaps of a cell.
- ``molecule``: a molecule's SCF with its anchor at the origin and its axis along +z.
- ``slab``: the bulk with one axis stretched to open vacuum (spec 40).
- ``supercell``: a diagonal supercell, ``n1 × n2 × n3`` (spec 41).
- ``fixing``: which atoms get ``if_pos = 0 0 0``; ``kmesh``: the mesh of the new cell.
- ``write``: the structure into an input's text; ``report``: ``geracao.md``.

Errors are ``SurfaceError`` with a Portuguese sentence. Qt-free.
"""

from __future__ import annotations

__all__ = ["SurfaceError"]


class SurfaceError(Exception):
    """Why a surface structure cannot be built, in Portuguese."""
