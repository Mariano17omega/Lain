# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

DFT study: methylmercury (CH3Hg+, "H3CHg") adsorption on kaolinite clay surfaces, using Quantum ESPRESSO (QE). Based on the paper "Atomic-Scale Insights into Methylmercury Complexation on Clay Mineral: A Density Functional Study" (PDF + supplementary in `Literatura/`).

Full task spec and current state: `ideia.md` — read it first, it is the working brief for this repo, not just notes.

No code exists yet in this repo (fresh, no commits). The two `.in` files are reference QE inputs already validated by convergence tests:

- `scf-kaolinite.in` — bulk kaolinite SCF (ibrav=0, explicit CELL_PARAMETERS + fractional ATOMIC_POSITIONS, 34 atoms, k-mesh 6x4x4).
- `scf-H3CHg.in` — isolated methylmercury molecule SCF (ibrav=14 cubic box, celldm(1)=40 Bohr, 5 atoms, Gamma-only). Box-size convergence test showed no energy change from 9x9x9 Å³ upward — this is the required vacuum/box minimum when the molecule sits on a slab.

## What needs to be built

Python generator scripts (pymatgen + ASE) that produce QE SCF inputs for slab models:

- `001` and `010` surface supercells of kaolinite, pristine and with methylmercury adsorbed.
- Supercell is 2x1x1 of the `scf-kaolinite.in` bulk cell (hard computational ceiling — do not go larger).
- Output layout (create if missing):
  - `surface_pure/001/`, `surface_pure/010/`
  - `surface_with_methylmercury/001/`, `surface_with_methylmercury/010/`
- A `reporte.md` describing the full generation workflow.

## Hard constraints (from the brief, do not relax)

- **Never hardcode physical/numerical parameters.** Read `celldm`, `CELL_PARAMETERS`, `ATOMIC_SPECIES`, pseudopotential filenames, `ecutwfc`/`ecutrho`, smearing, `conv_thr`, `mixing_beta`, etc. from `scf-kaolinite.in` and `scf-H3CHg.in` at generation time, and propagate them into generated inputs.
- **K-points must be rescaled**, not copied: derive slab k-mesh from the bulk `6 4 4` mesh scaled by the supercell multiplicity (2x1x1) and slab thickness/vacuum, not reused verbatim.
- Slab vacuum must satisfy the 9x9x9 Å³ minimum box result from the H3CHg convergence test.
- Adsorption site placement must use `pymatgen.analysis.adsorption`: `Slab.get_surface_sites()` for surface atom identification, `AdsorbateSiteFinder.find_adsorption_sites()` for placement — don't hand-place coordinates.
- Pseudopotential directories (`pseudo_dir`) differ between the two reference inputs (different machines/users) — carry over the correct one per system rather than assuming one is canonical.

## Working conventions

- This is a computational chemistry / materials science project, not a general software project — there is no build/lint/test suite. Validate generated QE inputs by inspection (correct namelists, atom counts matching species blocks, cell/k-point consistency), not automated tests.
- Keep generator scripts driven by parsing the reference `.in` files rather than duplicating constants, so regenerating inputs after a bulk convergence re-check stays a one-command operation.
