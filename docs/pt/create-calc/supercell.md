# Supercélula

Repete a estrutura do SCF **n1 × n2 × n3**, como `vc-relax`. O SCF costuma ser o de uma superfície relaxada (vácuo ao
longo de c), mas um bulk também serve (só mudam os padrões de `cell_dofree` e dos átomos fixos).

- **Arquivos**: `vc-relax_<prefix>.in` (`prefix = '<prefix>-<n1>x<n2>x<n3>'`, `nbnd` × cópias), `.qsub`, `geracao.md`.
- **Campos**: **Repetições** ao longo de a, b, c (1 a 8), **Vácuo mínimo** (só verifica e avisa; a célula não muda),
  **Rede de k-points** (vazio = a do SCF dividida pelas repetições), `cell_dofree`, regra de **átomos fixos**
  (camada inferior, espécies e vizinhos, do SCF, nenhum) e a **tolerância de ligação**.
- Avisos: k-points `gamma` mantido pode não bastar; repetir ao longo do vácuo empilha slabs.

Código: `core/calc_create/types/supercell.py`, `core/calc_create/surface/supercell.py`.
