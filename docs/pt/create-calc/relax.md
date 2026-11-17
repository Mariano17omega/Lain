# Relaxamento

O SCF com `calculation = 'relax'` ou `'vc-relax'`, `nstep`, `forc_conv_thr`, `&IONS` e, no vc-relax, `&CELL`.

- **Cálculo** (`calculation`, aparece também no modo Padrão):
    - `relax` (padrão): só os átomos se movem; a célula fica a do SCF.
    - `vc-relax`: a célula também relaxa (`&CELL`).
- **Arquivos**: `relax_<prefix>.in` ou `vc-relax_<prefix>.in` (o nome segue o cálculo escolhido), `relax.qsub`. No modo
  Avançado, o nome abre vazio e o texto cinza mostra o nome padrão; um nome digitado vale para os dois cálculos.
- **Campos**: passos máximos (`nstep`, padrão 100, aparece também no modo Padrão), convergência das forças (`forc_conv_thr`, padrão `1e-3` Ry/Bohr),
  dinâmica dos íons (`ion_dynamics`: `bfgs` ou `damp`), malha k opcional. Valores já presentes no SCF viram o padrão.
- **Só no vc-relax**: **Dinâmica da célula** (`cell_dynamics`: `bfgs`, `damp-pr`, `damp-w`) e **Pressão** (`press`,
  kbar, padrão 0). O `pw.x` exige `bfgs` nos dois lados ou em nenhum: quando o par do SCF não combina, a dinâmica da
  célula começa com a que combina com a dos íons (`bfgs` com `bfgs`, `damp-pr` com `damp`).
- **Continuar um relax que não convergiu**: o input traz a linha `! restart_mode = 'restart'` comentada em `&CONTROL`. Se o
  `nstep` acabar, tire o `!`, aumente o `nstep` se quiser e rode de novo na mesma pasta, com os **mesmos NP e `nk`** (o `pw.x`
  lê as posições de `<outdir>/<prefix>.save`). Slab, Supercélula e Molécula na superfície têm o mesmo campo e a mesma linha.
- Acompanhe com o [gráfico de relax](../plots/relax.md); ao convergir, use "Gerar SCF convergido".

Código: `core/calc_create/types/relax.py` (o `&CELL` em `vc_relax.py`); template `qsub/relax.qsub.j2`.
