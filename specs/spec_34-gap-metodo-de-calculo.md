# Spec 34: Gap de energia — método de cálculo escolhido pelo usuário (bandas, PDOS e bandas com PDOS)

| | |
|---|---|
| **Prioridade** | 34 (o aviso "metálico" do item 1 já foi corrigido em `f5492fb`; o valor que o usuário espera só vem com o método do R1) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 13 (spin), spec 20 (gap na legenda: `gap_entries`, `legend_gap`), spec 21 (a seleção de átomos não muda o gap), spec 22 (bandas + DOS), spec 27-6 (regras de E_F e "no caminho") |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda o contrato de `gap_entries` / `summary` (usado pelo rodapé e pela legenda de bandas, PDOS e bandas + DOS) e mexe em física do gap. |

## Itens de origem (`Ideias.md`)

> - O botão para mostrar o gap de energia no grafico de bandas, na sessão 'LEGENDAS' da aba de configurações de grafico não funciona. O Sistema é um isolante com gap maior de 1 eV, mas quando clico no botão, aparece o aviso dizendo que ão é possivel calcular o gap porque o sistema é metalico.
>
> - Em 'Documentation/Exemplos_plot/' tem dois scripts de plot de bandas e pdos. Eles possuem duas formas de calcular o GAP de energia, um usa HOMO/LUMO (do scf.out) e outro detarmina a ultima banda ocupada e a primeira vazia e calcula a diferença entre elas. Quero que implemente os dois metodos de calculo de gap de energia, de forma que o usuario possa escolher qual metodo usar no plot de bandas, pdos, e bandas com pdos.

Os dois itens são o mesmo problema: o gap que o app mostra não é o que o usuário calcula nos scripts dele, e ele quer escolher o método.

## Situação atual

- **R1 (item 1, reproduzido).** Com a pasta real do usuário `Documentation/Exemplo-bands-010-mehg-O1` (365 bandas × 81 k, 495 elétrons, `smearing`,
  E_F = −2,8805 eV; `bands.plot` com `legend_gap: true`): **antes de `f5492fb`** `ds.gap` era `None`, o rodapé dizia "metálico" e a
  legenda ganhava `NO_GAP_NOTE` ("Sem gap para a legenda: sistema metálico ao longo do caminho", `core/calculations/bands/gap.py:43`):
  é a queixa. **Em `HEAD`** (`fermi_edges`, `bands/data.py:277-291`) o gap é **0,0724 eV**, com a nota "gap pela posição de E_F: 495
  elétrons não enchem bandas inteiras" e a legenda `E_gap = 0.072 eV`. O aviso sumiu; o valor continua longe do "maior que 1 eV" do
  usuário: a contagem cai entre duas bandas planas coladas em E_F (`n=247`: topo −2,9351 eV, base da seguinte −2,8627 eV).
- **R2 (item 2, os dois métodos dos scripts).**
  - `Documentation/Exemplos_plot/plot_pdos-no_HCHg.py:53-96`: lê o par `highest occupied, lowest unoccupied level` do `scf.out`
    (HOMO/LUMO) e a E_F; gap = `LUMO − HOMO`. Sem o par (`:96`) cai num gap lido da DOS (`detect_gap_from_dos`, `:142-181`): a maior
    região com `DOS < 1,0 estados/eV` (tolerância **absoluta**) cujo centro está em (−7, 6) eV, largura mínima 0,05 eV.
  - `Documentation/Exemplos_plot/plot_bands_pdos-mehg-fixedcolors.py:82-92`: "maior intervalo sem estados dentro da janela visível":
    ordena todas as energias `E − E_F` (todas as bandas, todos os k), fica com as que estão em `(E_min, E_max)` e toma o **maior espaçamento
    entre vizinhas**; VBM e CBM são as duas vizinhas. (O usuário descreve este método como "última banda ocupada e primeira vazia"; o
    código é o do maior intervalo, e a contagem de bandas é o que o app já faz.)
  - No exemplo do item 1 o método da janela dá **3,764 eV** (de +0,432 a +4,196 eV em relação a E_F, janela −2…8 eV); o HOMO/LUMO não existe
    (`smearing`: o `scf.out:1691` só traz a E_F).
- **O app hoje.** Bandas: contagem de elétrons, `band_edges` (`bands/data.py:243-274`), com `fermi_edges` para contagem ímpar;
  `gap_entries(dataset)` (`bands/gap.py:25-44`) lê só o dataset (calculado no worker) e é a **fonte única** do rodapé
  (`bands/render.py:306-340`, `summary(dataset)`) e da legenda (`gap_handles`, `legend_gap_notes`). PDOS: `PdosDataset.gap`
  (`pdos/data.py:27,79`) vem de `pdos_gap` (`pdos/gap.py:21-37`: o par HOMO/LUMO impresso, senão `projwfc.dos_gap`,
  `core/qe/projwfc.py:230-260`, tolerância relativa `GAP_DOS_REL_TOL = 1e-3` do pico e busca a até `GAP_SEARCH_EV = 1,0` eV de E_F); a
  legenda a lê em `pdos/render.py:95-98`. Bandas + DOS usa só o gap das bandas (`bands_dos/render.py:56,59`). O par HOMO/LUMO só existe
  com ocupações fixas e `nbnd` maior que as bandas ocupadas (`PwOutput.fermi_kind == "homo_lumo"`, `pw_output.py:17,128-139`; `lumo` em
  `:51`). Nenhum campo de método existe: `LEGEND_GAP_FIELD` (`calculations/params.py:131-138`) é só o `bool`.

## Requisitos

### R1: Parâmetro `gap_method`

1. Novo `GAP_METHOD_FIELD` em `core/calculations/params.py` (junto de `LEGEND_GAP_FIELD`): `ParamField("gap_method", "Método do gap", "Legenda",
   "choice", requires="legend_gap")`, valores `auto` ("Automático"), `homo_lumo` ("HOMO/LUMO do SCF") e `janela` ("Maior intervalo na
   janela"). Tooltip: o que cada um faz e que `janela` depende da faixa de energia visível.
2. `gap_method: str = "auto"` em `BandsParams`, `PdosParams` e `BandsDosParams`; este copia o campo pelo nome como já faz com `legend_gap`
   (`bands_dos/params.py:75,146`) e o repassa por `bands_view` / `dos_view`. SCF e relax não o têm.
3. **Padrão `auto` = o comportamento de hoje, bit a bit** (goldens e `test_legend_gap_*` sem regenerar). Valor guardado que não é um dos
   três cai no padrão (a validação por tipo de campo de `plot_file`).
4. O método muda **só** o gap da legenda e do rodapé. Nunca a referência (`vbm`, `midgap`), `dataset.vbm/cbm/edges` nem a figura.

### R2: Bandas

1. `gap_entries(dataset, params)` (assinatura nova; `gap_handles`, `legend_gap_notes` e `summary(dataset, params)` seguem a fonte única):
   - `auto`: o que `gap_entries(dataset)` faz hoje;
   - `homo_lumo`: `BandsDataset` ganha `lumo: float | None` (de `pw.lumo`, preenchido onde `fermi_kind` já é, `bands/data.py:155-157`); o
     gap é `lumo − fermi` quando `fermi_kind == "homo_lumo"` e passa de `EDGE_TOL`, **uma** entrada (`channel=None`: o pw.x imprime um
     par para os dois canais, como `pdos_gap`). Sem o par: nenhuma entrada e a nota `NO_HOMO_LUMO_NOTE` ("HOMO/LUMO não impresso pelo
     pw.x: só com ocupações fixas e nbnd maior que as bandas ocupadas");
   - `janela`: função pura `window_gap(energies, ref, emin, emax) -> tuple[float, float] | None` em `bands/gap.py`: as energias
     `E − ref` de **todas** as bandas e pontos k que caem em `(emin, emax)`, ordenadas; o maior espaçamento entre vizinhas, só se
     `≥ WINDOW_GAP_MIN_EV = 0,05` (a mesma largura mínima do script da PDOS); VBM e CBM são as vizinhas. `ref` e a janela são os do gráfico
     (`reference`, `emin`, `emax`).
2. Spin: `janela` roda por canal (`↑` e `↓`) e dá o global como `spin_band_edges` (`max` dos topos e `min` das bases, só se maior que
   `EDGE_TOL`); `homo_lumo` é a entrada única de cima.
3. `legend_gap_notes(dataset, params)` explica a ausência por método: `homo_lumo` → `NO_HOMO_LUMO_NOTE`; `janela` → "Sem gap para a legenda:
   nenhum intervalo vazio de pelo menos 0,05 eV na janela de energia". A nota `dataset.gap_note` (regras da spec 27-6) só vale em `auto`.
4. **Testes** (`tests/test_gap_method_bands.py`, novo): `auto` idêntico ao de `test_bands_gap_fermi.py` / `test_legend_gap_bands.py`;
   `janela` num isolante sintético (`ENERGIES` de `test_bands_gap_fermi.py`) dá `CBM − VBM`; num sistema de contagem ímpar com duas bandas
   coladas em E_F (energias sintéticas como as do exemplo: pares planos em E_F e um vazio de ~3,8 eV acima) dá o vazio grande e não 0,07;
   a mesma figura com `emin/emax` mais estreito que o vazio não tem gap e tem a nota; `homo_lumo` com `PwOutput(fermi_kind="homo_lumo",
   lumo=…)` e sem; spin com os dois canais e com um só; `reference` não muda o valor de `janela`; o rodapé e a legenda dizem o mesmo número.

### R3: PDOS

1. `pdos/gap.py` ganha `gap_for(dataset, params) -> GapInfo | None`:
   - `auto`: `dataset.gap` como hoje;
   - `homo_lumo`: `GapInfo(lumo − homo, "homo_lumo")` do par impresso (NSCF antes do SCF, como `pdos_gap`); sem par: `None` e a nota;
   - `janela`: `projwfc.dos_gap_window(energy, total, lo, hi)`: a maior sequência de pontos com a DOS total `≤ GAP_DOS_REL_TOL × pico` cujos
     dois pontos que a delimitam estão em `[lo, hi]` (a janela do gráfico, em energia absoluta: `ref + emin` e `ref + emax`) e
     de largura `≥ 0,05 eV`; medida como `dos_gap` mede (do último ponto acima do limiar ao primeiro acima). Fonte `"dos"` (`≈`).
2. É sempre o total do **sistema**, nunca a seleção de átomos (spec 21): `dataset.data.total`.
3. `pdos/render.py:95-98` e o rodapé (`pdos/render.py:266`) chamam `gap_for`; `PdosDataset.gap` continua sendo o `auto`, calculado no worker.
4. **Testes** (`tests/test_gap_method_pdos.py`, novo): `auto` igual a `test_legend_gap_pdos.py`; `janela` em curvas sintéticas (isolante de 1,2 eV
   com E_F no meio, E_F na borda, metal, vazio fora da janela, janela mais estreita que o vazio); `homo_lumo` com `si_bands/si.scf.out`
   (par impresso) e com `al_pdos_flat` (sem par: `None` + nota); a seleção de átomos não muda nada.

### R4: Bandas com DOS

1. O método vale para a entrada **das bandas** (a legenda e o rodapé são os das bandas, `bands_dos/render.py:56,84`): `janela` usa a janela e a
   referência únicas da figura combinada; `homo_lumo` usa o `pw` do SCF das bandas.
2. A DOS desta figura não desenha gap (hoje também não): `gap_for` não é chamado.
3. **Testes** (`test_bands_dos_render.py`): os três métodos, e que a janela compartilhada é a que o `janela` usa.

### R5: Grids e persistência

1. `gap_method` vai para o `<kind>.plot` pelo campo `choice` e é restaurado; uma célula de grid (`session.copy()`) o carrega sem código novo
   (teste em `tests/test_grid_render.py`: a célula de bandas com `janela`, sessões de `plot_grid_helpers.py`).
2. "Restaurar padrões" volta para `auto`.

## Fora de escopo
- Dizer se o gap é direto ou indireto, ou onde ficam o VBM e o CBM (como na spec 20).
- Usar o método para escolher a referência (`vbm`, `midgap`) ou desenhar a faixa do gap.
- Escolher o método sozinho (por exemplo, `janela` quando a contagem é ímpar): a escolha é do usuário.
- A tolerância **absoluta** do script (1,0 estados/eV): ela depende do tamanho do sistema (um slab de 97 átomos tem DOS de centenas
  de estados/eV); o app mantém a relativa da spec 20.
- Gap por canal de spin na PDOS (o pw.x imprime um par).

## Decisões assumidas (confirmar na revisão)
1. **Padrão `auto`** (o que existe): a pasta de exemplo continua mostrando 0,072 eV com a nota até o usuário escolher "Maior intervalo na
   janela". A alternativa é tornar `janela` o padrão quando a contagem de elétrons é ímpar; muda figuras que existem, então ficou fora.
2. O "segundo método" implementado é o **do código** do script (maior espaçamento entre vizinhas dentro da janela), não a contagem de
   bandas, que é o `auto`. Se o usuário queria a contagem como método separado, `auto` já a faz nos isolantes.
3. O método `janela` **depende da faixa de energia visível** (como o script): dar zoom no eixo muda o gap. Fica dito no tooltip.
4. Largura mínima de 0,05 eV, a do script da PDOS, para o método não "achar" gaps numéricos num metal denso.
5. O rodapé (`E_gap (no caminho) = …`) segue o método, para ele e a legenda dizerem o mesmo número (a regra "uma fonte" da spec 20).
6. Em `janela` com spin, a entrada `global` usa a mesma regra de `spin_band_edges` (só com gap nos dois canais).

## Notas de implementação
- Novos: `tests/test_gap_method_bands.py`, `tests/test_gap_method_pdos.py`.
- Alterados: `core/calculations/params.py` (218 linhas; o campo), `bands/params.py`, `pdos/params.py`, `bands_dos/params.py`, `bands/data.py`
  (`BandsDataset.lumo`), `bands/gap.py` (59 linhas; `window_gap`, `gap_entries(dataset, params)`, notas), `bands/render.py` e `bands/module.py`
  (`summary(dataset, params)`), `pdos/gap.py` e `pdos/render.py`, `core/qe/projwfc.py` (260; `dos_gap_window`), `bands_dos/render.py`.
- `PlotView` / `ParamsBody` não mudam: o campo é `choice` com `requires`.
- Limites: nenhum arquivo passa de ~330 linhas depois; `base.py` (454) não é tocado.
- Documentação ao implementar: `CLAUDE.md`, seção "Energy gap in the legend (spec 20)": o método e que ele só muda a legenda e o rodapé.

## Critérios de aceite e testes
- [ ] Padrão `auto`: `test_legend_gap_bands.py`, `test_legend_gap_pdos.py`, `test_bands_gap_fermi.py`, `test_figure_regression.py` e
      `test_bands_spin_render.py` passam sem regenerar goldens.
- [ ] Bandas, contagem ímpar com `janela`: gap do vazio grande (não 0,07) e rodapé e legenda com o mesmo valor.
- [ ] `janela` respeita `emin/emax` e `reference`; sem intervalo ≥ 0,05 eV: sem entrada e com a nota.
- [ ] `homo_lumo` sem par impresso: sem entrada e com `NO_HOMO_LUMO_NOTE` em bandas, PDOS e bandas + DOS.
- [ ] PDOS `janela` e `homo_lumo` nos casos sintéticos e com as fixtures citadas; a seleção de átomos não muda o gap.
- [ ] Uma célula de grid de bandas com `janela` desenha a mesma legenda que a figura aberta.
- [ ] **Conferência manual (usuário):** na pasta `Exemplo-bands-010-mehg-O1`, "Maior intervalo na janela" com a janela do script (−2 a 8 eV)
      mostra ≈ 3,76 eV.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
