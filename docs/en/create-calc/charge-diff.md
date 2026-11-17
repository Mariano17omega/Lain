# Charge difference

Three SCFs and `pp.x` computing Δρ = ρ(base) − ρ(clean) − ρ(isolated) or, with `nspin = 2`,
Δm = m(base) − m(clean) − m(isolated), with m = ρ↑ − ρ↓.

- **Files**: the base SCF, `scf_<p>_clean.in` (without the chosen atoms), `scf_<p>_isolated.in` (only those atoms), one
  `pp.x` per density and `pp_charge_diff.in`, which subtracts. The three SCFs share cell, cutoffs and mesh.
- **Fields**: the **Átomos** tab (atoms of the isolated fragment) is the essential; in Advanced, the quantity
  (`plot_num` 0 or 6), the `.xsf` format and folder. With 6 the data are named `<p>.spin`, `<p>_spin_diff.xsf`…,
  and an SCF without `nspin = 2` blocks "Create" (`pp.x` would write only zeros).
- **Script**: the three SCFs with MPI and the same pools, then the four `pp.x`.
- A `disk_io` of `minimal` or `none` is removed from the three SCFs, with a warning per file: `pp.x` reads their
  charge densities, which those values do not save.

Code: `core/calc_create/types/charge_diff.py`, `core/calc_create/fragments.py`;
templates `qe/charge_diff/pp_charge_diff.in.j2`, `qsub/charge_diff.qsub.j2`.
