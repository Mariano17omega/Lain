# Spec 20: Gap de energia na legenda (bandas e PDOS)

| | |
|---|---|
| **Prioridade** | 20 (independente das demais; a spec 22 reaproveita o campo e o texto) |
| **Status** | Implementada. Desvios: o handle da PDOS entra na lista explícita de handles (`ax.get_legend_handles_labels()` + o texto), não como artista vazio em `ax.plot`, para `ax.get_lines()` não ganhar um artista; o gap exato vem do primeiro entre NSCF e SCF que **imprimiu** HOMO/LUMO (não só "o NSCF, se existir"), e um par impresso que não abre gap (`lumo − homo ≤ EDGE_TOL`) é conclusivo: metal, sem consultar a curva; `gap_handle` mora em `gap_label.py` e o campo é a constante `LEGEND_GAP_FIELD` de `calculations/params.py` (fora de `COMMON_FIELDS`), colocada depois dos campos comuns, no fim da seção "Legenda". A curva de DOS **encolhe** o gap pela cauda do alargamento (≈ 3σ por borda com limiar `GAP_DOS_REL_TOL = 1e-3`): um alargamento gaussiano de 0,04 eV dá ≈ 0,96 eV para 1,2 eV, e um maior erra mais; por isso o `≈`. Sem PDOS de isolante nas fixtures, a curva só foi ajustada em curvas sintéticas |
| **Depende de** | spec 13 (bandas e PDOS já em pacotes, com spin) |
| **Usada por** | spec 22 (a figura combinada bandas + DOS) |
| **Esforço** | M |

## Itens de origem (`Ideias.md`)

> - Na aba de configurações dos graficos, add um botão para incluir o grap de energia nas legedas do plot. Essa opção deve ser um checkbox e deve aparecer apenas nos graficos de bandas e PDOS.

"Grap de energia" é o **gap de energia** (band gap): o intervalo de energia entre a banda de valência e a banda de
condução, `E_gap = CBM − VBM`. **Não é o nível de Fermi**: a energia de Fermi (ou o HOMO) é um *nível*, um ponto da
escala; o gap é uma *diferença* de dois níveis. Esta spec não toca na linha nem na legenda de E_F.

## Situação atual

- **Bandas já calculam o gap**, mas só o mostram no rodapé:
  - `BandsDataset` (`core/calculations/bands/data.py:96-118`) tem `vbm`, `cbm` e a propriedade `gap`
    (`cbm − vbm`, `None` em metal). Com spin há `edges: dict[str, ChannelEdges]` (`"up"`, `"down"`), e cada
    `ChannelEdges` tem `vbm`, `cbm`, `gap` e `metallic` (l.25-62). Os extremos saem da contagem de elétrons
    (`count_edges`, l.75-82) ou do cruzamento de E_F (`channel_edges`, l.45-62), com tolerância `EDGE_TOL = 1e-3` eV;
    `_band_edges` (l.238-254) e `spin_band_edges` (l.272-287) montam o dataset (os extremos globais só existem se os
    dois canais têm gap).
  - `summary` (`bands/render.py:255-277`) escreve `E_gap = 1.234 eV` e `_spin_gaps` (l.280-289) `gap ↑ 1.234 eV`,
    `↓ metálico`, `gap global …`. Nada disso entra na figura.
  - O gap é uma diferença: não depende de `params.reference` (`fermi|vbm|midgap|absolute`, que só desloca o eixo),
    nem da janela `emin/emax`.
- **A legenda das bandas** (`_render_plain`, l.55-80) tem handles `Valência`, `Condução` e `$E_F$`; o modo de spin
  tem os seus (`_render_spin`, l.96-146; `finish_side` põe a legenda em `axes[0]`, `draw.py:66`). `add_legend`
  (`draw.py:43-55`) só desenha com `show_legend`: desligado por padrão nas bandas (`CommonParams.show_legend=False`),
  ligado na PDOS (`pdos/params.py:67`).
- **A PDOS não tem gap nenhum.** `PdosDataset` (`pdos/data.py:14-38`) guarda só `fermi_scf`/`fermi_nscf`, os E_F por
  canal e a magnetização. Dados disponíveis:
  - `PdosData.energy` (eV, absoluto, sem deslocar) e `PdosData.total: Channel(up, down)` (a soma das projeções
    quando falta `pdos_tot`, `total_is_sum`; `core/qe/projwfc.py`);
  - `PwOutput` do SCF e do NSCF pelo cache de sniff (`load_dataset`, `pdos/data.py:42-56`). Com ocupações **fixas** o
    pw.x imprime `highest occupied, lowest unoccupied level (ev): HOMO LUMO`: `fermi_kind == "homo_lumo"`,
    `fermi` = HOMO e `lumo` (`core/qe/pw_output.py:17-29,126-138`). Com smearing ou tetraedros imprime só a energia
    de Fermi, sem gap. Para spin com magnetização fixa o pw.x imprime **um** HOMO/LUMO para os dois canais.
- **Fixtures:** só `si_bands/si.scf.out` (semicondutor) tem a linha HOMO/LUMO; `al_bands`, `al_pdos_flat` e
  `qe731_ni_spin_*` são metais. **Não há PDOS de isolante nas fixtures**: os testes da PDOS usam curvas sintéticas e
  o `PwOutput` de `si_bands`.
- **Painel:** `ParamField` do tipo `bool` vira `QCheckBox` (`ui/widgets/params_body.py:178-183`); um campo só aparece
  em quem o declara em `param_schema`; a seção "Legenda" tem `show_legend`, `legend_loc` e `legend_frame`
  (`COMMON_FIELDS`, `core/calculations/params.py:126-128`). SCF e relax têm esquema próprio e nunca veem um campo
  declarado só em bandas e PDOS.

## Requisitos

### R1: Parâmetro `legend_gap`
1. `BandsParams.legend_gap: bool = False` e `PdosParams.legend_gap: bool = False`.
2. `ParamField("legend_gap", "Gap de energia na legenda", "Legenda", "bool")` no `param_schema` de bandas e de PDOS,
   **sempre** (não depende do dataset, para o painel não mudar de forma). Tooltip: "Mostra o gap (CBM − VBM) na
   legenda. Sem efeito com a legenda oculta ou em sistema metálico."
3. Fora de `COMMON_FIELDS`: SCF e relax não mudam. O `.plot` grava o bool como qualquer outro; um `.plot` sem o
   campo continua carregando (padrão desligado, `apply_stored`).

### R2: O texto da legenda
1. `core/plotting/gap_label.py:gap_label(value, channel=None, approx=False) -> str` (Qt-free, em `QT_FREE`):
   - `$E_{gap}$ = 1.234 eV` (3 casas, ponto decimal, o formato do rodapé; nome `E_gap` como em
     `Y_LABELS["midgap"]` e no `summary`);
   - canal de spin: `$E_{gap}$ ↑ = 1.234 eV`, `$E_{gap}$ ↓ = …`; global quando há entradas por canal:
     `$E_{gap}$ global = …`;
   - `approx=True` (gap lido da curva de DOS): `$E_{gap}$ ≈ 1.23 eV` (2 casas, que é a resolução da grade).
2. A entrada é **só texto**: handle invisível (`Line2D([], [], linestyle="none", label=texto)`), sem marcador e sem
   sombrear o gap na figura. Vai depois das demais entradas da legenda.
3. O valor é sempre a diferença CBM − VBM: não muda com `reference`, `emin/emax`, orientação ou com o gap ficar
   fora da janela visível.
4. Sem gap (metal, gap indeterminável): **nenhuma** entrada; o campo continua no painel e não faz nada. Não se escreve
   "metálico" na legenda.
5. Com `show_legend` desligado o campo não tem efeito e não liga a legenda sozinho.

### R3: Bandas
1. `bands/gap.py:gap_entries(dataset) -> list[GapEntry(channel, value)]`, **uma** função para o rodapé e a legenda,
   com a regra que o `summary` já usa:
   - sem spin: uma entrada global (`dataset.gap`), ou nenhuma se for metal;
   - spin com os dois canais: `↑` e `↓` (os que têm gap) e a global quando `dataset.gap` existe;
   - spin só com o canal ↑ (`edges["up"]`): só `↑`.
   `summary` e `_spin_gaps` passam a consumir `gap_entries` (o texto do rodapé **não muda**, ver testes).
2. Com `legend_gap`, `_render_plain` e `_render_spin` (empilhado e lado a lado) acrescentam um handle por entrada, via
   `gap_label`. No layout lado a lado a legenda continua no primeiro eixo.

### R4: PDOS
1. `PdosDataset.gap: GapInfo | None` (`GapInfo(value, source)`, `source` em `"homo_lumo" | "dos"`), calculado em
   `load_dataset` (worker), por esta ordem:
   1. **exato:** o `PwOutput` do NSCF e, na falta dele, o do SCF, com `fermi_kind == "homo_lumo"` e `lumo` definido:
      `value = lumo − fermi` (aqui `fermi` é o HOMO); só vale se `> EDGE_TOL`, senão é metal;
   2. **pela DOS:** `core/qe/projwfc.py:dos_gap(energy, total, fermi) -> float | None`, com `total` = soma dos canais
      de **todos** os átomos (`PdosData.total`, `pdos_tot` ou a soma completa; nunca a seleção de átomos da spec 21,
      o gap é do sistema). Limiar `GAP_DOS_REL_TOL = 1e-3` vezes o máximo da DOS total; a região contígua com DOS ≤ limiar
      mais próxima de E_F, a até `GAP_SEARCH_EV` (0,25 eV) de E_F; `value` = largura entre o último ponto acima do limiar
      abaixo da região e o primeiro acima dela. Sem E_F, E_F dentro de uma banda (metal), ou região que toca a borda da
      grade (sem estados de um dos lados) → `None`;
   3. nenhum dos dois → `None`.
2. Na legenda: `gap_label(value)` para `"homo_lumo"` e `gap_label(value, approx=True)` para `"dos"`. **Uma** entrada só
   (o pw.x imprime um HOMO/LUMO para os dois canais; a DOS usa a soma dos canais), sem entradas por spin.
3. `render_pdos` acrescenta o handle em todos os modos (`mirror`, `overlay`, `up`, `down`, `sum`, nas duas orientações).
   Onde a legenda vem dos artistas rotulados (`handles=None`), o handle entra como artista rotulado sem dados
   (`ax.plot([], [], linestyle="none", label=texto)`); no `overlay`, entra junto aos handles montados à mão.
4. Constantes (`GAP_DOS_REL_TOL`, `GAP_SEARCH_EV`) com nome e comentário em `projwfc.py`; o ajuste fino é feito na
   implementação, com os testes de R6 como rede.

### R5: Figura combinada (spec 22)
A spec 22 reaproveita `legend_gap` e `gap_label` na parte das bandas e da DOS. Na figura combinada o gap vem **das
bandas** (exato, `gap_entries`), uma entrada só no eixo da DOS; o gap da PDOS não entra aí (os dois eixos de energia são
os mesmos).

## Fora de escopo
- Desenhar o gap na figura (faixa sombreada entre VBM e CBM, setas, marcadores de VBM/CBM).
- Dizer se o gap é **direto** ou **indireto**, ou onde ficam o VBM e o CBM no caminho k.
- Gap por canal de spin na PDOS (o pw.x só dá um par HOMO/LUMO).
- Mostrar o gap no rodapé da PDOS (`RenderInfo.summary` dela não muda).
- Qualquer coisa sobre a **energia de Fermi** na legenda: a entrada `$E_F$` das bandas continua como está.
- Gap óptico, de quase-partícula ou de outros métodos; correções (scissor).

## Decisões assumidas (confirmar na revisão)
1. "Grap de energia" = **gap de energia** (correção em relação à primeira versão desta spec).
2. A entrada é só texto (sem marcador nem sombra); sombrear o gap fica para uma spec futura.
3. O campo existe sempre em bandas e PDOS e não faz nada quando não há gap, em vez de aparecer e sumir com o dataset.
4. Metal: sem entrada (não se escreve "metálico" na legenda; o rodapé das bandas já diz).
5. PDOS: gap exato do HOMO/LUMO impresso pelo pw.x quando existe; senão, lido da curva de DOS e marcado com `≈`. Como
   a maioria das PDOS usa smearing ou tetraedros (sem HOMO/LUMO impresso), o caso da DOS é o comum, e é aproximado
   (erro ≈ `DeltaE` do projwfc, tipicamente 0,01 eV, mais o alargamento).
6. Símbolo `E_{gap}` (como o rodapé e o rótulo do meio do gap), 3 casas nas bandas e 2 com `≈`.
7. Spin nas bandas: por canal e global, as mesmas entradas do rodapé.
8. Padrão **desligado**, para as figuras e os goldens atuais ficarem idênticos.

## Notas de implementação
- Novos: `core/plotting/gap_label.py`, `core/calculations/bands/gap.py`. `gap_label.py` entra em `QT_FREE`
  (`tests/test_architecture.py`).
- Alterados: `bands/params.py` (campo e esquema), `bands/render.py` (`_render_plain` l.55-80, `_render_spin`,
  `summary`/`_spin_gaps` passam a usar `gap_entries`), `pdos/params.py` (campo e esquema), `pdos/data.py`
  (`PdosDataset.gap`, `load_dataset`), `pdos/render.py` (`render_pdos`, ramo `overlay`), `core/qe/projwfc.py`
  (`dos_gap`, constantes).
- `RenderInfo`, `format_coordinates`, `apply_limits` e `ParamsBody` não mudam (campo `bool` já existe).
- A leitura é toda em `load_dataset` (worker); a GUI só desenha.

## Critérios de aceite e testes
- [ ] Padrão desligado: `test_figure_regression.py`, `test_bands_spin_render.py` e `test_pdos_spin.py` passam sem
      regenerar goldens; o rodapé das bandas é idêntico ao de hoje (`E_gap = …`, `gap ↑ … · gap global …`, `metálico`).
- [ ] `gap_label`: valor, canais ↑/↓/global, `approx` com `≈` e 2 casas (função pura, sem Qt).
- [ ] Bandas, semicondutor (`si_bands`): com `legend_gap` e legenda visível, a legenda contém `$E_{gap}$ = <dataset.gap>`
      e o valor é o do rodapé; mudar `reference` (fermi, vbm, midgap, absolute) e `emin/emax` não muda o texto.
- [ ] Bandas, metais (`al_bands`, `qe731_ni_spin_bands`): nenhuma entrada de gap, com o campo ligado.
- [ ] Bandas com spin (dataset sintético dos testes de `test_bands_spin_render.py`): dois canais com gap → entradas `↑`,
      `↓` e global; canal ↓ metálico → só `↑`; run só com ↑ → só `↑`; layouts empilhado e lado a lado.
- [ ] `gap_entries`: o rodapé (`summary`) é gerado a partir dela e os testes existentes de `summary` seguem verdes.
- [ ] PDOS, exato: `PwOutput` de `si_bands/si.scf.out` (HOMO/LUMO) vira `GapInfo(lumo − homo, "homo_lumo")`; NSCF tem
      precedência sobre o SCF; `lumo − homo ≤ EDGE_TOL` → `None`.
- [ ] PDOS, pela DOS (curvas sintéticas): isolante com gap de 1,2 eV e E_F no meio → `≈ 1,2 eV` dentro de `DeltaE`; E_F
      na borda da banda; metal (`al_pdos_flat`, `qe731_ni_spin_pdos`) → `None`; sem E_F → `None`; região sem estados de
      um dos lados → `None`; spin soma os canais.
- [ ] PDOS: o gap **não** muda com a seleção de átomos da spec 21 (usa o total do sistema).
- [ ] PDOS: a entrada aparece com `legend_gap` e legenda visível em `mirror`, `overlay`, `up`, `down`, `sum`, nas duas
      orientações; com `≈` quando vem da DOS; sem entrada em metal.
- [ ] SCF e relax: `param_schema` não contém `legend_gap`.
- [ ] `.plot`: ida e volta do campo; `.plot` antigo sem o campo carrega (`test_plot_file.py`).
- [ ] `test_module_contract.py::test_every_schema_field_belongs_to_a_section`: a seção "Legenda" existe nos dois módulos.
- [ ] `test_architecture.py`: `gap_label.py` sem PyQt6, todos os arquivos abaixo de 500 linhas.
