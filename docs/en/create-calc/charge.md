# Charge

SCF and `pp.x` writing the charge density as XSF (to view in XCrySDen).

- **Files**: `charge.qsub`, a copy of the SCF, `pp_<name>_charge.in` (`<name>` = the folder name typed in step 1).
- **Standard**: only the name and the SCF. **Advanced**: `plot_num` (0 = electron density; 6 = spin polarization,
  only with `nspin = 2`), `iflag` (0–4; default 3 = 3D grid), `output_format` (default 5 = XSF; shown only with
  `iflag` 2 or 3) and `fileout`, in the `cdd_xsf/` folder. The `plot_num` tooltip notes that, with PAW, 0 and 6 are
  pseudo-densities (the all-electron one is 17 or 21).
- The script makes the `fileout` folder (`pp.x` does not) and runs `pp.x` without MPI.
- A `disk_io` of `minimal` or `none` is removed from the SCF, with a warning: `pp.x` reads the charge density,
  which those values do not save.

Code: `core/calc_create/types/charge.py`; templates `qe/charge/pp_charge.in.j2`, `qsub/charge.qsub.j2`.
