"""The structure of a pw.x input in 3D (spec 43): the data, bonds, scene and camera the viewer draws.

A port of the proof of concept in ``Documentation/Exemplo-visualizador_3d`` on numpy alone; ``ase.data``
(element tables) and ``scipy`` (bond search from 1 000 atoms) are imported on first use. Qt-free:

- ``model``: ``Structure`` (cell in Å, labels, fractions, flags, species, ``SourceInfo``), ``AtomRef``, ``atom_name``.
- ``source``: ``read_structure`` (worker) / ``structure_of_text``, with the input lexer, editor and ``latgen`` of
  ``core/qe``; errors are ``StructureReadError`` in Portuguese.
- ``elements``: species label → element, radii, Jmol color, Portuguese name.
- ``bonds``: bonds over periodic images and ``BondGraph``; ``replicate``: the drawn ``Scene`` (copies and ghosts).
- ``geometry``: the drawn radius of each atom and the bond halves that start on the sphere's surface.
- ``camera``: arcball, projections, views; ``pick``: the atom under a click; ``options``: ``DisplayOptions``.
"""
