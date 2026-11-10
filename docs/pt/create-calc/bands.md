# Bandas

SCF, `pw.x` com `calculation='bands'` ao longo de um caminho de alta simetria, e `bands.x`.

- **Arquivos**: o SCF, `bands.in` (pw.x), `bands_pp.in` do `bands.x` (ou `bands_pp_up.in` / `bands_pp_dw.in` para um
  SCF com spin colinear — um por canal) e `bands.qsub`.
- **Campos**: **Caminho de alta simetria** (pontos com rótulos; botão *Distribuir pelo comprimento*; o Lain avisa
  segmentos que colapsam no eixo x do `bands.x`), **Arquivo das bandas** (`filband`, padrão `./band`;
  `./band_up`/`./band_dw` por canal). No modo Padrão só o caminho é pedido: `nbnd` vem do SCF.
- **Avisos**: segmentos que colapsam no eixo x; dois pontos do caminho iguais em sequência (o `bands.x` deixa o
  `.gnu` vazio); `tot_magnetization` no SCF (o `bands.x` do QE aborta com magnetização restrita: os `pw.x` rodam e as
  bandas só saem da saída do `pw.x`). Um `disk_io` `nowf`, `minimal` ou `none` é tirado dos inputs gerados, com aviso,
  porque o `bands.x` precisa dos `wfc*.dat`.
- **Script**: pw.x SCF → pw.x bands → `bands.x` (um por canal).
- O resultado é detectado como `BANDS` — veja [bandas](../plots/bands.md).

Código: `core/calc_create/types/bandas.py`, `core/calc_create/kpath.py`; template `qe/bandas/bands_pp.in.j2`,
`qsub/bands.qsub.j2`.
