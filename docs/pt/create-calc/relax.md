# Relax

O SCF com `calculation = 'relax'`, `nstep`, `forc_conv_thr` e `&IONS`.

- **Arquivos**: `relax_<prefix>.in`, `relax.qsub`.
- **Campos**: passos máximos (`nstep`, padrão 50), convergência das forças (`forc_conv_thr`, padrão `1e-3` Ry/Bohr),
  dinâmica dos íons (`ion_dynamics`: `bfgs` ou `damp`), malha k opcional. Valores já presentes no SCF viram o padrão.
- Acompanhe com o [gráfico de relax](../plots/relax.md); ao convergir, use "Gerar SCF convergido".

Código: `core/calc_create/types/relax.py`; template `qsub/relax.qsub.j2`.
