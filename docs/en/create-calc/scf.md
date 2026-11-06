# SCF

Generates the SCF in a folder of its own from the source SCF (useful to reuse the structure with another `outdir`,
pseudopotentials or mesh).

- **Files**: `scf_<prefix>.in`, `scf.qsub`.
- **Field**: k-mesh (`kmesh`, optional; empty keeps the SCF's).
- **Script**: one line `mpiexec pw.x -nk $NK -i scf_<prefix>.in > scf_<prefix>.out`.
- `outdir = './tmp/'` and `pseudo_dir` from `jobs.pseudo_dir`, if set.

Code: `core/calc_create/types/scf.py`; template `resources/templates/qsub/scf.qsub.j2`.
