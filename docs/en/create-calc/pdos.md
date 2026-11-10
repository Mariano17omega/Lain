# PDOS

SCF, NSCF on a mesh and `projwfc.x`.

- **Files**: SCF, NSCF, `projwfc.in`, `pdos.qsub`.
- **Fields** (Standard: only `Emin`/`Emax`, blank: `projwfc.x` takes the whole range of the computed bands; when
  typed, they are absolute energies in eV): NSCF mesh (the SCF's when automatic),
  `occupations` (`tetrahedra` by default; also `smearing`, `tetrahedra_opt`, `tetrahedra_lin`, `fixed`), `DeltaE`
  (0.01), `ngauss`/`degauss` (0 and 0.000735 Ry ≈ 0.01 eV; they replace the smearing of `pw.x`; omitted with
  tetrahedra, since they would turn the method off). `nbnd` follows the SCF — above the last band the DOS is zero,
  so raise `nbnd` or lower `Emax`.
- **`disk_io`**: `projwfc.x` reads the NSCF's wavefunctions. If the SCF has `disk_io` `nowf`, `minimal` or `none`,
  Lain removes it from the NSCF (and `minimal`/`none` from the SCF too, which must leave the charge density) and
  says so; QE's defaults save what is missing.
- **Script**: pw.x SCF → pw.x NSCF → `projwfc.x`; at the end `mkdir -p orbitals && mv *pdos_atm#* orbitals/` (the glob
  does not move `projwfc.in/out`) and `projwfc.x`'s status is preserved for the e-mail.
- The result is detected as `PDOS` — see [PDOS](../plots/pdos.md).

Code: `core/calc_create/types/pdos.py`; templates `qe/pdos/projwfc.in.j2`, `qsub/pdos.qsub.j2`.
