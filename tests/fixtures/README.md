# Test fixtures

Real Quantum ESPRESSO outputs, kept small. **Lain supports QE ≥ 7.1:** new fixtures are always
from 7.1 or newer, and no code or fixture handles older formats. The one exception is
`ni_pdos_spin/` (QE 6.0, the official example), kept because it is the only spin-polarized PDOS
until the spin fixture of spec 13 replaces it.

`tests/test_qe_versions.py` holds one table with a row per fixture folder and checks each row per
version: the Fermi / HOMO line of the pw.x output, the block separator of `.gnu` files (empty
line in 7.3, one space in 7.1), the bands.x output and the PDOS column headers. QE 7.1 so far has
only the `kao_*` pw.x relax outputs; there are no 7.2 or 7.4 runs yet.

**Adding a version:** copy a real run (pw.x scf + bands.x with its `.gnu` + a short projwfc PDOS)
into `qe<version>_<system>/` (e.g. `qe74_al/`), trimmed like the others (whole BFGS steps,
per-k-point eigenvalue listings and every Nth PDOS row can go), document it in the table below
and add a `Run` row. `git add` the folder: `test_fixtures_untouched.py` fails on untracked files.

| Folder | Source | Notes |
|---|---|---|
| `al_bands/` | Al band-structure tutorial run (QE 7.3.1) | tutorial names (`al.scf.out`, `al.band.in`), `bands.in`/`bands.out` are bands.x files; `al.scf.out` crashes ASE's `espresso-out` reader (regression) |
| `si_bands/` | Si band-structure tutorial run (QE 7.3.1) | explicit 200-point `K_POINTS crystal` list without labels; pw.x printed no eigenvalues |
| `al_pdos_flat/` | Al DOS/PDOS tutorial run (QE 7.3.1) | flat layout (no `orbitals/`); PDOS files keep every 4th energy row; `al.projwfc.out` truncated (head + tail) |
| `ni_pdos_spin/` | QE `PP/examples/example02/reference`, **version 6.0** (GPL-2.0) | spin-polarized Ni PDOS; `ni.pdos.out` truncated |
| `si_relax/` | Si relax tutorial run (QE 7.3.1) | `si.rel.in` / `si.rel.out` |
| `kao_vc_relax/` | user's kaolinite bulk vc-relax (QE 7.1) | 25 BFGS steps in the run; keeps steps 0–2 and 23–24, `bfgs converged`, `Final scf calculation` and its SCF, `JOB DONE` |
| `kao_slab_relax/` | user's kaolinite (001) slab relax (QE 7.1) | 42 steps in the run; keeps steps 0–2 and 40–41 |
| `kao_supercell_relax/` | user's kaolinite 2×1×1 slab relax (QE 7.1) | a single step: `bfgs converged in 1 scf cycles and 0 bfgs steps` |

The `kao_*` outputs were trimmed by removing whole BFGS steps between complete steps and the
per-k-point eigenvalue listings of every SCF (everything the relax parser reads is untouched).

The PRD folder layout (`scf.out`, `nscf.out`, `projwfc.out`, `orbitals/`) is built at test time
from `al_pdos_flat/` (see the `al_pdos_orbitals` fixture in `conftest.py`).
