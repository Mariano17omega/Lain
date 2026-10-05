# Spec 22: Bandas com DOS na mesma figura

|                |                                                                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Prioridade** | 22                                                                                                                                |
| **Status**     | Implementada. Desvios:<br>- Os dois datasets carregam um após o outro no mesmo worker, não em paralelo. Uma segunda mecânica de threads iria contra a spec 15 R1, e o GIL ganharia pouco. Cada parte usa o `load_cached` do seu módulo.<br>- O par exige resultados `plottable`: bandas lidas só da saída do pw.x também valem, como no gráfico isolado.<br>- Seções: as comuns ficam sem prefixo ("Energia" é o eixo compartilhado, mais Estilo, Legenda, Figura e Exportar). Com prefixo ficam "Bandas ▸ Eixo k", "Bandas ▸ Cores", "Bandas ▸ Spin", "DOS ▸ Eixo" e "DOS ▸ Projeções".<br>- A legenda fica fora do eixo por padrão.<br>- `dos_folder` é derivado (`metadata={"derived": True}`): é gravado no `.plot`, mas nunca reaplicado. `PairTarget.from_plot_file` o lê para reabrir o par.<br>- Os erros ("Pasta da DOS não encontrada", par desfeito) seguem o caminho de falha de carga: rodapé + diálogo, e a aba aberta fica como estava.<br>- `RenderInfo.notes` agora aparece no painel de ajustes. Antes nenhuma tela a mostrava.<br>- `PlotView.paths` faz renomear a pasta da DOS fechar a aba.<br>- O par vem de `core/detection.py:PairTarget`, que detecta as duas pastas no worker.<br>- Duas pastas que têm bandas e PDOS cada uma não formam par. |
| **Depende de** | spec 13 (bandas e PDOS em pacotes, com spin), spec 16 (multi-seleção na grade), spec 20 (gap na legenda), spec 21 (átomos da DOS) |
| **Usada por**  | spec 23 (a figura combinada pode ir numa célula do Grid)                                                                          |
| **Esforço**    | G                                                                                                                                 |

## Itens de origem (`Ideias.md`)

> - Add um botão 'Bandas com DOS' no menu do botão direito do mouse. Esse botão só apareve quando o usuario seleciona uma pasta com calculo de Bandas e uma pasta com calculo de DOS. O botão 'Bandas com DOS' plotar as bandas e a DOS no mesmo grafico, com o mesmo eixo de energia (eixo y).

Também é o item F5 do `report.md` ("Bandas + DOS combinados"), antes adiado.

## Situação atual

- Contrato (`core/calculations/base.py:337`): `render(figure, dataset, params, style) -> RenderInfo`; o módulo
  é dono da figura inteira. Ajudantes de eixos em `core/plotting/draw.py`: `new_axes` (:15, `clear` +
  `add_subplot`), `stacked_axes` (:23), `side_axes` (:33, `sharex=True, sharey=True`, não serve para k × DOS),
  `finish`/`finish_side` (:58, :66; título, legenda, `tight_layout`).
- **Bandas** (`bands/render.py`): `_render_plain` (l.40-92) com energia em y: `energies - ref`,
  `ref = dataset.reference(params.reference)` (`fermi|vbm|midgap|absolute`, `bands/data.py:120`), `LineCollection`,
  `axhline(fermi - ref)`, `set_ylim(emin, emax)`. Reutilizáveis: `merged_ticks`, `tick_labels`, `shown_channels`,
  `_draw_channel`, `_fermi_lines`, `summary`, `format_coordinates`. A referência vem do SCF das bandas
  (papel `scf_out`, possivelmente de pasta vizinha por `infer_from_neighbours`).
- **PDOS** (`pdos/render.py`): `render_pdos` (l.65-164) é uma função só, com closures, que chama `new_axes` e
  `finish`. **A orientação vertical já existe** (`vertical = params.orientation == "vertical"`, l.80): desenha
  `ax.plot(values, energy)`, `fill_betweenx`, `axhline`/`axvline`, limites trocados (l.99-145). A referência é
  `fermi_source` + `shift_to_fermi` (l.70-71). Espelhamento de spin (`mirror`) torna o eixo da DOS simétrico.
  `PdosModule.apply_limits` (`pdos/module.py:131-136`) troca x e y quando vertical.
- "DOS" para o Lain é a PDOS: `FileKind.DOS_OUT` é só o stdout do dos.x e **não há leitor** de `fildos`
  (`core/sniff.py:37-51`, `file_types.py:19`). Sem `pdos_tot`, o total é a soma das projeções
  (`PdosData.total_is_sum`, `projwfc.py:196-200`).
- Menu de contexto: `ItemActions.show` chama `multi_menu(paths)` (`ui/widgets/context_menu.py:71,129`) quando a
  seleção não é de um item; hoje só lê `is_dir`, `input_pair` (l.150) e favoritos. `DetectionService.peek_results(
folder)` (`ui/services.py:62-65`) dá os resultados **só do cache**; `results(folder)` agenda detecção. Uma
  pasta pode ter vários resultados (bandas e PDOS juntos → `Ambiguous`, `core/detection.py:101-105`): usar `any`.
  Multi-seleção existe só na grade (`FilePanel`); a árvore emite lista de um item.
- Regra de arquitetura: `ui/` não conhece módulo (`kind == "bands"` é proibido em `ui/*.py`, teste em
  `test_module_contract.py:183`), então "é um par bandas + DOS" é decisão do `core/`.
- Plot manual: `ManualTarget(module, folder, mapping, sniff)` (`core/detection.py:80-95`) aceita arquivos
  forçados, inclusive fora da pasta (`base.py:229-233`); módulo sem papel `anchor` nunca é detectado sozinho
  (`base.py:251`); `plot_target(folder, files)` (`base.py:323-326`) decide chave e nome da aba;
  `plottable_modules()` (`core/detection.py:154-157`) alimenta o combo do diálogo de mapeamento.
- Sessão e abas: chave `plot:<kind>:<target>` (`core/plotting/session.py:108`); `.plot` por pasta e tipo
  (`plot_file_path`, `session.py`/`plot_file.py:29`); export em `<session.folder>/plots/<stem>` (`export.py:56`).

## Requisitos

### R1: Item "Bandas com DOS" no menu de contexto

1. Aparece em `multi_menu` **somente** quando a seleção tem exatamente duas pastas e
   `bands_dos_pair(peek_results(a), peek_results(b))` devolve um par (uma das pastas tem resultado de bandas e a
   outra, de PDOS, em qualquer ordem). Qualquer outra seleção deixa o menu como hoje (os textos de
   `tests/test_multi_selection.py` não mudam).
2. `core/calculations/bands_dos/pair.py:bands_dos_pair(a, b) -> BandsDosPair | None` (Qt-free) usa os resultados
   do cache; `ItemActions` não lê `kind`. Pasta ainda sem cache: `service.results(pasta)` agenda a detecção e o
   item aparece no próximo menu (como `file_actions_of`).
3. Os resultados do par têm de ser `plottable` (bandas com `gnu` ou `filband`; PDOS com `pdos_atm`). Pasta
   incompleta → sem item (o mapeamento manual continua sendo o caminho).
4. Clicar emite `bands_dos_requested(Path, Path)` → `PlotWorkflow.plot_pair(bands, dos)`, que carrega os dois
   datasets em paralelo no pool global e renderiza na GUI (como `plot_file`).

### R2: Módulo `bands_dos`

1. Pacote `core/calculations/bands_dos/` (`module`, `pair`, `params`, `render`), `CalculationModule` com
   `kind = "bands_dos"`, **sem** papel `anchor` (nunca detectado sozinho) e fora do combo de mapeamento
   (`ClassVar selectable = False`, lido por `plottable_modules()`).
2. Dataset: `BandsDosDataset(bands: BandsDataset, dos: PdosDataset)`, montado por `load` a partir de duas
   `DetectionResult` (as do par) e do cache de sniff, reaproveitando `bands.load` e `pdos.load`.
3. `plot_target(folder, files)` devolve a pasta das bandas; a chave da aba é
   `plot:bands_dos:<bandas>|<dos>` e o título "Bandas + DOS — <fórmula>".

### R3: Figura

1. Dois eixos lado a lado com **eixo y compartilhado** (energia): `draw.py:bands_dos_axes(figure, ratios)` =
   `figure.subplots(1, 2, sharey=True, gridspec_kw={"width_ratios": ratios})`, sem espaço horizontal entre
   eles. Bandas à esquerda (k em x), DOS à direita (densidade em x, energia em y).
2. `render_pdos` é dividido em `draw_pdos(ax, dataset, params, style, ref, …)`, que desenha na `ax` recebida
   (a orientação vertical atual), e o `render_pdos` que chama `new_axes` + `draw_pdos` + `finish`. Bandas:
   `_render_plain`/`_draw_channel` ganham o mesmo corte. Nenhum comportamento de bandas ou PDOS isolados muda
   (`test_figure_regression.py` passa sem regenerar goldens).
3. **Referência única:** a das bandas (`dataset.bands.reference(params.reference)`), aplicada a
   `bands.energies - ref` e `dos.energy - ref`. Se E_F do cálculo da PDOS diferir do das bandas em mais de
   0,05 eV, `RenderInfo.notes` traz "E_F da DOS difere do das bandas em x eV".
4. Limites de energia (`emin`, `emax`) e linha de Fermi em comum; o x da DOS começa em 0 (ou simétrico, ver R4).
5. Legenda uma só, no eixo da DOS (ou das bandas, se a DOS não tem série); com `legend_gap` (spec 20) a
   entrada do gap vem **uma vez**, das bandas (`gap_entries`, exato) e de `gap_label`; o gap da PDOS não entra
   (os dois eixos de energia são os mesmos).

### R4: Parâmetros (`BandsDosParams`)

1. Estende `CommonParams`. Campos das bandas: `reference`, `emin`, `emax`, `xmin`, `xmax`, `labels`,
   `show_hs_lines`, `show_fermi_line`, `valence_color`, `conduction_color`, `fermi_color` (e os de spin). Campos da DOS:
   `dos_width_ratio` (padrão 0,35), `grouping`, `hidden_series`, `series_colors`, `orbital_colors`,
   `show_total`, `fill_occupied`, `spin_mode` (padrão `overlay` aqui; `mirror` continua disponível),
   `atoms` (spec 21, mesmo `CompoundStore`) e `legend_gap` (spec 20).
2. Seções do painel: as das bandas e as da PDOS, com prefixo no título ("Bandas ▸ Energia", "DOS ▸ Projeções")
   por `ParamField.section`, sem código de UI específico.
3. `apply_limits` mapeia o eixo das bandas a `emin/emax/xmin/xmax` e o da DOS ao limite de densidade (a y
   compartilhado vale para os dois). `format_coordinates` por eixo (`axes_index` 0 = bandas, 1 = DOS).

### R5: Persistência e exportação

1. `bands_dos.plot` na pasta das bandas (YAML, `plot_file.py`), com `dos_folder` (caminho relativo à pasta das
   bandas) para a regeneração e a reabertura reencontrarem a DOS. Campo `kind: "text"` no dataclass, validado
   como os demais.
2. Se `dos_folder` não existe mais, regenerar mostra o erro "Pasta da DOS não encontrada" na aba (sem exceção).
3. Exportação: `plots/bands_dos.<ext>` na pasta das bandas, com as regras de `plan_export` (nunca sobrescreve
   sem perguntar).

## Fora de escopo

- DOS total do `dos.x` (`fildos`): continua sem leitor (F2). Só PDOS.
- Mais de uma DOS ou mais de um cálculo de bandas na mesma figura; sobrepor simulações (F9).
- Posicionar a DOS à esquerda ou acima.
- Item de menu para uma pasta só com bandas e PDOS juntas (o caminho do usuário é a multi-seleção).

## Decisões assumidas (confirmar na revisão)

1. "Cálculo de DOS" = pasta com resultado `pdos`; sem `pdos_tot` usa-se a soma das projeções, como hoje.
2. Referência única das bandas para os dois eixos; E_F divergente só avisa (não corrige sozinho).
3. Spin da DOS: `overlay` por padrão na figura combinada (o espelhado deixa o eixo da DOS simétrico e
   confunde ao lado das bandas), mas todos os modos ficam disponíveis.
4. `bands_dos.plot` fica na pasta das bandas, que é a pasta "dona" da aba e a âncora do `plot_target`.
5. A DOS usa a seleção de átomos salva do composto (spec 21). Se os compostos das duas pastas não coincidirem
   (chaves diferentes), a seleção da DOS vale só para o composto da DOS e há aviso em `RenderInfo.notes`.

## Notas de implementação

- Novos: `core/calculations/bands_dos/{__init__,module,pair,params,render}.py` (cada um < 500 linhas),
  registro em `core/calculations/__init__.py:REGISTRY`.
- Alterados: `core/plotting/draw.py` (`bands_dos_axes`), `pdos/render.py` (`draw_pdos`),
  `bands/render.py` (corte do desenho de um canal), `core/calculations/base.py` (`selectable`),
  `core/detection.py` (`plottable_modules`), `ui/widgets/context_menu.py` (item + sinal), `ui/plot_workflow.py`
  (`plot_pair`), `ui/main_window.py` (uma linha de `connect`; arquivo em 475/500 linhas).
- `pdos/render.py` e `bands/render.py` hoje têm o desenho acoplado a `figure`; extrair `draw_*` primeiro, com
  `test_figure_regression` como rede, antes de escrever o módulo novo.
- `main_window.py` não deve crescer: se faltar espaço, mover `compare_inputs`/`open_summary` para um pequeno
  `ui/tab_openers.py`.

## Critérios de aceite e testes

- [ ] Refatoração: `test_figure_regression.py`, `test_bands_spin_render.py`, `test_pdos_spin.py` passam sem
      regenerar goldens depois de extrair `draw_pdos` e o corte das bandas.
- [ ] `bands_dos_pair`: bandas + PDOS (qualquer ordem) → par; bandas + bandas, PDOS + PDOS, uma pasta sem
      resultado, pasta incompleta, três pastas → `None`; uma pasta com bandas **e** PDOS (resultado
      `Ambiguous`) forma par com outra pasta de bandas ou de PDOS, escolhendo o resultado que falta.
- [ ] Menu: com bandas + PDOS selecionados, o item "Bandas com DOS" aparece; os outros menus não mudam
      (`test_multi_selection.py::test_menu_of_three_items` etc. intactos). Sem cache de detecção, o item
      aparece depois que a detecção chega.
- [ ] Sem `kind == "<tipo>"` em `ui/` (`test_module_contract.py`); `DummyModule` cobre `selectable`.
- [ ] Figura: dois eixos, `sharey` verdadeiro, mesma escala de y, `width_ratios` respeitado; E_F em 0 nos dois
      com referência `fermi`; com `absolute`, as duas energias na mesma escala.
- [ ] E_F divergente (>0,05 eV) entre bandas e DOS → nota em `RenderInfo.notes`; igual → sem nota.
- [ ] Spin (`qe731_ni_spin_bands` + `qe731_ni_spin_pdos`): dois canais das bandas e DOS em `overlay` sem erro;
      com `legend_gap` ligado a legenda tem **uma** entrada de gap, a das bandas (`gap_label`); metal → nenhuma.
- [ ] `bands_dos.plot`: ida e volta com `dos_folder` relativo; pasta da DOS movida → mensagem na aba.
- [ ] Abas: `plot:bands_dos:<a>|<b>` abre uma vez; reabrir foca a mesma; fechar grava o `.plot`.
- [ ] Exportação `plots/bands_dos.png` sem sobrescrever sem perguntar.
- [ ] O módulo não aparece no combo do diálogo de mapeamento.
