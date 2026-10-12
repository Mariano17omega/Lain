# Spec 36: Deslocamento da legenda (`dx` e `dy`)

| | |
|---|---|
| **Prioridade** | 36 (pequena e independente) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 8 (`ParamField`, `requires`), spec 20 (seção "Legenda"), spec 22 (a legenda de bandas + DOS), spec 23 (grids: `fit_cell`) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho do commit `8d05da9` (campos novos de legenda em `CommonParams` + `draw.add_legend`). |

## Itens de origem (`Ideias.md`)

> - Na sessão 'LEGENDAS' da aba de configurações de grafico, add dois campos 'dx' e 'dy' para o usuario adicionar um deslocamento na posição da legenda para ajustar ela com mais libertade.

O script de referência do usuário já faz isso: `Documentation/Exemplos_plot/plot_bands_pdos-mehg-fixedcolors.py:18-19` define
`LEGEND_DX, LEGEND_DY = 0.0, 0.1` ("fração do painel PDOS: dx > 0 direita, dy > 0 cima") e o `:204` passa
`bbox_to_anchor=(1.0 + LEGEND_DX, 0.5 + LEGEND_DY)` com `bbox_transform=ax_d.transAxes` e `loc='center right'`.

## Situação atual

- `CommonParams` (`core/calculations/params.py:72`) tem `show_legend`, `legend_loc`, `legend_frame`, `legend_size` e
  `legend_transparency`; os campos da seção "Legenda" estão em `COMMON_FIELDS` (`:140-210`). Sem deslocamento.
- `core/plotting/draw.py:93-110` (`add_legend`) é o único lugar que monta a legenda de bandas, PDOS e bandas + DOS (via `finish`,
  `finish_side`, `finish_joined`, `:113-143`), e também do SCF (`calculations/scf.py:224`) e do relax (`calculations/relax.py:248`): com
  `legend_loc == "outside"` usa `loc="upper left"`, `bbox_to_anchor=(1.02, 1.0)` e `borderaxespad=0`; senão, `loc=<escolha>` sem
  `bbox_to_anchor`. As escolhas são `best`, `upper right`, `upper left`, `lower right`, `lower left`, `center right` e `outside`
  (`LEGEND_LOCATIONS`, `params.py:120-128`).
- Em bandas + DOS a legenda mora nos eixos da DOS (`bands_dos/render.py:57`, `finish_joined(figure, ax_dos if dos_handles else ax_bands, …)`):
  o deslocamento é em fração dessa área, como no script.
- Um parâmetro de `CommonParams` sem campo de esquema precisa declarar o tipo (`plot_file` valida por tipo de campo); um campo `float` com
  esquema é validado sozinho. Testes da seção: `tests/test_legend_style.py`.

## Requisitos

### R1: Dois parâmetros

1. `CommonParams.legend_dx: float = 0.0` e `legend_dy: float = 0.0`, em **fração da largura / altura dos eixos** onde a legenda mora
   (positivo: direita / cima), como no script.
2. Dois `ParamField` em `COMMON_FIELDS`, seção "Legenda", depois de "Posição": `"dx"` e `"dy"` (`float`, `minimum=-1`, `maximum=1`,
   `step=0.05`, `requires="show_legend"`), tooltip "Deslocamento horizontal da legenda, em fração da largura do gráfico (positivo:
   direita)" e o equivalente vertical. Valem para todos os módulos que usam `COMMON_FIELDS` (bandas, PDOS, bandas + DOS, SCF, relax).

### R2: `add_legend`

1. Sem deslocamento (`dx == dy == 0`) os argumentos de `ax.legend` são **os de hoje**: figuras e goldens iguais.
2. Com deslocamento: a âncora é o canto (ou o ponto médio) do eixo que corresponde a `legend_loc`
   (`upper right` = (1, 1), `upper left` = (0, 1), `lower right` = (1, 0), `lower left` = (0, 0), `center right` = (1, 0,5)) somada a
   `(dx, dy)`, com `bbox_transform=ax.transAxes` e o mesmo `loc` (a legenda se prende pelo mesmo canto). `outside` parte de (1,02; 1,0) e
   soma `(dx, dy)`.
3. `best` é decidido pelo matplotlib na hora de desenhar e não aceita âncora: com deslocamento diferente de zero, `best` conta como
   `upper right`. O tooltip de `dx`/`dy` diz isso.
4. Valor guardado fora de `[-1, 1]` ou não numérico cai no padrão (validação por tipo de campo, `plot_file`).

### R3: Onde mais aparece

1. Grids (spec 23): a célula desenha com `PlotSession.render(cell, style, params=)`, que já leva `CommonParams`; `fit_cell` mede a legenda
   deslocada. Nenhum código novo, mas há teste (abaixo).
2. Exportação e preview usam o mesmo `render`: figura igual nos dois.

### R4: Testes

- `tests/test_legend_style.py`: o padrão desenha a mesma legenda de `HEAD` (as posições dos artistas, `figure_structure.py`, e os goldens); `dx=0,2` move a
  caixa da legenda para a direita no tamanho esperado (em coordenadas dos eixos) para cada `legend_loc`; `outside` com deslocamento; `best`
  vira `upper right` com deslocamento; valores inválidos voltam ao padrão.
- `tests/test_module_contract.py`: `DummyModule` já usa `COMMON_FIELDS`; o esquema ganha os dois campos.
- `tests/test_figure_regression.py`: goldens sem regenerar.
- `tests/test_grid_render.py`: uma célula com `legend_dx` desloca a legenda **dentro** da célula (a caixa não sai do `SubFigure`).
- `tests/test_plot_file.py`: os dois campos vão e voltam do `<kind>.plot`.

## Fora de escopo
- Arrastar a legenda com o mouse.
- Deslocamento em pontos ou em polegadas (fração do painel, como o script).
- Legendas de módulo próprio fora de `add_legend` (não há).

## Decisões assumidas (confirmar na revisão)
1. Unidade: **fração dos eixos**, a do script de referência. A alternativa (pontos) tira a dependência do tamanho do painel, mas não
   é o que o usuário já usa.
2. Faixa `−1 … 1`: o suficiente para colocar a legenda em qualquer parte de um painel ou além da borda; um valor maior no `.plot` cai no
   padrão (R2.4).
3. Rótulos `dx` e `dy`, os que o usuário pediu.

## Notas de implementação
- Alterados: `core/calculations/params.py` (218 linhas; dois campos e dois `ParamField`), `core/plotting/draw.py` (172; a âncora),
  `tests/test_legend_style.py`, `tests/test_grid_render.py`, `tests/test_plot_file.py`.
- Limites: nenhum arquivo perto de 500.
- Documentação ao implementar: `CLAUDE.md`, parágrafo "Legend and axis text sizes": `legend_dx` / `legend_dy` e a regra do `best`.

## Critérios de aceite e testes
- [ ] Sem deslocamento: `test_figure_regression.py`, `test_legend_style.py` e os goldens passam sem regenerar.
- [ ] `dx`/`dy` movem a legenda em fração do painel para cada posição, inclusive `outside`; `best` com deslocamento = `upper right`.
- [ ] Os campos aparecem na seção "Legenda" de bandas, PDOS, bandas + DOS, SCF e relax, desabilitados com a legenda oculta.
- [ ] Persistência em `.plot` e célula de grid.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
