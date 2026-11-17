# Supercell

Repeats the SCF's structure **n1 × n2 × n3**, as a `relax` or a `vc-relax`. The SCF is usually a relaxed surface's
(vacuum along c), but a bulk works too (only the calculation, `cell_dofree` and fixed-atom defaults change).

- **Calculation** (`calculation`, shown in the Padrão mode too), as in the [Slab](slab.md):
    - SCF with vacuum (a surface): `relax` by default, the plane at the bulk's lattice parameter; `vc-relax` relaxes the
      plane (`cell_dofree = '2Dxy'`), for an isolated 2D material.
    - SCF without vacuum (a bulk): `vc-relax` with `cell_dofree = 'all'` by default.
- **Files**: `relax_<prefix>.in` or `vc-relax_<prefix>.in` (`prefix = '<prefix>-<n1>x<n2>x<n3>'`, `nbnd` × copies),
  `.qsub`, `geracao.md`.
- **Fields**: **Repetitions** along a, b, c (1 to 8), **Minimum vacuum** (only for an SCF with vacuum; it checks and
  warns, the cell does not change), **k-point grid** (empty = the SCF's divided by the repetitions, rounded up: never less dense than the SCF's), `cell_dofree` (vc-relax only), the
  **fixed atoms** rule (bottom layer, species and neighbours, from the SCF, none; the parameters of each rule are shown
  only when it is chosen) and the **bond tolerance** (only with species and neighbours).
- **Saw-like field and dipole correction** (only for an SCF with vacuum; the `tefield` and `dipfield` boxes are
  shown in the Padrão mode too), as in the [Slab](slab.md): the boxes, `edir` and `eamp` start as the SCF has them, so
  the chain of an adsorption keeps one choice. `emaxpos` and `eopreg` are computed again for the supercell, unless
  typed; off, the keys leave the input. With copies along `edir` (`n3 > 1`) there is one vacuum per copy and the
  correction assumes one: the `dipfield` field shows the error.
- Warnings: a kept `gamma` k-point may not suffice; repeating along the vacuum stacks slabs.
- **Maximum steps** (`nstep`, default 100, shown in the Padrão mode too) and the commented line
  `! restart_mode = 'restart'` in `&CONTROL` are the [Relaxation](relax.md)'s: if the relax does not converge,
  uncomment the line and run again.

Code: `core/calc_create/types/supercell.py`, `core/calc_create/surface/supercell.py`.
