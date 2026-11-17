# Supercélula

Repete a estrutura do SCF **n1 × n2 × n3**, como `relax` ou `vc-relax`. O SCF costuma ser o de uma superfície relaxada
(vácuo ao longo de c), mas um bulk também serve (só mudam os padrões do cálculo, de `cell_dofree` e dos átomos fixos).

- **Cálculo** (`calculation`, aparece também no modo Padrão), como no [Slab](slab.md):
    - SCF com vácuo (superfície): `relax` por padrão, o plano no parâmetro de rede do bulk; `vc-relax` relaxa o plano
      (`cell_dofree = '2Dxy'`), para um material 2D isolado.
    - SCF sem vácuo (bulk): `vc-relax` com `cell_dofree = 'all'` por padrão.
- **Arquivos**: `relax_<prefix>.in` ou `vc-relax_<prefix>.in` (`prefix = '<prefix>-<n1>x<n2>x<n3>'`, `nbnd` × cópias),
  `.qsub`, `geracao.md`.
- **Campos**: **Repetições** ao longo de a, b, c (1 a 8), **Vácuo mínimo** (só num SCF com vácuo; verifica e avisa, a
  célula não muda), **Rede de k-points** (vazio = a do SCF dividida pelas repetições, arredondada para cima: nunca menos densa que a do SCF), `cell_dofree` (só no vc-relax), regra de **átomos
  fixos** (camada inferior, espécies e vizinhos, do SCF, nenhum; os parâmetros de cada regra aparecem só quando ela é
  escolhida) e a **tolerância de ligação** (só com espécies e vizinhos).
- **Campo em dente de serra e correção de dipolo** (só num SCF com vácuo; as caixas `tefield` e `dipfield` aparecem
  também no modo Padrão), como no [Slab](slab.md): as caixas, `edir` e `eamp` nascem como no SCF, para a cadeia de
  uma adsorção usar a mesma escolha. `emaxpos` e `eopreg` são recalculados para a supercélula, salvo quando digitados;
  desligadas, as chaves saem do input. Com cópias ao longo de `edir` (`n3 > 1`) há um vácuo por cópia e a correção
  supõe um só: o campo `dipfield` marca o erro.
- Avisos: k-points `gamma` mantido pode não bastar; repetir ao longo do vácuo empilha slabs.
- **Passos máximos** (`nstep`, padrão 100, também no modo Padrão) e a linha `! restart_mode = 'restart'` comentada em
  `&CONTROL` são os do [Relaxamento](relax.md): se o relax não convergir, descomente a linha e rode de novo.

Código: `core/calc_create/types/supercell.py`, `core/calc_create/surface/supercell.py`.
