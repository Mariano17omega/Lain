# Relax and VC-Relax

**Detection (`RELAX`)**: `pw.x` output with `calculation = 'relax'` or `'vc-relax'`.

Shows the optimization's progress per step against the input's convergence thresholds. It reads BFGS and also
**damped dynamics** (`ion_dynamics = 'damp'`; `cell_dynamics = 'damp-pr'` or `'damp-w'`): each SCF is a step and the
X axis reads "Passo da dinâmica". Damped dynamics prints no enthalpy, so its vc-relax shows |ΔE|. The `fire` dynamics
is not read:

- **Energy/enthalpy** panel (|ΔE|) and **total force** panel; **Painéis**: *Both*, *Energy / enthalpy*, *Force* or *All*.
- **Y scale**: log or linear; **Limiares** (thresholds: `etot_conv_thr`/`forc_conv_thr` lines); step window
  (`Passo mín.`/`Passo máx.`).
- Legend with the thresholds.

After a relax converged by BFGS, the output's context menu offers **Gerar SCF convergido** (only the `.in`, with the
final structure — see [workflow](../workflow.md)); the output of a damped dynamics does not offer it yet.

Code: `core/calculations/relax.py`, `relax_panels.py`; parser `core/qe/relax.py`, final structure in
`core/qe/final_structure.py`, SCF from relax in `core/qe/scf_from_relax.py`.
