# VC-Relax

O relax mais `&CELL`: a célula também relaxa.

- **Arquivos**: `vc-relax_<prefix>.in`, `vc-relax.qsub`.
- **Campos** do relax mais **Dinâmica da célula** (`cell_dynamics`: `bfgs`, `damp-pr`, `damp-w`) e **Pressão**
  (`press`, kbar, padrão 0).
- Herda de `RelaxType`.

Código: `core/calc_create/types/vc_relax.py`; template `qsub/vc-relax.qsub.j2`.
