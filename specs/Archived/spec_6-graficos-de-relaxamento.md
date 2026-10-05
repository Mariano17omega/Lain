# Spec 6: Gráficos de relaxamento (relax / vc-relax)

| | |
|---|---|
| **Prioridade** | 6 (feature maior; aproveita as specs 2 e 3) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 2 (fundo/estilo da figura), spec 3 (`relax.plot`) |
| **Usada por** | nenhuma |
| **Esforço** | G |

## Item de origem (`Ideias.md`)

> - No caso de simulações de relaxamento, 'relax' e 'vc-relax', quero que faça o plot do progresso de relaxamento. Em 'Documentation/Relax-Viewer-' tem um pequeno app que ler outputs do relaxamento e gerar o plot, em escala linear e escala log, do |ΔE| vs passos BFGS, e Força total vs Passos BFGS. Esse o 'Relax-Viewer-' como referencia para implementar esses dois plots. O Lain deve ser capaz de identificar se é um relaxamento e gerar os dois plots quando clicar no botão plot, iqual como é bom bandas e PDOS.

Decisão confirmada: **uma figura com dois painéis** (|ΔE| em cima, Força embaixo, eixo X
compartilhado), com parâmetros para escolher os painéis e a escala.

Nota: com a spec 1, o botão "Plot" só abre o workspace e os ajustes. Quem gera o gráfico é "Gerar
Gráfico" / Ctrl+G, como para bandas e PDOS. "Quando clicar no botão plot" é lido aqui como "pelo
fluxo normal de gerar gráfico".

## Situação atual

- A detecção já existe: `RelaxModule` (`src/qe_studio/core/calculations/info.py:11`, badge `RELAX`,
  "Otimização estrutural") reconhece por conteúdo as saídas pw.x com `calculation` relax/vc-relax
  (`pw_output._calculation`, `src/qe_studio/core/qe/pw_output.py:77-80`). Mas ela é **só informativa**
  (`plottable = False`).
- Ao gerar gráfico numa pasta de relax, `MainWindow._map_manually` (`src/qe_studio/ui/main_window.py:414`)
  abre o mapeamento manual com a mensagem "…identificada como RELAX, que ainda não tem gráfico no MVP"
  (coberto por `test_relax_folder_asks_and_can_cancel`, `tests/test_plot_workflow.py:179`).
- Referência (app separado, PySide6, cores fixas de tema escuro):
  - `Documentation/Relax-Viewer-/relax_viewer/parser.py`: regex por linha. `!    total energy` abre um
    passo pendente; `Total force` e `number of bfgs steps` completam o passo; lê `number of scf
    cycles`, os limiares (`energy convergence thresh.`, `force convergence thresh.`, linha
    `criteria: energy < … Ry, force < … Ry/Bohr`), `bfgs converged`, e para em
    `Final scf calculation`;
  - `models.py`: `RelaxationStep`, `RelaxationResult.energy_deltas` (|E_i − E_{i−1}|);
  - `diagnostics.py`: "Relaxado" se `bfgs converged`, ou se o último |ΔE| ≤ etot_conv_thr e a última
    força ≤ forc_conv_thr;
  - `plotting.py`: |ΔE| em barras, força em linha com marcadores, linha tracejada do limiar,
    `_positive_for_log` (troca valores ≤ 0 por min/10 na escala log), ticks inteiros rareados acima de
    20 passos.
- Fixture real: `tests/fixtures/si_relax/si.rel.out` (relax de Si, QE 7.3.1). Tem os limiares no
  cabeçalho (linhas 52-53: 1.0E-04 Ry e 1.0E-06 Ry/Bohr), 6 passos com `number of bfgs steps` (0 a 5),
  um 7º SCF seguido de `bfgs converged in 7 scf cycles and 6 bfgs steps` (linha 2786), sem
  `Final scf calculation`, e último ΔE = 0 (energias iguais). O `demo_project` copia essa pasta para
  `01_relax`.
- Detalhe da referência a corrigir: o 7º SCF (após a convergência) não tem linha
  `number of bfgs steps`, e a referência o descarta como "passo incompleto".

## Requisitos

### R1: Parser `src/qe_studio/core/qe/relax.py`
1. Portar do Relax-Viewer **apenas** a parte de passos e limiares. A leitura de estrutura/células fica
   fora (3D fora de escopo). Mesmo estilo de `pw_output.py`: regex, sem ASE (o reader do ASE falha em
   saídas do QE ≥ 7, ver docstring de `pw_output.py`).
2. Leitura linha a linha (streaming), sem carregar o arquivo inteiro, porque vc-relax pode ter centenas
   de MB. O parser roda no worker (`load` → `_LoadTask`).
3. Passo completo = `!    total energy` + `Total force` + identificação do passo, que pode ser:
   - `number of bfgs steps = k`, ou
   - `bfgs converged in N scf cycles and M bfgs steps`, que fecha o passo pendente como passo `M`.
     Isso corrige a referência (ver "Situação atual").
4. Parar em `Final scf calculation` (vc-relax). O SCF final numa nova base de ondas planas não é passo
   BFGS. A energia dele pode aparecer no resumo como "E final (SCF final)".
5. Limiares, em ordem de precedência: cabeçalho (`energy convergence thresh.` / `force convergence
   thresh.`) → linha `criteria:` → input do relax (`etot_conv_thr` / `forc_conv_thr` do `&CONTROL`,
   papel `relax_in`) → padrões do QE (1.0e-4 Ry, 1.0e-3 Ry/Bohr), marcados como "(padrão do QE)".
6. Saídas incompletas (job rodando ou interrompido): devolve os passos completos, conta os incompletos
   e registra aviso. `job_done` vem de `JOB DONE`.
7. Dataclasses: `RelaxStep(index, bfgs_step, energy_ry, force_ry_bohr, scf_cycles)` e
   `RelaxData(calculation, steps, energy_threshold, force_threshold, threshold_source, converged,
   job_done, truncated_steps, final_scf_energy)`, com a propriedade `energy_deltas`.

### R2: Módulo plotável
1. `RelaxModule` sai de `info.py` e vai para `src/qe_studio/core/calculations/relax.py`, que o
   registra em `REGISTRY` (`core/calculations/__init__.py`) na mesma posição. Mantém `kind = "relax"`,
   badge `RELAX` e "Otimização estrutural", e passa a ter `plottable = True`.
2. Papéis: `relax_out` obrigatório e âncora; `relax_in` opcional (só limiares) e âncora (mantém a
   detecção atual). Os globs PRD continuam (`relax*.in`, `vc-relax*.out`…).
3. `load(result) -> RelaxDataset(folder, data: RelaxData, formula, warnings)`. Se não houver nenhum
   passo completo, gera `LoadError("Nenhum passo de relaxamento completo em <arquivo>.")`.
4. Mensagem do `_map_manually` ajustada: RELAX deixa de ser citado como "sem gráfico", e o texto passa
   a valer só para SCF/CALC.

### R3: Figura
1. Uma figura com até dois painéis empilhados e eixo X compartilhado (`sharex`):
   - **topo: |ΔE| (Ry)**, uma barra por passo `i ≥ 1` com |E_i − E_{i−1}|;
   - **base: Força total (Ry/Bohr)**, linha com marcadores, um ponto por passo `i ≥ 0`.
2. Eixo X: "Passo BFGS", com o índice sequencial do passo completo (0, 1, 2…). Quando o QE não repete
   a contagem, ele coincide com `number of bfgs steps`. Ticks inteiros, rareados acima de 20 passos
   (como na referência).
3. Linhas horizontais tracejadas nos limiares (`etot_conv_thr` no topo, `forc_conv_thr` na base),
   com legenda `etot_conv_thr = 1.0e-04 Ry` e `forc_conv_thr = 1.0e-06 Ry/Bohr`.
4. Escala Y log (padrão) ou linear. Na log, valores ≤ 0 são trocados por um piso (mínimo positivo / 10,
   como `_positive_for_log`), o que é necessário na fixture, onde o último ΔE = 0.
5. Estados vazios, com texto centralizado no painel: "São necessários pelo menos dois passos completos
   para calcular |ΔE|." e "Nenhum passo completo de relaxamento encontrado."
6. Cores e fundo vêm dos parâmetros e do estilo da figura (spec 2), e não das cores fixas escuras da
   referência. Usar `core/plotting/draw.py:new_axes`/`finish` adaptados para mais de um eixo.

### R4: Parâmetros (`RelaxParams(CommonParams)`) e painel de ajustes
| Campo | Rótulo | Seção | Tipo | Padrão |
|---|---|---|---|---|
| `panels` | Painéis | Relaxamento | choice: `both` "Ambos", `energy` "\|ΔE\|", `force` "Força" | `both` |
| `scale` | Escala Y | Relaxamento | choice: `log` "Log", `linear` "Linear" | `log` |
| `show_thresholds` | Limiares | Relaxamento | bool | `True` |
| `energy_color` | Cor \|ΔE\| | Estilo | color | `#38bdf8` |
| `force_color` | Cor força | Estilo | color | `#10b981` |
| `threshold_color` | Cor limiares | Estilo | color | `#f43f5e` |
| `xmin`, `xmax` | Passo mín./máx. | Eixo X | float opcional (auto) | `None` |

- Nova seção "Relaxamento" em `SECTIONS` (`src/qe_studio/core/calculations/params.py:10`), antes de
  "Estilo".
- `show_legend` começa `True` para mostrar os limiares.
- Tamanho padrão: `plot.figure_size` do config. Com `panels = both`, a altura padrão é multiplicada
  por 1,5.
- Pan/zoom: `PlotSession.apply_limits` e `reset_view` (`src/qe_studio/ui/plot_session.py:54-69`)
  ganham um ramo `relax`, que grava só `xmin/xmax`. O Y fica automático.

### R5: Resumo (rodapé e topo do painel de ajustes)
`RenderInfo.summary` no formato:
`Relaxado ✓ · 6 passos BFGS · |ΔE| final 0.0e+00 Ry · F final 0.0e+00 Ry/Bohr`, ou
`Não relaxado · …` / `Em andamento · …` (sem `JOB DONE`). O critério é o de `diagnostics.is_relaxed`.
Os avisos do dataset (passos incompletos ignorados, limiares padrão do QE, job incompleto) aparecem no
topo do painel, como já acontece com bandas/PDOS.

### R6: Exportação
1. Novo hook `CalculationModule.export_stem(params) -> str`, com padrão `self.kind`. `MainWindow.export_plot`
   (`main_window.py:542`) passa a usá-lo no lugar de `session.kind`.
2. Relax: `relax` (ambos os painéis), `relax_energia` (só |ΔE|), `relax_forca` (só força). O controle
   de sobrescrita/versões (`next_free_stem`) continua igual.

### R7: Persistência e fundo
`relax.plot` (spec 3) e `background` (spec 2) funcionam sem código específico, porque `RelaxParams`
herda `CommonParams`.

## Fora de escopo
- Visualização 3D da estrutura e legenda CPK do Relax-Viewer.
- Evolução de volume, parâmetros de rede ou entalpia no vc-relax.
- Energia em eV (fica em Ry, como na referência).
- Monitorar o arquivo e atualizar o gráfico sozinho enquanto o job roda (basta sincronizar e gerar de
  novo).

## Decisões assumidas (confirmar na revisão)
1. No vc-relax, o |ΔE| usa a `!    total energy` (paridade com a referência), embora o critério do
   BFGS no vc-relax seja sobre a entalpia. Plotar entalpia fica como melhoria futura.
2. Uma única "Escala Y" para os dois painéis.
3. O eixo X usa o índice sequencial (R3.2) em vez do número BFGS do QE, para não sobrepor pontos quando
   o QE repete a contagem (reset do histórico BFGS).
4. As cores padrão vêm da referência (azul claro/verde/vermelho). Não vão para o `config.yaml`
   (podem ir depois, se desejado).

## Pendência
- **Fixture vc-relax real:** o CLAUDE.md exige fixtures reais e reduzidas do QE. É preciso que o
  usuário forneça uma saída vc-relax (com `Final scf calculation`) para `tests/fixtures/si_vc_relax/`
  (ou similar), reduzida como as demais e documentada em `tests/fixtures/README.md`. Sem ela, o
  comportamento do R1.4 fica testado só com texto sintético mínimo no teste do parser.

## Notas de implementação
- Novos arquivos: `src/qe_studio/core/qe/relax.py`, `src/qe_studio/core/calculations/relax.py`,
  `tests/test_relax.py`.
- Alterados: `core/calculations/info.py` (remove `RelaxModule`), `core/calculations/__init__.py`,
  `core/calculations/params.py` (`SECTIONS`), `core/calculations/base.py` (`export_stem`),
  `ui/plot_session.py`, `ui/main_window.py` (`export_plot`, `_map_manually`).
- `PlotView._on_release` usa `figure.axes[0]`. Com `sharex`, o X é igual em todos os eixos, então
  funciona.
- Performance (NFR §7, < 500 ms): o parser em streaming de uma saída de 100 passos deve ficar bem
  abaixo disso. Adicionar um caso `@pytest.mark.perf` com saída sintética grande.

## Critérios de aceite e testes
- [ ] Parser em `si.rel.out`: 7 passos completos (0..6), limiares 1e-4 / 1e-6 com origem "cabeçalho",
      `converged` verdadeiro, `job_done` verdadeiro, 0 passos truncados, último |ΔE| = 0.
- [ ] Saída truncada no meio de um passo (cópia via `copy_fixture` + corte): passos parciais,
      `converged` falso, `truncated_steps` = 1, sem exceção.
- [ ] Sem limiares no output e sem input → padrões do QE e aviso correspondente.
- [ ] Texto sintético com `Final scf calculation`: o SCF final fica fora dos passos.
- [ ] Detecção: `demo_project/01_relax` → `RelaxModule` completo e plotável.
- [ ] `test_plot_workflow`: gerar gráfico em `01_relax` abre uma aba "Otimização estrutural · 01_relax",
      sem diálogo de mapeamento, e exporta `plots/relax.png|svg|pdf`. Substitui
      `test_relax_folder_asks_and_can_cancel`.
- [ ] Render: `panels=both` → 2 eixos; `energy`/`force` → 1 eixo; `scale=log` com ΔE = 0 não gera
      aviso nem erro do matplotlib; `show_thresholds=False` remove as linhas.
- [ ] `export_stem`: `relax`, `relax_energia`, `relax_forca`.
- [ ] Zoom horizontal grava `xmin/xmax`, e Reset volta a `None`.
