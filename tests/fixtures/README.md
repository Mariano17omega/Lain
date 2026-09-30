# Test fixtures

Real Quantum ESPRESSO 7.3.1 outputs, kept small:

| Folder | Source | Notes |
|---|---|---|
| `al_bands/` | Al band-structure tutorial run | tutorial names (`al.scf.out`, `al.band.in`), `bands.in`/`bands.out` are bands.x files; `al.scf.out` crashes ASE's `espresso-out` reader (regression) |
| `si_bands/` | Si band-structure tutorial run | explicit 200-point `K_POINTS crystal` list without labels; pw.x printed no eigenvalues |
| `al_pdos_flat/` | Al DOS/PDOS tutorial run | flat layout (no `orbitals/`); PDOS files keep every 4th energy row; `al.projwfc.out` truncated (head + tail) |
| `ni_pdos_spin/` | QE 7.3.1 `PP/examples/example02/reference` (GPL-2.0) | spin-polarized Ni PDOS; `ni.pdos.out` truncated |
| `si_relax/` | Si relax tutorial run | `si.rel.in` / `si.rel.out` |
| `kao_vc_relax/` | user's kaolinite bulk vc-relax (QE 7.1) | 25 BFGS steps in the run; keeps steps 0–2 and 23–24, `bfgs converged`, `Final scf calculation` and its SCF, `JOB DONE` |
| `kao_slab_relax/` | user's kaolinite (001) slab relax (QE 7.1) | 42 steps in the run; keeps steps 0–2 and 40–41 |
| `kao_supercell_relax/` | user's kaolinite 2×1×1 slab relax (QE 7.1) | a single step: `bfgs converged in 1 scf cycles and 0 bfgs steps` |

The `kao_*` outputs were trimmed by removing whole BFGS steps between complete steps and the
per-k-point eigenvalue listings of every SCF (everything the relax parser reads is untouched).

The PRD folder layout (`scf.out`, `nscf.out`, `projwfc.out`, `orbitals/`) is built at test time
from `al_pdos_flat/` (see the `al_pdos_orbitals` fixture in `conftest.py`).
