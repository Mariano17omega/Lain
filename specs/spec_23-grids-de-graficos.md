# Spec 23: Grids de gráficos (grade N×M numa só figura)

| | |
|---|---|
| **Prioridade** | 23 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 15 (controladores, `for_window`), spec 22 (a figura combinada pode ser uma célula) |
| **Usada por** | nenhuma |
| **Esforço** | G |

## Itens de origem (`Ideias.md`)

> - gride de graficos: Add um um botão na barra superior chamado "Grids" que abre uma janela para selecionar e configurar o gride de graficos;
>   Nessa janela, o usuario cria uma grade NxM para unir os graficos. Cada quadrante da grade pode exibir um grafico.
>   Para cada quadrante, o usuario escolhe um grafico que já foi plotado, define o posição (linha, coluna) e define um título.

Para não confundir com a "grade" de arquivos do painel (modo grade/lista), o recurso se chama **Grid** na
interface, como pediu o texto.

## Situação atual

- **Render:** `module.render(figure, dataset, params, style)` é dono da figura inteira. Os ajudantes de
  `core/plotting/draw.py` fazem `figure.clear()` + `add_subplot`/`subplots` e fecham com `figure.suptitle`,
  `add_legend` e `figure.tight_layout(pad=0.6)` (`new_axes` :15, `stacked_axes` :23, `side_axes` :33, `finish`
  :58, `finish_side` :66). SCF chama também `figure.clear()` e `figure.text` direto (`scf.py:215-234`).
- Verificado com matplotlib 3.11: `Figure.subfigures()`/`add_subfigure(gs[r, c])` aceitam `subplots`,
  `add_subplot`, `suptitle`, `text`, `legend`, `set_facecolor`; `SubFigure.clear()` limpa só os eixos da célula.
  **Falta `tight_layout`** em `SubFigure`: `draw.py:63` e `:74` levantariam `AttributeError`. `savefig`,
  `set_size_inches` e o fundo só existem na `Figure` raiz.
- **Sessões:** `PlotSession` (`core/plotting/session.py:34`: `result`, `dataset`, `params`, `defaults`, `info`;
  `key`, `style`, `title`, `folder`). Chave `plot:<kind>:<target>` (:108). `.plot` por `<pasta>/<kind>.plot`.
  Uma sessão sintética precisa de `DetectionResult` fabricado (`core/detection.manual_result`).
- **Quais gráficos "já foram plotados":** `Workspace.items()` (`ui/widgets/workspace.py:131`) devolve
  `(chave, widget)`; filtrar `PlotView` e ler `w.session` (já feito em `PlotWorkflow.plot_of`,
  `plot_workflow.py:124`). Nada mais guarda sessões. As abas não são restauradas ao reabrir o app
  (`layout_controller.py:187-188`).
- **Interação:** `PlotView._install_readout` numera `enumerate(self.figure.axes)` da raiz (`plot_view.py:258`)
  e passa esse índice a `session.format_coordinates`; os módulos interpretam o índice como "painel N deste
  gráfico". `_axis_limits` e `_on_release` (:273-279) devolvem os limites de **todos** os eixos da raiz e
  `apply_limits` lê só `axes_limits[0]`. `ScaledFigureCanvas` mantém polegadas fixas e um `rc` único.
- **Exportação:** `plan_export`/`render_figure`/`export_figure` (`core/plotting/export.py:56,71,95`) são
  genéricos em `(module, dataset, params)`; `plan_export` usa `session.folder`. `PlotExporter.export` copia os
  parâmetros e roda em worker (`ui/plot_export.py`).
- **UI:** `TopBar` (`ui/widgets/bars.py:147-230`): o botão "Plotar" é um `QPushButton` primary
  (l.198-202), o painel de ações é `ui/actions.py:ACTIONS`. Controladores `for_window` (`help_controller.py:46`,
  `palette_controller.py:59`, `first_run.py:57`); `main_window.py` tem 475/500 linhas.
- **Persistência com caminhos relativos:** `FolderMemory` (`core/folder_memory.py`) e `NavigationStore`
  guardam caminhos relativos a `paths.local_root`; `appdirs.set_aside_corrupt` trata arquivo corrompido.

## Requisitos

### R0: `draw.py` à prova de `SubFigure`
1. `finish` e `finish_side` só chamam `figure.tight_layout` quando `figure` é uma `Figure` raiz; numa
   `SubFigure` o layout é da raiz, que o Grid cria com `layout="constrained"`.
2. `scf.py` e `relax.py` não usam nada fora do conjunto comum a `Figure` e `SubFigure`.
3. Nenhuma figura isolada muda: `test_figure_regression.py` passa sem regenerar goldens.

### R1: Definição da grade (core, sem Qt)
1. `core/plotting/grid.py`:
   - `GridCell(row, col, ref: PlotRef, title: str)` com `PlotRef(folder, kind, partner=None)`: pasta (e a
     segunda pasta da figura de bandas + DOS da spec 22), `kind` do módulo e título (vazio = o título do
     próprio gráfico);
   - `GridSpec(name, rows, cols, cells)` com `validate() -> list[str]`: `rows`, `cols` ≥ 1 (limite 6 × 6),
     `row`/`col` dentro da grade, **uma posição por célula**, ao menos uma célula, nome não vazio sem `/`;
   - células ocupam uma posição (sem mesclar linhas ou colunas).
2. `GridStore` (`grids.json` em `appdirs.data_dir()`, versão 1): `names()`, `get(name)`, `save(spec)`,
   `delete(name)`. Caminhos de pasta **relativos a `paths.local_root`** (`abs:<caminho>` fora dele), como
   `FolderMemory`; `MainWindow` chama `set_root` na partida e no `reload_config`. Carga preguiçosa e sob lock,
   escrita atômica, arquivo ilegível posto de lado (`set_aside_corrupt`), caminho injetável nos testes.
3. Renomear uma pasta (`MainWindow.rename_path`) atualiza as referências do `GridStore` (como
   `FolderMemory.rename`).

### R2: Módulo `grid`
1. `core/calculations/grid/` (`module`, `params`, `render`): `kind = "grid"`, sem papel `anchor`,
   `selectable = False` (spec 22). Dataset: `GridDataset(spec, cells: list[GridCellData])`, cada
   `GridCellData` com a `PlotSession` da célula (ou `error: str` quando não carregou).
2. `render`: `fig_grid = figure.subfigures(rows, cols)`; para cada célula `session.render(subfig)` (que aplica o
   `PlotStyle` e o `MPL_LOCK` da própria sessão); depois o título da célula (`subfig.suptitle`), quando
   definido, **substitui** o da sessão. Posição sem célula fica vazia (fundo, sem eixos). Célula com `error`
   mostra o texto "Plot indisponível: <motivo>" centralizado.
3. `GridParams(CommonParams)`: `cell_width`, `cell_height` (polegadas; `figure_size = (cols × cell_width,
   rows × cell_height)`, calculado, não editado à mão), `background` (cor), `font_size`, `show_titles`.
   Cada célula mantém os **parâmetros do seu próprio gráfico** (os da aba aberta ou, sem aba, os do `.plot`);
   o Grid não os edita (ver "Fora de escopo").
4. `apply_limits` e `format_coordinates` roteados por célula: `PlotView` (ou um `GridView` derivado) calcula,
   para cada eixo, a qual `SubFigure` pertence e entrega ao módulo da célula o índice **local** e só os limites
   dessa célula. Mexer o zoom numa célula altera os parâmetros dessa sessão, e o Grid é regenerado.
5. Exportação: o `GridModule` entra no mesmo `export_figure`; `session.folder` do Grid é `paths.local_root` e
   o arquivo é `<local_root>/plots/grid_<nome>.<ext>`, com as regras de `plan_export` (nunca sobrescreve sem
   perguntar).

### R3: Botão e janela "Grids"
1. `TopBar`: botão "Grids" (`QPushButton`, ícone `grid_view` já vendorizado) ao lado de "Plotar", sinal
   `grids_requested`. Ação `grids.open` ("Gráficos ▸ Grids…", paleta e atalhos entram sozinhos).
2. `ui/grids_controller.py:GridsController.for_window(window)` abre `ui/dialogs/grid_dialog.py:GridDialog`
   (não modal, um por vez, `delete-on-close`, como o de atalhos). `MainWindow` ganha só o registro do controlador
   e o `connect` do botão (≤ 3 linhas).
3. Janela:
   - topo: **Nome**, **Linhas** e **Colunas** (spinboxes N × M), "Abrir…" (menu com os nomes do `GridStore`) e
     "Salvar";
   - tabela de células (uma por linha): **Gráfico** (combo com as **abas de plot abertas**: título e pasta;
     entrada vem de `Workspace.items()` filtrado por `PlotView`, via callback do controlador), **Linha**, **Coluna**
     (spinboxes limitados a N e M) e **Título**; botões "Adicionar célula" e "Remover";
   - validação ao vivo com `GridSpec.validate()` (mensagem sob a tabela; "Gerar" desabilitado enquanto houver erro);
   - "Pré-visualizar" mostra uma miniatura da grade (retângulos com o título) sem renderizar os gráficos;
   - "Gerar" abre (ou atualiza) a aba `grid:<nome>` do workspace e fecha a janela.
4. Gerar monta as sessões: célula com aba aberta usa a sessão da aba **no estado atual** (inclusive edições não
   salvas, cópia dos parâmetros); célula sem aba (grade reaberta depois) carrega pasta + `.plot` em workers
   (`PlotWorkflow.load_plot`), com o spinner de ocupado do rodapé.
5. Uma aba de Grid tem a barra de ferramentas e o export do `PlotView`, e seu painel de ajustes mostra só os
   campos do `GridParams`. Fechar a aba não grava `.plot` de Grid (a definição vive no `GridStore`).

### R4: Reabrir e manter
1. "Abrir…" carrega a definição; células cujas pastas sumiram ficam marcadas na tabela ("pasta não encontrada")
   e são geradas como "Plot indisponível".
2. Apagar uma grade salva: botão "Excluir" com confirmação no próprio diálogo.
3. As grades salvas valem para o projeto atual (`local_root`); trocar o projeto mostra as de `abs:` e as
   relativas resolvidas no novo root (as que não resolvem ficam indisponíveis, nunca apagadas).

## Fora de escopo
- Editar parâmetros de cada gráfico dentro do Grid (use a aba do gráfico; o Grid pega o estado atual).
- Mesclar células (linha ou coluna múltipla), larguras desiguais, letras "(a)(b)" automáticas, anotações.
- Grid dentro de Grid; gráficos de pastas fora do projeto atual além do que `abs:` já cobre.
- Salvar o Grid dentro de uma pasta de simulação (as pastas são sincronizadas).

## Decisões assumidas (confirmar na revisão)
1. "Já foi plotado" = tem **aba de plot aberta**. A grade salva guarda `(pasta, tipo)`, então reabre mesmo com
   as abas fechadas (recarrega do `.plot`).
2. As células são redesenhadas vetorialmente em `SubFigure`, não coladas como imagem: o export fica nítido
   (PDF/SVG) e o zoom funciona por célula.
3. Grades salvas por nome em `grids.json` (diretório de dados), relativas ao `local_root`.
4. Exporta em `<local_root>/plots/` porque um Grid não pertence a uma pasta de simulação.
5. Cada célula usa os parâmetros do **seu** gráfico; o Grid só controla layout, fundo e fonte. Fonte e estilo
   do Grid valem para os títulos; o texto interno de cada gráfico segue o `font_size` do seu parâmetro.
6. Limite de 6 × 6 células, para o tamanho da figura e a memória ficarem razoáveis.

## Notas de implementação
- Novos: `core/plotting/grid.py`, `core/calculations/grid/{module,params,render}.py`, `ui/grids_controller.py`,
  `ui/dialogs/grid_dialog.py` (se passar de ~300 linhas, dividir em `grid_cells.py` para a tabela).
- Alterados: `core/plotting/draw.py` (R0), `core/calculations/{scf,relax}.py` (só se algum uso escapar de R0),
  `core/calculations/__init__.py:REGISTRY`, `ui/widgets/bars.py` (botão), `ui/actions.py` (`grids.open`),
  `ui/widgets/plot_view.py` (eixos por célula; preferir uma subclasse `GridView` em arquivo novo a crescer o
  `PlotView`), `ui/widgets/workspace.py` (`open_grid`), `ui/plot_workflow.py` (carregar células),
  `ui/main_window.py` (≤ 3 linhas; `rename_path` avisa o `GridStore`), `scripts/screenshot.py` (opcional).
- `PlotView.render`/`ScaledFigureCanvas.draw` seguem a regra de só tentar o `MPL_LOCK` e repetir em 50 ms
  (spec 15); o Grid renderiza **na GUI** só depois que todas as sessões das células carregaram.
- `rc` único do canvas: o `font_size` do Grid vale para o canvas; células com outros tamanhos de fonte mantêm o
  seu `rc` em tempo de criação (limite conhecido do matplotlib com `mathtext` em tempo de desenho).

## Critérios de aceite e testes
- [ ] R0: `finish` numa `SubFigure` não levanta; todos os testes de figura (`test_figure_regression`,
      `test_bands_spin_render`, `test_pdos_spin`, `test_relax`, `test_scf`) passam sem regenerar goldens.
- [ ] `GridSpec.validate`: posição fora da grade, posição repetida, 0 células, nome vazio, 7×1 → erros
      específicos; grade válida → lista vazia. Propriedades (Hypothesis) de ida e volta no `GridStore`.
- [ ] `GridStore`: ida e volta com caminhos relativos; `abs:` fora do root; projeto movido continua
      resolvendo; arquivo corrompido posto de lado e nunca sobrescrito; renomear pasta atualiza referências.
- [ ] Render em `SubFigure` de bandas, PDOS, relax, SCF e bandas+DOS: número de eixos por célula igual ao do
      gráfico isolado; títulos das células; posição vazia sem eixos; célula com erro mostra o texto.
- [ ] Limites por célula: soltar o zoom na célula (0,1) altera só os parâmetros da sessão dessa célula;
      `format_coordinates` recebe índice local.
- [ ] Janela (pytest-qt): combo lista só abas de plot abertas; spinboxes respeitam N×M; "Gerar" desabilitado
      com erro; "Salvar" e "Abrir" fazem a ida e volta; "Excluir" pede confirmação.
- [ ] Fluxo: dois plots abertos → Grid 1×2 → "Gerar" abre a aba `grid:<nome>`; fechar os dois plots e reabrir o
      Grid salvo recarrega pelo `.plot`; célula de pasta apagada → "Plot indisponível".
- [ ] Exportação: `<local_root>/plots/grid_<nome>.png` sem sobrescrever sem perguntar.
- [ ] Botão "Grids" na `TopBar`; ação `grids.open` na paleta; `test_main_window.py` ajustado se a forma da barra
      mudar.
- [ ] `test_architecture.py`: arquivos novos < 500 linhas; `core/plotting/grid.py` sem Qt; `ui/` sem `kind ==`.
