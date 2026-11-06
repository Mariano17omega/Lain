# Supercell

Repeats the SCF's structure **n1 × n2 × n3**, as a `vc-relax`. The SCF is usually a relaxed surface's (vacuum along
c), but a bulk works too (only the `cell_dofree` and fixed-atom defaults change).

- **Files**: `vc-relax_<prefix>.in` (`prefix = '<prefix>-<n1>x<n2>x<n3>'`, `nbnd` × copies), `.qsub`, `geracao.md`.
- **Fields**: **Repetitions** along a, b, c (1 to 8), **Minimum vacuum** (only checks and warns; the cell does not
  change), **k-point grid** (empty = the SCF's divided by the repetitions), `cell_dofree`, the **fixed atoms** rule
  (bottom layer, species and neighbours, from the SCF, none) and the **bond tolerance**.
- Warnings: a kept `gamma` k-point may not suffice; repeating along the vacuum stacks slabs.

Code: `core/calc_create/types/supercell.py`, `core/calc_create/surface/supercell.py`.
