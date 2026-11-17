# Relaxation

The SCF with `calculation = 'relax'` or `'vc-relax'`, `nstep`, `forc_conv_thr`, `&IONS` and, for a vc-relax, `&CELL`.

- **Calculation** (`calculation`, shown in the Padrão mode too):
    - `relax` (default): only the atoms move; the cell stays the SCF's.
    - `vc-relax`: the cell relaxes too (`&CELL`).
- **Files**: `relax_<prefix>.in` or `vc-relax_<prefix>.in` (the name follows the chosen calculation), `relax.qsub`. In
  the Avançado mode the name opens empty and the grey text shows the standard name; a typed name holds for both.
- **Fields**: maximum steps (`nstep`, default 100, shown in the Padrão mode too), force convergence (`forc_conv_thr`, default `1e-3` Ry/Bohr), ion
  dynamics (`ion_dynamics`: `bfgs` or `damp`), optional k-mesh. Values already in the SCF become the default.
- **vc-relax only**: **Cell dynamics** (`cell_dynamics`: `bfgs`, `damp-pr`, `damp-w`) and **Pressure** (`press`, kbar,
  default 0). `pw.x` needs `bfgs` on both sides or on neither: when the SCF's pair does not fit, the cell dynamics
  starts as the one that goes with the ion dynamics (`bfgs` with `bfgs`, `damp-pr` with `damp`).
- **Continuing a relax that did not converge**: the input carries the line `! restart_mode = 'restart'` commented out in
  `&CONTROL`. If `nstep` runs out, remove the `!`, raise `nstep` if you want and run again in the same folder, with the
  **same NP and `nk`** (`pw.x` reads the positions from `<outdir>/<prefix>.save`). Slab, Supercell and Molecule on the
  surface have the same field and the same line.
- Follow it in the [relax plot](../plots/relax.md); when it converges, use "Gerar SCF convergido".

Code: `core/calc_create/types/relax.py` (the `&CELL` in `vc_relax.py`); template `qsub/relax.qsub.j2`.
