# Charge

SCF and `pp.x` writing the charge density as XSF (to view in XCrySDen).

- **Files**: `charge.qsub`, a copy of the SCF, `pp_<name>_charge.in` (`<name>` = the folder name typed in step 1).
- **Standard**: only the name and the SCF. **Advanced**: `plot_num` (0 = electron density), `iflag` (0–4; default 3 =
  3D grid), `output_format` (default 5 = XSF) and `fileout`, in the `cdd_xsf/` folder.
- The script makes the `fileout` folder (`pp.x` does not) and runs `pp.x` without MPI.

Code: `core/calc_create/types/charge.py`; templates `qe/charge/pp_charge.in.j2`, `qsub/charge.qsub.j2`.
