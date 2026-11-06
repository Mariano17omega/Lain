# Relax

The SCF with `calculation = 'relax'`, `nstep`, `forc_conv_thr` and `&IONS`.

- **Files**: `relax_<prefix>.in`, `relax.qsub`.
- **Fields**: maximum steps (`nstep`, default 50), force convergence (`forc_conv_thr`, default `1e-3` Ry/Bohr), ion
  dynamics (`ion_dynamics`: `bfgs` or `damp`), optional k-mesh. Values already in the SCF become the default.
- Follow it in the [relax plot](../plots/relax.md); when it converges, use "Gerar SCF convergido".

Code: `core/calc_create/types/relax.py`; template `qsub/relax.qsub.j2`.
