# Spec 46: Janela 3D: barra só com x, y, z, eixos e rótulos ajustáveis, seção "Rotação", "Apagar" nas medidas e botões "Print" e "Restaurar padrões"

| | |
|---|---|
| **Prioridade** | 46 (abre a nona rodada). Ajustes pequenos sobre o que as specs 43 e 44 entregaram; a spec 47 grava os campos novos. Independente das specs 33–42 e 45. |
| **Status** | Implementada (14/10/2026). Desvios:<br>- `core/structure3d/options.py` ganhou `background_of_theme(nome)` (a regra `light` → `claro`, que `window.py` tinha em linha, agora dividida com o botão "Restaurar padrões").<br>- `Windows.open(path, structure=None, **options)` (helper dos testes) passa `root=` à janela.<br>- Os testes de "Apagar" são funções novas em `test_structure3d_measure_ui.py` (a sequência d1, d2, a1, a linha selecionada, o átomo pendente, "Copiar" depois de "Apagar" e a mistura com Delete), em vez de estender `test_copy_clear_and_delete`; os de "Restaurar padrões" cobrem também o tema trocado com a janela aberta (o fundo é o do tema de agora).<br>- O "Print" mostra "Imagem salva em plots/<nome>" com o mesmo `MESSAGE_MS` (3 s) das outras mensagens da barra de status. |
| **Depende de** | spec 43 (`StructureWindow`, `StructurePanel`, `DisplayOptions`, `Camera`, `StructureCanvas.render_image`), spec 44 (`MeasuresSection`), spec 24 (`core/unique_names.py`), spec 32 (`core/plotting/names.py`: nomes dos arquivos exportados), spec 15 (`run_task`) |
| **Usada por** | spec 47 (grava os campos novos de `DisplayOptions` e a câmera) |
| **Esforço** | M (R1, R4 e R6: P; R2, R3 e R5: M) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que as specs 43 e 44 abriram (campos do painel, `DisplayOptions`, seção de medidas); nenhum arquivo chega a 450 linhas e `ui/main_window.py` não muda. |

## Itens de origem (`Ideias.md`, 14/10/2026)

> - Na barra acima a estrutura 3D, é reduntante mostrar tanto as opções de vista para os eixos (x, y, z) quanto as vistas para (a, b, c). Quero que só mostre as opções de eixos (x, y, z) na barra de cima.
> - Na aba esquerda, na seção 'EXIBIÇÃO' tem a opção de mostrar e ocultar os eixos. Ele oculta e mostrar os dois sistemas de eixos. Quero que divida esse botão em dois. Um para ocultar e exibir os eixos (x, y, z) e outro para ocultar e exibir os eixos (a, b, c).
> - Na aba esquerda, na seção 'EXIBIÇÃO', adicione a opção de ajustar a espessura dos eixos (x, y, z), e dos eixos (a, b, c) separadamente.
> - Na aba esquerda, na seção 'EXIBIÇÃO', adicione a opção de ajustar o tamanho dos rotulos.
> - Os botões de checkbox de 'ligações' está separado dos outros, para melhorar a organização, deixe todos juntos, um depois do outro.
> - Na aba esquerda, adicione uma nova seção chamada 'ROTAÇÃO'. Nessa seção adicione botões de atalho para girar a estrutura em 45 graus nos eixos. Um para cada direção (x+, x-, y+, y-, z+, z-).
> - Adicione um botão 'PRINT' para salvar a imagem 3D para arquivo PNG.
> - Na aba esqueda, na sesção de "MEDIDAS", o botão "Limpar" apaga todas as medidas feitas. Quero que adicione o botão "Apagar" ao lado do botão "Limpar", com a função de apagar a ultima medida.

Acrescentado na revisão da primeira versão desta spec (14/10/2026):

> - Quero que inclua o botão "Restaurar padrões"

Os dois itens sobre gravar a vista em `view3d.plot` (uma seção por arquivo) estão na spec 47, que também diz o que "Restaurar padrões" faz com o arquivo.

Interpretação:

- **"Restaurar padrões"** = o botão de mesmo nome do painel de ajustes dos gráficos, na janela 3D: volta as **opções** e a **câmera** da janela ao padrão. As medidas e o átomo atual não são ajustes e ficam.
- **"barra acima a estrutura 3D"** = a barra `#plotToolbar` da `StructureWindow` ("Resetar vista" e o menu "Vista ▾"); o menu lista hoje seis vistas.
- **"rotulos"** = o texto que a vista desenha: os rótulos dos átomos (o campo "Rótulos") e os nomes dos eixos (a, b, c e x, y, z).
- **"girar a estrutura em 45 graus nos eixos"** = em torno dos eixos cartesianos x, y, z da estrutura (os do triedro do canto da vista).
- **"PRINT"**: o pedido não diz onde fica o botão; vai na barra da vista, ao lado de "Vista".
- **"ultima medida"** = a última que foi feita, de qualquer tipo (distância ou ângulo).

## Situação atual

- **R1 (barra).** `ui/widgets/structure3d/window.py:37` `VIEWS = ("a", "b", "c", "x", "y", "z")`; `_bar` (`:92-121`) faz uma ação por vista, "Ao longo de a (A)" … "Ao longo de z (Z)" (`:112-116`), em `view_actions`; o tooltip do botão é "Olhar ao longo de um eixo" (`:108`). As teclas são outro caminho: `canvas.py:31-38` `AXIS_KEYS` (A, B, C, X, Y, Z) → `view_along` (`:135-137`) → `Camera.view_axis` (`camera.py:115-127`), e `shortcut_help` (`canvas.py:95-96`) lista "Vista ao longo de a, b, c" e "…x, y, z". O teste `tests/test_structure3d_canvas.py:148-161` usa `view_actions["x"]` e a tecla C.
- **R2 (Exibição).** `ui/widgets/structure3d/panel.py:135-171` (`_build_display`) põe as linhas nesta ordem (`:155-164`): "Estilo", "Raio", **"Ligações"** (caixa), "Fator de ligação", "Repetição", "Rótulos", **"Caixa da célula"**, **"Eixos"**, **"Perspectiva"** (caixas), "Fundo": a caixa "Ligações" fica três linhas longe das outras.
  Há **uma** caixa de eixos, `show_axes` (`panel.py:153`, `:162`) ↔ `DisplayOptions.show_axes` (`core/structure3d/options.py:36`), que desliga os dois sistemas: as setas a, b, c (primitiva `K_ARROW`, `renderer.py:261-271`, espessura `1.8` px em `:269`) e, no overlay, os nomes a, b, c e o triedro x, y, z (`overlay.py:103-109`; `_triad`, `:63-74`: caneta de `2.0` px em `:69`, 30 px de comprimento em `:68`). A ponta da seta tem 8 px fixos (`arrow_head`, `overlay.py:28-38`). Nenhum campo muda uma espessura.
  **Texto:** `renderer.py:34` `LABEL_PX = 11` → `ui_font(LABEL_PX)` (`:371`) → `draw_overlays` põe a fonte uma vez no painter (`overlay.py:90`); por isso os rótulos dos átomos (`:92-95`), os nomes a, b, c (`:104-108`), as letras do triedro (`:74`) e o número do selo de uma medida (`badge`, `:59`, num disco de raio fixo `BADGE_RADIUS = 8` px, `:23`) têm todos o mesmo tamanho, que nada edita (lido no código; não medido).
  Testes de hoje: `tests/test_structure3d_render.py:53` põe `canvas.options.show_axes = False`; `tests/test_structure3d_panel.py:182-195` (`test_display_fields_edit_the_options`).
- **R3 (rotação).** A orientação só muda pelo arcball (`camera.py:84-94`, ligado em `canvas.py:239-278`) ou por `view_axis`, que *alinha* a vista a um eixo (e reenquadra: `view_along`, `canvas.py:135-137`); não há passo de rotação. `_rotation(axis, angle)` (`camera.py:13-20`, Rodrigues) existe, e a câmera guarda `rotation` com as linhas (direita, cima, para o observador), `v = R (p − centro)` (`camera.py:40-46`). As seções do painel são `TITLES = ("Átomo", "Medidas", "Exibição", "Espécies", "Célula")` (`panel.py:45`), abertas por padrão `OPEN_BY_DEFAULT` (`:46`).
- **R4 ("Apagar").** `ui/widgets/structure3d/measures.py:174-187`: dois botões, "Copiar" e "Limpar" (`clear`, `:268-277`: as duas tabelas, os átomos pendentes e as marcas). Para tirar uma linha só, selecioná-la e apertar Delete (`MeasureTable.keyPressEvent`, `:125-130` → `delete_selected`, `:254-266`). `self.measurements` é a lista na ordem em que foram feitas (`:142`, `:233`) e as linhas de cada tabela seguem essa ordem (`add`, `:91-101`).
- **R5 ("Print").** Nada exporta a vista: o "Fora de escopo" da spec 43 diz "Exportar imagem (PNG/SVG) da vista: não pedido". `StructureCanvas.render_image(size, draft=False, dpr=1.0)` (`canvas.py:201-215`) desenha um quadro num `QImage` sem mostrar o widget (o anel de foco é do `paintEvent`, `:189-199`: não entra). As figuras do Lain vão para `<simulação>/plots/` (`PLOTS_DIR`, `core/plotting/export.py:25`) com o nome `<pastas desde a raiz>-<nome>` (`core/plotting/names.py`: `export_prefix`, `join_stem`; spec 32) e nunca sobrescrevem (`_2` primeiro: `next_free_stem`); `plots/` não vai no push (`DEFAULT_PUSH_EXCLUDES`, `core/config.py:59`). `core/unique_names.py:write_new` escreve só texto.
  **Medido** (script no scratchpad, fora do repositório; camadas de grafeno empilhadas de `tests/test_perf_structure3d.py`, vista de 960 × 780, bola e vareta, offscreen): o quadro a 1× leva 16 / 47 / 99 ms com 500 / 2 000 / 5 000 átomos, a 2× leva 39 / 110 / 213 ms, e codificar a imagem de 1920 × 1560 em PNG leva 156 / 206 / 172 ms (1,0 a 1,7 MB).
- **R6 ("Restaurar padrões").** A janela 3D não tem como voltar ao padrão: R / "Resetar vista" só reenquadra a câmera e "Restaurar cores" (`panel.py:255-259`, `restore_colors`) só limpa as cores das espécies; as opções (`StructureCanvas.options`, o objeto que o painel lê a cada uso: `panel.py:175`, `:196`, `:238`) não têm volta, e com as linhas novas da R2 são 14 campos mais as espécies. O precedente é o painel dos gráficos: `QPushButton("Restaurar padrões")` no rodapé do painel (`ui/widgets/params_body.py:84-91`, tooltip "Voltar todos os ajustes ao padrão e apagar `<kind>.plot`") e `PlotWorkflow.restore_defaults` (`ui/plot_workflow.py:413-431`), que **pergunta** com `QMessageBox.question` ("Voltar todos os ajustes deste gráfico ao padrão e apagar …?") antes de agir. O painel 3D é uma coluna de seções numa `QScrollArea` (`panel.py:87-103`) sem rodapé. Os padrões de hoje: `DisplayOptions(background=<tema>)` em `window.py:68-69`; câmera enquadrada por `reset_view` (`canvas.py:121-133`).

## Requisitos

### R1: A barra da vista só com x, y, z

1. `window.py`: `VIEWS = ("x", "y", "z")`. O menu "Vista" tem "Ao longo de x (X)", "Ao longo de y (Y)" e "Ao longo de z (Z)", e `view_actions` só essas três chaves.
2. As teclas A, B e C **continuam** (`AXIS_KEYS`, `view_along`, `Camera.view_axis` e a linha "Vista ao longo de a, b, c" de `shortcut_help` não mudam): só a barra perde as opções. O tooltip do botão "Vista" passa a "Olhar ao longo de x, y ou z (as teclas A, B e C olham ao longo de a, b e c)", para a vista ao longo da rede continuar descobrível.
3. **Testes** (`tests/test_structure3d_canvas.py`, estendendo `test_keys_and_view_menu`): `list(window.view_actions) == ["x", "y", "z"]` e os textos do menu; a tecla C ainda alinha a vista a c (o teste de hoje); o tooltip diz as teclas.

### R2: "Exibição": eixos separados, espessuras, tamanho dos rótulos e as caixas juntas

1. **Opções** (`core/structure3d/options.py`, Qt-free): `show_axes` sai; entram `show_abc: bool = True`, `show_xyz: bool = True`, `abc_width: float = 1.8` e `xyz_width: float = 2.0` (px na tela, **os valores de hoje**: o desenho com os padrões não muda), e `label_size: int = 11` (px na escala de fonte 1, o `LABEL_PX` de hoje). Constantes públicas: `MIN_AXIS_WIDTH, MAX_AXIS_WIDTH = 0.5, 8.0`, `MIN_LABEL_SIZE, MAX_LABEL_SIZE = 8, 32` e os três padrões (`DEFAULT_ABC_WIDTH`, `DEFAULT_XYZ_WIDTH`, `DEFAULT_LABEL_SIZE`); `__all__` e o docstring do módulo acompanham.
2. **Desenho.**
   - `show_abc` liga as setas a, b, c (a primitiva `K_ARROW`, espessura `options.abc_width`) **e** os seus nomes; `show_xyz` liga o triedro (caneta `options.xyz_width`) e as suas letras. Os dois são independentes: com um desligado o outro continua inteiro.
   - A ponta da seta cresce com a espessura: `ARROW_HEAD_PX × max(1, abc_width / DEFAULT_ABC_WIDTH)` (8 px no padrão, como hoje); o comprimento do triedro (30 px) não muda.
   - **Tamanho:** `ui_font(options.label_size)` no lugar de `ui_font(LABEL_PX)`; vale para os rótulos dos átomos, os nomes a, b, c e as letras do triedro. O **selo numerado** de uma medida (`badge`) **mantém** `DEFAULT_LABEL_SIZE`: o disco tem raio fixo e um número maior vazaria dele (`draw_overlays` põe a fonte do selo antes de desenhá-lo e volta à dos rótulos).
   - `LABEL_PX` sai do `renderer.py`.
3. **Painel** (`panel.py:_build_display`), **nesta ordem** (as caixas juntas, uma depois da outra, depois as espessuras que dependem das duas últimas):

   | # | Linha | Campo | Observação |
   |---|---|---|---|
   | 1 | "Estilo" | combo | como hoje |
   | 2 | "Raio" | decimal | como hoje |
   | 3 | "Fator de ligação" | decimal | como hoje; desabilitado sem "Ligações" |
   | 4 | "Repetição" | a, b, c | como hoje |
   | 5 | "Rótulos" | combo | como hoje |
   | 6 | "Tamanho dos rótulos" | `NoWheelSpinBox` 8–32, sufixo " px" | `label_size`; tooltip "Tamanho do texto da vista: rótulos dos átomos e nomes dos eixos" |
   | 7 | "Fundo" | combo | como hoje |
   | 8 | "Ligações" | caixa | `show_bonds` |
   | 9 | "Caixa da célula" | caixa | `show_cell` |
   | 10 | "Perspectiva" | caixa | `perspective` (a tecla P continua atualizando-a) |
   | 11 | "Eixos x, y, z" | caixa | `show_xyz`; tooltip "Triedro x, y, z do canto da vista" |
   | 12 | "Eixos a, b, c" | caixa | `show_abc`; tooltip "Setas a, b, c da célula" |
   | 13 | "Espessura x, y, z" | decimal 0,5–8,0, passo 0,5, sufixo " px" | `xyz_width`; **desabilitado** com "Eixos x, y, z" desligada |
   | 14 | "Espessura a, b, c" | decimal 0,5–8,0, passo 0,5, sufixo " px" | `abc_width`; desabilitado com "Eixos a, b, c" desligada |

   Os campos novos são `NoWheel*` (a roda rola o painel) e a localidade é `QLocale.c()` (ponto decimal), como os de hoje. O atributo `panel.show_axes` sai; entram `panel.show_xyz`, `panel.show_abc`, `panel.label_size`, `panel.xyz_width` e `panel.abc_width`. `sync()` e `_changed()` seguem um só caminho (`_syncing`), e nenhum campo move a câmera (spec 43 R3).
4. **Testes.**
   - `tests/test_structure3d_panel.py`: (a) a ordem das linhas da seção "Exibição" é a da tabela e as cinco caixas (8 a 12) estão em linhas **consecutivas** da grade; (b) cada caixa de eixos edita só o seu campo (`show_xyz` desligado deixa `show_abc` ligado) e a espessura correspondente fica desabilitada; (c) cada campo novo edita a sua opção (e `sync()` o devolve ao painel depois de P); `test_the_wheel_does_not_change_a_field` ganha os três campos numéricos novos.
   - `tests/test_structure3d_render.py` (`render_image`, offscreen; use uma estrutura com a origem da célula à vista, como `si_bands/si.scf.in` com `reset_view()`, e compare recortes em volta da origem projetada e do canto do triedro): (d) `show_abc` desligado tira as setas e seus nomes e deixa o triedro idêntico, e o contrário também (o `FrameStats.primitives` cai de 3 só com `show_abc` desligado); (e) `abc_width` e `xyz_width` maiores aumentam os pixels que não são fundo no recorte, e os padrões produzem as mesmas espessuras de antes (`1.8` e `2.0`); (f) `label_size` 20 faz o texto de "Símbolo" ocupar um retângulo maior que com 11, e o disco do selo de uma medida tem os mesmos pixels com 11 e com 20.
   - O teste de hoje `test_structure3d_render.py:53` passa a desligar `show_abc` e `show_xyz`.

### R3: Seção "Rotação": girar a estrutura 45° em torno de x, y e z

1. **Núcleo** (`core/structure3d/camera.py`, Qt-free): `ROTATION_STEP_DEG = 45.0` e `Camera.rotate_world(axis: str, degrees: float)`, `axis` em `"x"`, `"y"`, `"z"`: gira a **estrutura** em torno do eixo cartesiano do mundo que passa pelo centro da vista (`camera.center`, o centro do bloco), regra da mão direita (`x+` leva +y para +z), isto é `rotation ← rotation @ R_axis(θ)`. `zoom`, `pan`, `center` e `focal` não mudam.
2. **Vista** (`canvas.py`): `StructureCanvas.rotate_structure(axis, degrees=ROTATION_STEP_DEG)` chama `rotate_world` e `update()`. **Não reenquadra** (o zoom que o usuário escolheu fica: spec 43 R3), não mexe na seleção, nas marcas nem nas medidas; o ponto central da estrutura fica onde estava na tela.
3. **Painel** (`ui/widgets/structure3d/rotation.py`, novo): `RotationSection(section, canvas)` preenche a seção **"Rotação"** (cabeçalho "ROTAÇÃO"): seis `QPushButton` numa grade de 3 colunas e 2 linhas, **`x+`, `y+`, `z+`** em cima e **`x-`, `y-`, `z-`** embaixo, cada um com o tooltip "Girar a estrutura 45° em torno de x (regra da mão direita)" (e "… no sentido contrário" para os `-`) e o mesmo texto como `accessibleName`. Clicar chama `canvas.rotate_structure`. Os botões ficam em `buttons["x+"]` … `buttons["z-"]`.
4. `TITLES` ganha "Rotação" **depois de "Exibição"** (`("Átomo", "Medidas", "Exibição", "Rotação", "Espécies", "Célula")`) e `OPEN_BY_DEFAULT` também (a seção é pequena e foi pedida como atalho); o estado aberto/fechado é o QSettings `structure3d/sections/Rotação`, como as outras.
5. **Testes.**
   - `tests/test_structure3d_core.py` (câmera): `x+` seguido de `x-` devolve a `rotation` (a 1e-12); oito `z+` voltam à inicial; para um ponto do mundo, `camera_coords` depois de `rotate_world("z", 90)` é a de rodar o ponto +90° em torno de z (o eixo +x vai para +y); `zoom`, `pan`, `center` e `focal` iguais; um eixo desconhecido levanta `ValueError`.
   - `tests/test_structure3d_rotation.py` (novo, janela com `Windows(qtbot).open(SI_SCF)`): a seção vem depois de "Exibição" e está aberta; os seis botões existem com os textos pedidos; cada clique deixa `rotation == antes @ R_axis(±45°)` e `zoom`, `pan` e o átomo atual iguais; um átomo na tela se move (a projeção muda) e nenhum clique de rotação inicia uma medida nem muda `canvas.marks`; a vista de perspectiva e a ortográfica giram igual.

### R4: "Apagar" apaga a última medida

1. `MeasuresSection` (`measures.py`): botão **"Apagar"** (`delete_button`) logo depois de "Limpar" na mesma linha, tooltip "Apagar a última medida", habilitado quando `bool(self.measurements)` (como "Limpar" e "Copiar"; `_refresh`).
2. `delete_last()`: remove `measurements[-1]` (a última **feita**, de qualquer tipo) da lista e a última linha da tabela do seu tipo (a ordem das linhas é a das medidas: `add` acrescenta nos dois). Nada mais muda: os átomos **pendentes** de uma medida em andamento ficam (as marcas voltam a ser os pendentes, como em `delete_selected`), a linha selecionada em outra tabela não importa (apaga a última feita, não a selecionada), e a tabela que fica vazia se esconde com o seu título. Delete na tabela e "Limpar" continuam como são.
3. **Testes** (`tests/test_structure3d_measure_ui.py`, estendendo `test_copy_clear_and_delete`): com d1, d2 e a1 feitos nessa ordem, "Apagar" tira a1 (a tabela de ângulos se esconde), depois d2, depois d1, e o botão fica desabilitado; com a linha de d1 selecionada, "Apagar" ainda tira a última; com um átomo pendente, ele continua pendente (`measurer.pending`, `canvas.marks`) e a medida anterior é a que sai; "Copiar" depois de "Apagar" não traz a medida; `measurements` e as linhas das tabelas coincidem depois de misturar Delete e "Apagar".

### R5: Botão "Print": a vista em PNG

1. **Botão** na barra da vista (`window.py:_bar`), depois de "Vista", um `IconButton` (variante `plotTool`, ícone `image`, já vendorizado) com o texto "Print" e o tooltip "Salvar a imagem da vista em PNG, na pasta plots/ do cálculo". Atributo `print_button`. Uma estrutura sem arquivo de origem (`source.path` vazio, só em código) deixa o botão desabilitado.
2. **Imagem.** `canvas.render_image(canvas.size(), draft=False, dpr=PRINT_SCALE)` na thread da GUI, com `PRINT_SCALE = 2` (o tamanho da vista × 2 em pixels: 1920 × 1560 para uma vista de 960 × 780): é **a vista como está** (câmera, opções, fundo; o anel do átomo atual e os selos das medidas entram, o anel de foco e o de passagem do mouse não). Para uma imagem limpa o usuário clica no vazio antes.
3. **Arquivo** (`core/structure3d/image_file.py`, novo, Qt-free): `print_stem(source_path, root)` = `join_stem(export_prefix(pasta, root), f"{nome sem a última extensão}-3d")` (`<local_root>/ilita/Analise_1/scf.in` → `ilita-Analise_1-scf-3d`; a pasta é a própria raiz → `scf-3d`; fora da raiz ou `root` `None` → o nome da pasta do arquivo, `Analise_1-scf-3d`); `save_png(folder, stem, data: bytes) -> Path` cria `<pasta>/plots/` **sem** `parents` (uma pasta que sumiu é erro, nunca recriada) e grava `plots/<stem>.png`, ou `<stem>_2.png`, `_3`… se o nome existe, **nunca sobrescrevendo**, com `O_EXCL` (duas janelas, ou dois cliques seguidos, nunca escolhem o mesmo nome). `core/unique_names.py` ganha `write_new_bytes(path, data, first=1)`; `write_new` e ele dividem o laço (os testes de hoje de `test_unique_names.py` seguem verdes) e o `save_png` usa `first=2`, a convenção das figuras.
4. **Fluxo.** A codificação em PNG (150 a 210 ms, medido) roda num worker: `ui/widgets/structure3d/print_image.py:save_view(image, folder, stem) -> Path` (encoda o `QImage` num `QBuffer` e chama `save_png`) em `run_task`, com `on_done` / `on_error` métodos da janela. Ao terminar: barra de status "Imagem salva em plots/`<nome>`" (3 s) e o sinal `image_saved(Path)`; em erro, "Não foi possível salvar a imagem: `<motivo>`" (8 s) e `print_failed(str)`. Nenhum diálogo: um clique, um arquivo.
5. **A raiz do projeto** vem do controlador: `StructureWindow(..., root: Callable[[], Path | None] | None = None)` (chamado a cada clique) e `Structure3DController.for_window` passa `lambda: window.config.paths.local_root`, como o `PlotExporter`. Sem `root` (testes, scripts), o prefixo é a pasta do arquivo.
6. **Testes.**
   - `tests/test_structure3d_image.py` (novo, core): `print_stem` nos três casos acima, com um nome longo (cortado por `MAX_STEM_BYTES`) e sem pasta; `save_png` grava os bytes, cria `plots/`, nunca sobrescreve (o conteúdo do primeiro fica), numera `_2`, `_3`, e não recria uma pasta que sumiu (`tmp_path / "sumiu"` continua inexistente, `FileNotFoundError`); `test_unique_names.py`: `write_new_bytes` (bytes iguais, `first=2`, nunca sobrescreve, uma escrita que falha não deixa arquivo).
   - `tests/test_structure3d_print.py` (novo; **cópia** de `si_bands/si.scf.in` em `tmp_path`: nunca escrever em `tests/fixtures/`): clicar "Print" (espera `image_saved`) cria `plots/<pasta>-si.scf-3d.png`, um PNG válido de `canvas.width() × 2` por `canvas.height() × 2` pixels cujo pixel do canto é o fundo da cena; o segundo clique faz `…-3d_2.png` e deixa o primeiro igual; a câmera, as opções e a seleção não mudam; com `root` o nome leva o projeto; a pasta removida antes do clique dá `print_failed` e nenhuma pasta recriada; um átomo atual aparece como anel na imagem e some depois de clicar no vazio.
   - `tests/test_structure3d_ui.py`: pela janela principal (`demo_project` é a raiz), imprimir uma janela aberta de `05_si/si.scf.in` grava `05_si/plots/05_si-si.scf-3d.png`.
   - `tests/test_perf_structure3d.py` (`perf`): o quadro a 2× de 2 000 átomos ≤ 200 ms (medido 110 ms); a codificação não entra (worker).

### R6: "Restaurar padrões" volta as opções e a câmera ao padrão

1. **Botão** "Restaurar padrões" (`panel.restore_button`, `QPushButton`) num **rodapé fixo** do `StructurePanel`, abaixo da `QScrollArea` (sempre à vista, mesmo com o painel rolado), com o tooltip "Voltar as opções, a câmera e a rotação ao padrão". Sempre habilitado: não há como comparar a câmera atual com a enquadrada de forma confiável (o zoom do padrão depende do tamanho da vista).
2. **Pergunta**, como a dos gráficos: `ask_restore(parent) -> bool` (função de módulo de `panel.py`, trocada nos testes como `ask_discard`; `QMessageBox.question`, título "Restaurar padrões", texto "Voltar todas as opções e a câmera desta janela ao padrão?"). "Não": nada muda.
3. **Efeito** (`StructureCanvas.restore_defaults(background)`, que o painel chama com o fundo do tema do app **agora**, `theme.name`: `dark` → "escuro", `light` → "claro"):
   - `self.options` vira um `DisplayOptions(background=…)` novo: estilo, raio, fator, ligações, repetição, rótulos, tamanho, caixa, perspectiva, as duas caixas de eixos e as espessuras nos padrões, cores e visibilidade das espécies limpas; o objeto é **trocado** (o painel e o renderer o leem a cada uso), e `refresh_options()` refaz a cena;
   - a câmera volta à vista inicial: `reset_view()` (isométrica, enquadrada), zoom, deslocamento e rotação incluídos;
   - o painel é atualizado (`sync()`, as cores das espécies como em `restore_colors`, as caixas "Visível" marcadas, sem disparar `set_species_visible` uma vez por espécie);
   - **ficam**: o átomo atual, os átomos pendentes e as medidas (e o modo), o estado aberto ou fechado das seções (QSettings), o tamanho da janela.
4. `StructureCanvas.restored: bool` fica `True` depois do passo 3 (a spec 47 o usa para apagar a seção do `view3d.plot` ao fechar); sem a spec 47 nada o lê.
5. **Testes** (`tests/test_structure3d_panel.py`, `Windows(qtbot).open(SLAB_2X1)`, `ask_restore` trocado): com estilo, raio, repetição, as duas caixas de eixos, espessuras, tamanho, uma cor e uma espécie oculta mudados, mais zoom, pan e uma rotação, "Restaurar padrões" (resposta Sim) deixa `canvas.options == DisplayOptions(background="escuro")`, cada campo do painel no padrão, os swatches na cor Jmol, todas as caixas "Visível" marcadas, a câmera igual à inicial (`same_camera`) e `canvas.restored`; com a resposta Não nada muda; um átomo atual e uma medida feita continuam (`canvas.current`, `measures.measurements`); uma janela com o tema claro (`ThemeManager("light")`) restaura para `"claro"`; depois de restaurar, uma edição e um clique de "Rotação" funcionam (o painel não ficou preso ao objeto antigo: `panel.radius.setValue` muda `canvas.options` **novo**).

## Fora de escopo

- **Gravar** as opções novas, a câmera e a rotação entre aberturas da janela: spec 47 (`view3d.plot`). O que "Restaurar padrões" faz com o arquivo também é da 47 (R3.5).
- Atalhos de teclado para girar ou para o "Print"; passo de rotação ajustável (o pedido é 45° fixo) e giro em torno dos eixos da tela ou dos vetores da rede (a, b, c).
- "Print" em SVG ou PDF, com fundo transparente, resolução escolhida ou **sem** os anéis e os selos: é a vista como está; diálogo para escolher onde salvar (sempre `plots/`).
- Tamanho do triedro (30 px) e das letras separado do dos rótulos dos átomos.
- "Restaurar padrões" que também apague as medidas, o átomo atual ou o estado das seções do painel: só opções e câmera; um botão de "voltar só a câmera" já existe (R, "Resetar vista").
- Desfazer (Ctrl+Z) de várias medidas; "Apagar" pede só a última.
- Tirar as teclas A, B e C: só a barra perde as opções (decisão 1).

## Decisões assumidas (confirmar na revisão)

1. **A, B e C continuam como teclas**; só o menu "Vista" da barra deixa de listá-las (o pedido fala de "mostrar" na barra). Se a ideia é tirar a vista ao longo de a, b, c da janela, basta apagar três entradas de `AXIS_KEYS` e a linha de `shortcut_help`.
2. **"Tamanho dos rótulos" vale para os rótulos dos átomos e para os nomes dos eixos** (a, b, c e x, y, z): são todos "rótulos" da vista e dividem uma fonte hoje. O número do selo de uma medida não cresce (disco de raio fixo).
3. **Os eixos da "Rotação" são os cartesianos x, y, z da estrutura** (os do triedro), pelo centro do bloco, **regra da mão direita aplicada à estrutura**; os botões de uma vista "para a direita / para cima" da tela são a alternativa. A rotação **não reenquadra**: o zoom e a posição ficam.
4. **A ordem da "Exibição"** é a da tabela do R2: o "Fator de ligação" sai do lado de "Ligações" para ficar entre os campos, e as espessuras vêm logo depois das duas caixas de eixos.
5. **Espessura em px na tela** (0,5 a 8,0), com os padrões de hoje (1,8 e 2,0); a ponta da seta cresce junto.
6. **"Apagar" é literal**: a última medida completa, de qualquer tipo; os átomos de uma medida em andamento não são tocados (Esc ou um clique no vazio os descarta, como hoje).
7. **"Print" grava direto em `plots/`**, sem diálogo, no nome `<pastas desde a raiz>-<arquivo>-3d.png` (a convenção da spec 32) e nunca sobrescreve (`_2`, `_3`…): muitos prints em ângulos diferentes são um clique cada. O texto do botão é "Print" (o pedido escreve 'PRINT'; o resto da barra está em caixa mista: é a constante `PRINT_TEXT`). A alternativa é um "Salvar como…" com o nome sugerido.
8. **A imagem tem o dobro dos pixels da vista** (`PRINT_SCALE = 2`, nítida num documento) e é a vista como está, com anéis e selos.
9. **"Restaurar padrões" fica num rodapé fixo do painel** (o painel é longo, e no fim da coluna ele ficaria atrás da rolagem; o dos gráficos fica no fim da coluna). Pergunta antes, como o dos gráficos. A alternativa é o fim da coluna, sem rodapé.
10. **O padrão é o das opções de uma janela nova**, com o fundo do tema do app *agora* (não o do momento em que a janela abriu); a câmera volta à vista inicial enquadrada. Medidas e átomo atual não são ajustes e ficam.

## Notas de implementação

- Novos: `src/qe_studio/ui/widgets/structure3d/rotation.py`, `src/qe_studio/ui/widgets/structure3d/print_image.py`, `src/qe_studio/core/structure3d/image_file.py`, `tests/test_structure3d_rotation.py`, `tests/test_structure3d_print.py`, `tests/test_structure3d_image.py`.
- Alterados: `core/structure3d/options.py` (campos e constantes), `core/structure3d/camera.py` (`rotate_world`), `core/unique_names.py` (`write_new_bytes`), `ui/widgets/structure3d/panel.py` (linhas, `TITLES`, a seção "Rotação", o rodapé "Restaurar padrões" e `ask_restore`), `renderer.py` (`show_abc`, `abc_width`, `label_size`), `overlay.py` (`show_xyz`, `xyz_width`, ponta da seta, fonte do selo), `canvas.py` (`rotate_structure`, `restore_defaults`, `restored`), `measures.py` (`delete_button`), `window.py` (barra, "Print", `root`), `ui/structure3d_controller.py` (`root`), `tests/test_architecture.py` (`QT_FREE`: `qe_studio.core.structure3d.image_file`) e os testes citados.
- Limites (`wc -l`, conferido): `window.py` 154, `panel.py` 290, `canvas.py` 343, `renderer.py` 414, `overlay.py` 109, `measures.py` 298, `structure3d_controller.py` 109. Espera-se `renderer.py` ≈ 420 (só linhas existentes mudam) e os demais abaixo de 400; a "Rotação" e o "Print" já nascem em arquivos próprios. `ui/main_window.py` (450/450) **não muda**.
- Se importar `core/plotting/export.py` (para `PLOTS_DIR`) arrastar matplotlib para quem só importa `core.structure3d.image_file`, mover a constante para `core/plotting/names.py` e reexportá-la em `export.py`.
- Documentação ao implementar: seção "Visualização 3D (specs 43, 44)" do `CLAUDE.md` (títulos para 43, 44, 46; a barra, os campos de `DisplayOptions`, a "Rotação", o "Apagar", o "Print", o "Restaurar padrões" e `image_file`); o parágrafo da "Visualização 3D" do `README.md` (campos de exibição, rotação, **Print**, **Apagar**, **Restaurar padrões**); o "Fora de escopo" da spec 43 sobre exportar imagem fica superado por esta (os arquivos de `Archived/` não se reescrevem).

## Critérios de aceite e testes

- [x] Com os padrões, `canvas.render_image` de `si.scf.in` (vista inicial, 1000 × 800) é **idêntica pixel a pixel** à da versão anterior (passo de verificação no mesmo ambiente: capturar as duas imagens num script do scratchpad, não vira teste, porque depende da versão do Qt); os testes de `test_structure3d_render.py`, `test_structure3d_canvas.py` e `test_structure3d_measure_ui.py` de hoje passam, só trocando `show_axes` por `show_abc` / `show_xyz`.
- [x] A barra só tem x, y, z e as teclas A, B, C seguem alinhando (`test_structure3d_canvas.py`).
- [x] A seção "Exibição" tem a ordem da tabela, as cinco caixas seguidas, as caixas de eixos independentes e as espessuras desabilitadas com o sistema desligado (`test_structure3d_panel.py`).
- [x] Espessura e tamanho dos rótulos mudam o desenho, e o selo da medida não cresce (`test_structure3d_render.py`).
- [x] "Rotação" gira 45° em torno de cada eixo nos dois sentidos, sem mexer em zoom, pan e seleção (`test_structure3d_core.py`, `test_structure3d_rotation.py`, novo).
- [x] "Apagar" tira a última medida feita, preserva os átomos pendentes e desabilita-se sem medidas (`test_structure3d_measure_ui.py`).
- [x] "Print" grava um PNG de 2× o tamanho da vista em `plots/` com o nome da convenção, nunca sobrescreve, e falha com mensagem sem recriar a pasta (`test_structure3d_image.py` e `test_structure3d_print.py`, novos; `test_structure3d_ui.py`).
- [x] "Restaurar padrões" pergunta, volta opções e câmera ao padrão (fundo do tema de agora), atualiza o painel inteiro e deixa medidas e átomo atual (`test_structure3d_panel.py`).
- [x] `test_fixtures_untouched.py` e `test_architecture.py` verdes (nenhum teste escreve em `tests/fixtures/`; `image_file` em `QT_FREE`; `FS_ALLOWED` sem entrada nova).
- [ ] (pendente: o usuário) Passo manual de aceite: o usuário abre o `scf` de uma superfície real, desliga só os eixos a, b, c, engrossa os x, y, z, aumenta os rótulos, gira 45° em torno de z duas vezes, tira um "Print" e abre o PNG em `plots/`.
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
