# Bandas com DOS

Uma figura com o **eixo de energia compartilhado**: bandas à esquerda, PDOS à direita. Nunca é detectada; nasce de
**duas pastas** selecionadas na grade (uma `BANDS`, uma `PDOS`), por **Bandas com DOS** no menu de contexto ou por
**Plot**/**Gerar Plot** com as duas selecionadas. Fica salva em `plots/` da pasta de bandas.

- Parâmetros de bandas (referência, janela, linhas, cores, canais de spin) e de PDOS (agrupamento, átomos, séries,
  total, preenchimento) juntos, mais `dos_width_ratio` (largura do painel da DOS, padrão 0,35 do painel das bandas).
- `spin_mode` padrão é *Sobreposto*: espelhar tornaria o eixo da DOS simétrico, estranho ao lado das bandas.
- `Gap na legenda` mostra o gap das bandas.
- Os dois painéis usam o E_F das bandas, que em isolantes é o meio do gap: veja
  [Nível de Fermi em isolantes](index.md#fermi-em-isolantes).
- No modo cluster, selecionar as duas pastas remotas e **Plotar** funciona do mesmo jeito (cópias em `tmp_remote/`).

Código: `core/calculations/bands_dos/` (`pair.py` forma o par; `module.py`, `render.py`, `params.py`, `table.py`).
