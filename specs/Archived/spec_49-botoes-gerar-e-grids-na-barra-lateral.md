# Spec 49: "Gerar Gráfico" e "Grids" na barra lateral, sem o botão "Plot", e o caminho da barra superior com espaço fixo

| | |
|---|---|
| **Prioridade** | 49 (ajuste de interface, independente das demais; R2 só tem sentido depois de R1) |
| **Status** | Implementada |
| **Depende de** | spec 1 (o botão "Plot" que R2 remove), spec 16 (`Breadcrumb`), spec 23 (botão "Grids"), spec 33 (a barra superior só com o LED) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): move botões e remove um caminho de código; segue o padrão do `ActivityButton`, e `ui/main_window.py` só perde linhas. |

## Itens de origem (`Ideias.md`)

> Os botões "Gerar Gráfico" e "Grid" que ficam na barra superior, jundo dos botões das abas, não combinam com a UX do projeto, quero fazer as seguintes musanças:
>
> - Mover os botões "Gerar Gráfico" e "Grid" para barra lateral onde já exitem outros botões.
> - Na barra lateral já tem um botão "Plot" com a função parecida com "Gerar Gráfico", pode remover o botão 'Plot'.
> - Quero que espaço destinado ao endereço da pasta seja fixo, não quero que os itens do lado direito se desloquem toda vez que entrar ou sair de pasta (O endereço da pasta muda).

"Grid" é o botão "Grids" (`ui/widgets/bars.py:221`, spec 23); "barra lateral" é a `ActivityBar`, a coluna de botões à esquerda (Árvore, Grade,
Plot, Rsync, Criar, Tema); "botões das abas" são os três botões "Árvore / Grade / Gráficos" da barra superior. Decisão do usuário: o "Plot" sai.

## Situação atual

- **R1 (botões na barra superior).** `ui/widgets/bars.py:166-235`, `TopBar`: `generate` ("Gerar Gráfico", variante `primary`, objeto
  `generateButton`, `:215-219`), `grids` ("Grids", `gridsButton`, `:221-225`) e `plot_file` ("Plotar SCF", `:227-232`, oculto até haver uma
  saída plotável aberta) ficam depois do `addStretch(1)` (`:214`), à direita dos três botões de painel (`toggles`, `:200-213`). Os sinais
  são `TopBar.generate_requested` / `grids_requested` (`:167,169`); as ligações: `ui/main_window.py:236` (`top_bar.generate_requested` →
  `generate_plot`) e `ui/grids_controller.py:65` (`window.top_bar.grids_requested` → `controller.open`). O ícone de `generate` é `bolt`,
  o de `grids` é `grid_view` (`_refresh_icons`, `:265-268`). Nenhum QSS usa `#generateButton` nem `#gridsButton` (grep em
  `ui/resources/styles`). A `ActivityBar` (`:98-163`) tem `ActivityButton`s de 46 × 44 px (ícone sobre rótulo de 9 px): `tree` ("Árvore"),
  `grid` ("Grade", ícone `grid_view`), `plot`, `rsync`, `new_calc` ("Criar") e `theme_button`. Testes que clicam: `tests/test_grid_dialog.py:25` e
  `tests/test_grid_workflow.py:37` usam `window.top_bar.grids`; nenhum teste clica em `top_bar.generate` (os helpers chamam
  `generate_plot_for`).
- **R2 (botão "Plot").** `ActivityBar.plot` (`bars.py:117-119`, ícone `bolt`, "Mostrar/ocultar o gráfico (sem salvar)", checkable) emite
  `plot_requested` (`:101,134`), ligado em `ui/main_window.py:233` a `toggle_plot` (`:377-384`): com o gráfico à vista
  (`LayoutController.plot_shown`, `ui/layout_controller.py:95-101`) oculta o workspace e volta à árvore; senão chama
  `PlotWorkflow.preview(pasta)` (`ui/plot_workflow.py:168-177`: mostra workspace e ajustes e gera **sem salvar**, ou só traz à frente o
  gráfico aberto da pasta). `ActivityBar.set_left_mode` (`bars.py:148-150`) marca `tree` ou `plot` conforme o painel esquerdo. "Gerar
  Gráfico" faz o mesmo e **salva** em `plots/` (`generate_plot` → `PlotWorkflow.generate(pasta, auto_export=True)`). Quem usa o que sai:
  `preview` só tem `toggle_plot` e `tests/test_plot_workflow_unit.py:97`; `plot_shown` só `toggle_plot`. Testes do botão:
  `tests/test_plot_workflow.py:560-615` (`test_plot_button_previews_without_saving`, `…never_asks_to_overwrite`, `…reuses_the_open_plot`,
  `test_second_plot_click_hides_the_plot`) e `tests/test_main_window.py:232,235` (`activity.plot.isChecked()`). O docstring de
  `plot_workflow.py:182` cita o botão "Plot". Os painéis têm outro caminho para ocultar o gráfico: o botão "Gráficos" da barra superior.
- **R3 (caminho que desloca a barra).** `TopBar` põe, da esquerda: voltar, avançar, `breadcrumb`, `led`, o separador e os três `toggles`,
  depois o `addStretch(1)` (`bars.py:195-214`). O `Breadcrumb` tem política `Preferred` × `Fixed` (`ui/widgets/breadcrumb.py:39`) e `sizeHint` =
  largura de todos os níveis limitada a `MAX_WIDTH` = 560 (`:29,132-135`); `set_path` (`:72-85`) chama `updateGeometry()` e ativa o layout do
  pai. Com o stretch só depois dos toggles, o `led`, o separador e os três toggles ficam logo à direita do caminho e **andam com a
  largura dele** a cada pasta aberta (até 560 px). **Não medido em execução**: segue do layout acima; o teste de R3 mede.
- Tamanhos: `ui/main_window.py` 450 de 450 (`PER_FILE_LIMIT`), `ui/widgets/bars.py` 360, `ui/widgets/breadcrumb.py` 184,
  `ui/plot_workflow.py` 483, `ui/layout_controller.py` 201.

## Requisitos

### R1: "Gerar Gráfico" e "Grids" na barra lateral

1. `ActivityBar` ganha `generate` e `grids`, dois `ActivityButton`, e os sinais `generate_requested` e `grids_requested` (ligados ao
   `clicked`, como `rsync`/`new_calc`). Ordem de cima para baixo: **Árvore, Grade, Gerar, Grids, Rsync, Criar** (os dois novos ficam onde o
   "Plot" estava); `Tema` continua embaixo.
   - `generate`: ícone `bolt`, rótulo "Gerar", tooltip "Detectar o tipo de cálculo e plotar a pasta selecionada (Ctrl+G)" (o de hoje).
   - `grids`: rótulo "Grids", tooltip "Unir gráficos abertos numa grade N×M (uma só figura)" (o de hoje), ícone `dashboard` (o `grid_view`
     já é o da "Grade"; dois botões vizinhos com o mesmo ícone se confundem). `scripts/fetch_assets.py` ganha `dashboard` em `ICONS` e o
     SVG é versionado em `ui/resources/icons/`; se o nome não existir na fonte, usar `table_chart` (já versionado). Não verificado: o
     download não foi tentado nesta sessão.
2. `TopBar` perde `generate`, `grids`, `generate_requested`, `grids_requested` e as duas linhas de `_refresh_icons` que os pintam; `plot_file`
   fica (a barra continua com ele). `ui/main_window.py:236` passa a ligar `self.activity.generate_requested`, **na mesma linha**
   (o arquivo está em 450/450: nenhuma linha nova); `ui/grids_controller.py:65` liga `window.activity.grids_requested`.
3. Nada muda no que os botões fazem: "Gerar" é `generate_plot` (Ctrl+G, a ação `plot.generate`); "Grids" abre a janela da spec 23. O texto de
   `ui/widgets/workspace.py:106` ("use “Gerar Gráfico” em uma pasta…") continua verdadeiro: o tooltip e a ação ainda se chamam assim.
4. A ordem de Tab (spec 19) já agrupa a barra lateral como uma região: nenhum código novo; os dois botões entram na região da barra
   lateral.
5. **Testes:** `tests/test_main_window.py`: a ordem dos botões da `ActivityBar` (`tree, grid, generate, grids, rsync, new_calc`),
   `not hasattr(window.top_bar, "generate")` e `grids`; um clique em `activity.generate` com a pasta `03_bands` de `demo_project` selecionada
   emite `plot_ready` e grava em `plots/` (o que o clique no `top_bar.generate` fazia); `tests/test_grid_dialog.py:25` e
   `tests/test_grid_workflow.py:37` passam a clicar `window.activity.grids`. `tests/test_focus.py`: os dois botões estão na cadeia de Tab
   da região da barra lateral.

### R2: remover o botão "Plot"

1. Saem: `ActivityBar.plot`, `plot_requested`, a linha `self.plot.setChecked(mode == "params")` de `set_left_mode` (que fica só com
   `tree`), `MainWindow.toggle_plot` e a ligação de `:233`, `LayoutController.plot_shown` e `PlotWorkflow.preview` (sem outro chamador).
   Ocultar o gráfico fica com o botão "Gráficos" da barra superior e com "voltar" do painel de ajustes (`params.back_requested`).
2. O docstring de `PlotWorkflow.plot_file` (`plot_workflow.py:182`) deixa de citar o botão "Plot". `ui/main_window.py` fica ~9 linhas
   menor; o limite `PER_FILE_LIMIT` de 450 **não** muda nesta spec.
3. **Testes:** removidos `test_plot_button_previews_without_saving`, `test_plot_button_never_asks_to_overwrite`,
   `test_plot_button_reuses_the_open_plot`, `test_second_plot_click_hides_the_plot` (`test_plot_workflow.py`) e o teste de `preview` em
   `test_plot_workflow_unit.py:97`; as asserções de `activity.plot` em `test_main_window.py:232,235` viram só as de `activity.tree`.
   Novo: `test_activity_bar_has_no_plot_button` (`not hasattr(ActivityBar, "plot_requested")`, como o teste que já existe para "params").
   A cobertura de "gerar não pergunta sobrescrever / reaproveita o gráfico aberto" já está nos testes de `generate` (`test_plot_workflow.py`);
   conferir que sobra um teste que gera uma pasta já plotada com a aba aberta e não duplica a aba.

### R3: espaço fixo para o caminho

1. Na `TopBar`, o `breadcrumb` entra com `layout.addWidget(self.breadcrumb, 1)` (fator de esticamento 1) e a política `Expanding` × `Fixed`;
   o `addStretch(1)` de `:214` sai. O botão `plot_file` ("Plotar SCF") passa a ficar **entre o caminho e o LED**
   (`voltar, avançar, caminho, plot_file, led, separador, toggles`), para que o LED e os três toggles fiquem no canto direito, em posição
   fixa, também quando ele aparece ou some (um clique em outra aba).
2. O caminho ocupa o que sobra da largura, sempre o mesmo para uma janela; `Breadcrumb.relayout()` (que esconde níveis do meio atrás do "…")
   continua decidindo pela largura recebida. `MAX_WIDTH` (`breadcrumb.py:29`) sai: com a janela larga o caminho inteiro cabe. O `minimumSizeHint`
   (até 240 px) não muda. O `set_path` continua ativando o layout do pai antes de `relayout()`.
3. **Testes** (`tests/test_top_bar_layout.py`, novo; `main_window` com a janela em 1400 px): a largura do `breadcrumb` e o `x` do `led` e do
   toggle "Árvore" são **iguais** com a raiz selecionada, com uma pasta profunda (`demo_project/03_bands`) e com um nome longo
   (pasta criada em `tmp_path` dentro do projeto); o mesmo ao mostrar e esconder `plot_file` (`set_plot_file(True, "Plotar SCF", "")`);
   com uma janela estreita (700 px) o "…" aparece e o LED continua à direita. Falha sem a correção (hoje o `x` do LED varia com o caminho).

## Fora de escopo

- Mover o "Plotar SCF"/"Plotar relaxamento" (`plot_file`) para a barra lateral: não foi pedido; fica na barra superior (só muda de lugar, R3.1).
- Reaproveitar o "Plot" como "prévia sem salvar": o usuário o dispensou; o gráfico sem salvar continua no menu de contexto "Plotar".
- Remover os três botões "Árvore / Grade / Gráficos" da barra superior: continuam.
- Mudar `PER_FILE_LIMIT` de `ui/main_window.py`: a folga que R2 abre fica de reserva.

## Decisões assumidas (confirmar na revisão)

1. **Posição:** "Gerar" e "Grids" ocupam o lugar do "Plot" (entre "Grade" e "Rsync"), nessa ordem.
2. **Rótulos:** "Gerar" (cabe nos 46 px do botão; "Gerar Gráfico" não cabe) e "Grids"; os tooltips guardam os nomes completos e o atalho.
3. **Ícone do "Grids":** `dashboard`, novo, porque `grid_view` é o da "Grade". Alternativa sem download: `table_chart`.
4. **"Plotar SCF" à esquerda do LED:** um deslocamento pequeno de um botão que o usuário não citou, para que ele não empurre o LED. Se
   preferir o botão no canto direito como hoje, o LED anda quando ele aparece.
5. **Sem prévia:** o único jeito de plotar a pasta pela barra lateral passa a ser "Gerar", que também grava em `plots/` (como o botão que
   o usuário quer manter).

## Notas de implementação

- Novos: `tests/test_top_bar_layout.py`; `src/qe_studio/ui/resources/icons/dashboard.svg` (ou nada, com `table_chart`).
- Alterados: `ui/widgets/bars.py` (R1–R3), `ui/widgets/breadcrumb.py` (política, `MAX_WIDTH`), `ui/main_window.py` (liga `activity.generate_requested`,
  perde `toggle_plot`), `ui/grids_controller.py:65`, `ui/layout_controller.py` (`plot_shown`), `ui/plot_workflow.py` (`preview`, docstring),
  `scripts/fetch_assets.py`, `scripts/screenshot.py` (confere que `top_bar.breadcrumb.setFixedWidth(250)` ainda vale), os testes citados.
- Limites: `ui/main_window.py` 450/450 → ~441 (só perde linhas); nenhum outro arquivo perto de 500 (`plot_workflow.py` 483 → ~474).
- Documentação ao implementar: `CLAUDE.md` (a lista da barra lateral e o texto de `ui/main_window.py` não citam o "Plot" por nome, mas a seção
  "Main window and controllers" fala de `top_bar` e a de `PlotWorkflow` de "the 'Plotar …' button's source"; conferir com `grep -n "Plot\b"`),
  `README.md` se descrever os botões, os screenshots de `scripts/screenshot.py`.

## Critérios de aceite e testes

- [ ] A barra lateral mostra, de cima para baixo, Árvore, Grade, Gerar, Grids, Rsync, Criar e Tema; a barra superior não tem "Gerar Gráfico" nem
      "Grids" (`test_main_window.py`).
- [ ] Clicar "Gerar" com uma pasta de bandas selecionada plota e grava `plots/`; Ctrl+G faz o mesmo (`test_main_window.py` / `test_plot_workflow.py`).
- [ ] Clicar "Grids" abre a janela da spec 23 (`test_grid_dialog.py`, `test_grid_workflow.py` pelo novo botão).
- [ ] Não existe botão "Plot": `ActivityBar` sem `plot` nem `plot_requested`; nenhum teste o referencia.
- [ ] A posição do LED e dos três toggles, e a largura do caminho, não mudam ao trocar de pasta nem ao mostrar o "Plotar SCF"
      (`test_top_bar_layout.py`), e o "…" continua aparecendo numa janela estreita.
- [ ] A ordem de Tab inclui os dois botões na região da barra lateral (`test_focus.py`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
