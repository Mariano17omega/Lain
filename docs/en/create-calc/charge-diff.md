# Charge difference

Three SCFs and `pp.x` computing Δρ = ρ(base) − ρ(clean) − ρ(isolated).

- **Files**: the base SCF, `scf_<p>_clean.in` (without the chosen atoms), `scf_<p>_isolated.in` (only those atoms), one
  `pp.x` per density and `pp_charge_diff.in`, which subtracts. The three SCFs share cell, cutoffs and mesh.
- **Fields**: the **Átomos** tab (atoms of the isolated fragment) is the essential; in Advanced, the `.xsf` format and
  folder.
- **Script**: the three SCFs with MPI and the same pools, then the four `pp.x`.

Code: `core/calc_create/types/charge_diff.py`, `core/calc_create/fragments.py`;
templates `qe/charge_diff/pp_charge_diff.in.j2`, `qsub/charge_diff.qsub.j2`.
