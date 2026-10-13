# Spec 43: "Visualização 3D" da estrutura de um input do pw.x, numa janela própria

| | |
|---|---|
| **Prioridade** | 43 (abre a rodada; a 44 constrói as medidas sobre ela). Independente das specs 33–42 |
| **Status** | Implementada (13/10/2026); ver "Decisões na implementação" |
| **Depende de** | spec 5 (`ItemActions`, menu de contexto), spec 11 (sniff `PW_IN` do input), spec 15 (`run_task`, controladores `for_window`), spec 19 (tema, escala de fonte, anel de foco), spec 25 (`core/qe/lattice.crystal_from_editor`), spec 27-5 (`close_dialogs`, `steps_for`), spec 32 (`NoWheel*`), spec 40 (`surface/model.flags_of`) |
| **Usada por** | spec 44 (medidas de distância e ângulo) |
| **Esforço** | G (R1: M, porta do núcleo; R2: M, ligações; R3: P; R4 e R5: M, janela e painel) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): pacote novo em `core/` e em `ui/`, a primeira janela de topo sem pai e em várias instâncias (fechamento, foco, atalhos), geometria 3D no renderer e `ui/main_window.py` em 448 de 450 linhas. |

## Itens de origem (`Ideias.md`, 13/10/2026)

> - Quero implementar a visualização 3D das estruturas a partir do scf.
> - Primeiro pedir um relatorio, @Documentation/Relatorios/Relatorio_visualizacao_3D_da_estrutura.md para o Claude analizar possiveis formas de implementar.
> - A partir do relatorio, foi feito um teste isolado, foi criado um programa simples para visualizar a estrutura a partir do scf. Esse programa está salvo em @Documentation/Exemplo-visualizador_3d
> - Gostei desse resultado, e quero implementar uma visualização 3D no projeto Lain. Quero que seja implementado da seguinte forma:
> - No menu do botão direito do mouse, adicione a opção 'Visualização 3D'
> - Esse Botão deve abrir uma nova janela independente da janela principal do Lain. Nessa janela o usuario visualiza a estrutura atomica 3D do scf.
> - O usuario poderá abrir quantas janelas de visualização 3D quiser. Para cada vez que abir um scf usado o botão 'Visualização 3D', cria-se uma nova janela de visualização 3D. Um exemplo é quando temos varios scf no banco de dados, cada scf tem sua própria janela 3D independente. Cada janela deve ter suas proprias configuracoes, como zoom, cor dos atomos, etc.
> - Dentro dessa nova janela, vai ter um painel do lado esquerdo e um painel do lado direito. Igual como foi feito em @Documentation/Exemplo-visualizador_3d .
> - Na visualização 3D, as arestas entram dentro dos atomos, fica estranho, porque dá para vê as arestas dentro dos atomos. Quero que as arestas não entrem dentro das esferas dos atomos. E independende da possição que olho, as arestas parecem retangulos, não parecem cilindros, como são na realidade, melhore isso.
> - Quando dou zoom e seleciono um atomo, o zoom é desfeito. Quero que mantenha o zoom quando clicar nos atomos.
> - Melhore a UI da aba do lado esquerdo do visualizado 3D, a forma como foi feita no Exemplo-visualizador_3d não ficou boa.

Os itens de "Distância" e "Ângulos" do mesmo pedido estão na spec 44.

Interpretação e decisões do usuário (13/10/2026, perguntadas antes de escrever):

- **"a partir do scf"** = qualquer input do pw.x (`scf`, `nscf`, `bands`, `relax`, `vc-relax`…): a estrutura é lida do mesmo jeito.
  Saídas (`.out`) ficam fora (decisão do usuário).
- **"painel do lado esquerdo e painel do lado direito"** = painel de informações | vista 3D, como no exemplo; as medidas são uma seção
  do painel esquerdo (decisão do usuário; spec 44).
- **Desenho em `QPainter`**, como o exemplo, com as ligações corrigidas; OpenGL fica fora (decisão do usuário).
- **"arestas"** são as ligações (as varetas entre os átomos), não as arestas da caixa da célula: é o que entra nas esferas e o que
  deveria ser cilindro.
- Os átomos são nomeados pelo **número do QE** (`O43` = 43º átomo do input), o mesmo de `pdos_atm#43` (decisão do usuário).

## Situação atual

- **Nada de 3D no Lain.** Nenhum módulo de `src/qe_studio` desenha estrutura (busca por "3D" acha só textos de `types/charge.py`). As
  peças que existem: `core/qe/lattice.py:196` `crystal_from_editor(editor)` (todo `ibrav`, porta do `latgen` do QE 7.1; devolve
  `Crystal(cell Å, labels, frac)` ou levanta `StructureError` em português; `crystal_sg` não é suportado);
  `core/calc_create/scf_info.py:84` `scf_info` **recusa** `calculation ≠ 'scf'` (`:92-94`), então não serve para um input de relax;
  `core/calc_create/surface/model.py:60` `flags_of(text)` (os `if_pos`) e `:86` `species_rows(text)`;
  `core/calc_create/surface/elements.py:25` `element_of` **levanta** `SurfaceError` para um rótulo sem elemento (`:32`) e mora no pacote
  de superfícies; `core/qe/input_edit.py:65` `read_input_text(path)` (só em workers); `core/sniff.py:28` `INPUT_READ_LIMIT` = 2 MB.
- **A prova de conceito** (`Documentation/Exemplo-visualizador_3d/`, fora do git): `core/` sem Qt (só numpy, e `ase.data` / `scipy` com
  import tardio) com `structure.py`, `elements.py`, `bonds.py`, `replicate.py`, `measure.py`, `camera.py`, `pick.py`, mais um léxico e
  um `latgen` próprios (`qe_lexer.py`, `qe_input.py`, `lattice.py`) que duplicam os do Lain; `ui/` com `canvas.py`, `renderer_paint.py`,
  `renderer_overlay.py`, `render_types.py`, `options.py` e os painéis; 119 funções de teste em `tests/`. `PORTING.md` §2 descreve a API.
  `bonds.py:15` usa `scipy.spatial.cKDTree` a partir de 1 000 átomos (`:82`); `scipy` não é dependência declarada do Lain
  (`pyproject.toml:7-16`), chega pelo ASE.
- **R2 (ligações).** `renderer_paint.py:209-228`: cada metade de ligação vai do **centro** do átomo (`xy[end]`) ao ponto médio e é
  ordenada pela profundidade `(depth[end] + mid_depth) / 2`; é desenhada com `drawLine` e uma caneta de **cor única** com ponta redonda
  (`_bond_pen`, `:117-123`; `:285-287`). Medido (molécula tipo H₂O num cubo de 20 bohr, vista ortográfica ao longo de z, ligações no
  plano da tela, zoom 120 px/Å, script no scratchpad): o pixel no centro do O é `#ff0d0d` com ligações (a cor lisa da vareta) e
  `#f22222` sem elas (a esfera sombreada): **a metade da ligação é pintada por cima da esfera**. Quinze pixels atravessando a metade do
  O, fora da esfera, são todos `#ff0d0d` (só as bordas antisserrilhadas diferem): **uma faixa lisa, sem sombreamento**, o
  "retângulo". `PORTING.md` §4 lista as limitações do algoritmo do pintor.
- **R3 (zoom desfeito).** `canvas.py:262-264`: `mouseDoubleClickEvent` chama `reset_view` (vista isométrica + `fit`, `camera.py:152-162`).
  Reproduzido no offscreen com a janela do exemplo e `samples/scf.in`: 4 passos da roda levam o zoom de 24,71 a 51,24 px/Å; dois
  cliques simples em átomos mantêm 51,24; um `mousePress`/`mouseRelease` seguido de `QTest.mouseDClick` no mesmo átomo volta a 24,71 (a
  seleção fica). O Qt faz um duplo clique de dois cliques em 400 ms e 5 px (`QStyleHints` do offscreen): clicar de novo no mesmo átomo,
  ou um toque duplo no touchpad, desfaz o zoom. **Segundo caminho, também medido:** mudar o "Fator de ligação" no painel leva o zoom de
  49,42 a 24,71: `refresh_options` (`canvas.py:76-93`) zera `_built_reps` ao recalcular as ligações (`:82-86`), e a cena refeita reenquadra
  (`:87-92`). Mudar o estilo não mexe no zoom. Se há outra causa na tela real (X11) **não foi verificado**: o exemplo não rodou fora do
  offscreen nesta sessão.
- **R4 (menu e janela).** `ui/widgets/context_menu.py`: sinais em `:59-67`, `show` em `:84-106`, `file_actions_of` (`:108-117`, só o sniff
  em cache: a GUI não lê o arquivo), `menu` (`:126-174`: "Plotar", "Resumo" e "Gerar SCF convergido" no topo, separador, depois as ações
  de todo item). O sniff em cache de um input do pw.x tem `kind == FileKind.PW_IN` (`core/sniff.py:42`; `_sniff_input`, `:216-224`, pelo
  leitor de namelists do ASE: um input em que ele falha é `UNKNOWN`). `ui/main_window.py` tem **448 linhas** (limite 450,
  `PER_FILE_LIMIT`); os controladores nascem de `for_window` em `:198-206`. As janelas não modais de hoje (`calc_create`, `grids`,
  `help`) são uma de cada vez, filhas da janela principal, e `close_dialogs` (`ui/shutdown.py:115-120`) pergunta a cada uma
  (`GridsController.close_dialog`, `grids_controller.py:86-90`); `steps_for` cancela as tarefas em `:88-94`. A folha de estilo é aplicada
  ao `QApplication` (`ui/theme/manager.py:138-146`), então uma janela sem pai também a recebe; o ícone vem de `app.setWindowIcon`
  (`ui/app_identity.py:41`). Os atalhos de widget aparecem na janela de atalhos pelos `providers` de `HelpController.for_window`
  (`ui/help_controller.py:49-55`).
- **R5 (painel esquerdo do exemplo).** `LeftPanel(QTabWidget)` com quatro abas (`panels.py:205-232`); `QFormLayout` com rótulos crus
  ("Rótulo da espécie:", "starting_magnetization", `:49-63`); raio num `QSlider` (`panel_display.py:39`, a roda o mexe); espécies numa
  `QTableWidget` de widgets com estilo embutido (`:81`, `:182`); avisos num `QPlainTextEdit` (`panels.py:174`); a tabela de medidas com
  seis colunas cortadas ("H7…", na captura de tela tirada nesta sessão). O painel de ajustes do Lain tem o que falta: `PanelHeader`
  (`ui/widgets/common.py:77`), a seção sanfona `Section` (`ui/widgets/param_widgets.py:46`: cabeçalho em maiúsculas, grade 40/60
  rótulo/campo, variantes de QSS `sectionHeader` / `sectionBody` / `fieldLabel`), `ColorButton` (`:23`), `NoWheelSpinBox` /
  `NoWheelDoubleSpinBox` / `NoWheelComboBox` (`ui/widgets/no_wheel.py:19-39`) e o estado aberto/fechado em QSettings
  (`params_body.py:31` `SECTIONS_KEY`, `:168-176`).
- **Testes de hoje.** `test_perf_detection.py:163` `test_main_window_import_skips_ase` (nada de `ase` ao importar a janela);
  `test_architecture.py` (`QT_FREE`, `FS_ALLOWED`: `ui/widgets/context_menu.py` tem 4 chamadas de disco). Nenhum teste toca 3D.

## Requisitos

### R1: Núcleo `core/structure3d/` (Qt-free), portado da prova de conceito

1. Pacote novo `src/qe_studio/core/structure3d/` (o nome evita confusão com `core/qe/structure.py`, que é o `read_sites` da PDOS), sem
   PyQt6, cada módulo em `QT_FREE`. Porta do `core/` do exemplo com os imports ajustados e estas mudanças:
   - `model.py` (novo): `AtomRef(index, shift)`, `SpeciesInfo(label, mass, pseudo, number)`, `SourceInfo(path, ibrav, nat, ntyp, prefix,
     calculation, nspin, starting_magnetization: dict[int, float], warnings)` e `Structure` (o do exemplo: `cart`, `position(ref)`,
     `symbols`, `formula` de Hill, `volume`, `lattice_parameters`, `species_index`), **sem** `hubbard_u` (no QE ≥ 7.1 o U vai no card
     `HUBBARD`). Mais `atom_name(structure, ref) -> str`: símbolo do elemento + número do QE (`O43`), e `O43(1,0,0)` para uma cópia com
     deslocamento; rótulo sem elemento: o rótulo + número (`X5`).
   - `source.py` (novo): `structure_of_text(text, path=None) -> Structure` e `read_structure(path) -> Structure` (worker:
     `read_input_text`). Usa o que o Lain já tem, não o léxico nem o `latgen` do exemplo: `InputEditor.from_text`, `crystal_from_editor`,
     `flags_of`, as linhas de `ATOMIC_SPECIES` (massa, pseudopotencial; um rótulo de posição sem linha de espécie entra com massa e
     pseudo vazios e um aviso), `prefix` (padrão `pwscf`), `calculation` (padrão `scf`), `nspin`, `starting_magnetization(i)`. Qualquer
     `calculation`. Erros como `StructureReadError(str)`, em português: "`<nome>` não é um input do pw.x (sem &SYSTEM)", "Estrutura de
     `<nome>` ilegível: `<motivo do StructureError>`", "`<nome>` passa de 2 MB: grande demais para um input" (`INPUT_READ_LIMIT`).
   - `elements.py` (novo): o `element_for_label` do exemplo (nunca levanta; desconhecido = cinza, raio 1,0 Å, `known=False`), nomes em
     português, cores Jmol, vdW 1,8 Å quando o ASE não tem; `ase.data` importado no primeiro uso. A regra de rótulo → elemento é a de
     `surface/elements.element_of` (um teste confere as duas em todos os rótulos das fixtures). Um rótulo sem elemento põe em
     `SourceInfo.warnings`: "Espécie sem elemento conhecido: `<rótulo>` (cinza, raio 1,0 Å)".
   - `bonds.py`, `replicate.py`, `camera.py`, `pick.py` (novos): os do exemplo. `scipy` entra em `pyproject.toml` como dependência
     declarada (já instalada pelo ASE; continua com import tardio, só a partir de 1 000 átomos).
   - `options.py` (novo): o `DisplayOptions` de `ui/options.py` do exemplo (já era sem Qt), com `background: str` (`"escuro"` |
     `"claro"`) no lugar de `dark: bool` e o modo de rótulo `"indice"` exibido como "Número".
   - `geometry.py` (novo): o raio desenhado de cada átomo por estilo, hoje espalhado no renderer (`BALL_FACTOR`, `BOND_RADIUS`,
     `max_world_radius`), e as metades de ligação de R2. O renderer e a seleção leem daqui, então concordam.
   - **Não** se portam: `measure.py` (spec 44), `qe_lexer.py`, `qe_input.py`, `lattice.py`, `example.py` e a linha de comando.
2. Importar `qe_studio.core.structure3d.*` não carrega `ase` nem `scipy`; `test_main_window_import_skips_ase` continua verde com a `ui/`
   importando o pacote.
3. **Testes:** `tests/test_structure3d_source.py` (novo): cada input do pw.x das fixtures (`al_bands/al.scf.in`, `al_bands/al.band.in`,
   `al_pdos_flat/al.nscf.in`, `si_bands/si.scf.in`, `si_relax/si.rel.in`, `qe731_ni_spin_bands/ni.scf.in`, `kao_vc_relax/vc-relax.in`,
   os cinco de `kao_surface_inputs/`) é lido, com célula e frações iguais às de `crystal_from_editor`; `scf-kaolinite-slab-001-2x1x1.in`
   tem `flags` `(0, 0, 0)` nos átomos fixos (linha 48 do arquivo); `si.scf.in` tem a espécie `Si` com massa 28.086 e pseudo
   `Si.pz-rrkj.UPF`; `ni.scf.in` tem `starting_magnetization {1: 0.8}`; erros (sem `ATOMIC_POSITIONS`, `crystal_sg`, um bands.x input)
   dão a frase. `tests/test_structure3d_core.py` (novo): os testes de `bonds`, `replicate`, `camera`, `pick` e `elements` do exemplo,
   trocando a amostra dele pelas fixtures (Si diamante: 4 vizinhos por átomo a `√3/4 · celldm(1)`, 2,33 Å; `scf-H3CHg.in`: 3 ligações C–H) e `atom_name`.
   `test_properties.py`: as ligações de `frac + k` (k inteiro por átomo) têm as mesmas distâncias que as de `frac`.

### R2: Ligações como cilindros, que não entram nas esferas

1. `core/structure3d/geometry.py:half_bonds(scene, radii, bond_radius) -> HalfBonds` (novo): para a ligação a–b de eixo `u`, a metade de
   `a` começa na superfície da esfera, `a + u·√max(r_a² − ρ², 0)` (onde o cilindro de raio `ρ` encosta na esfera de raio `r_a`, o raio
   **desenhado**), e termina no ponto médio; a de `b` é a simétrica. Uma metade cujo início passa do ponto médio (esferas que se
   sobrepõem até ali) não é desenhada. `ρ` é o raio da vareta do estilo (`bola-vareta` 0,10 Å, `vareta` 0,20 Å); em `vareta` o átomo é
   a bolinha de 1,3 ρ do exemplo, e o corte usa esse raio; `fio` não corta (linhas de 1,6 px do centro ao centro, como hoje).
2. O renderer desenha cada metade como um **quadrilátero preenchido**: as projeções do início e do fim, alargadas `±ρ·zoom·escala` (a
   escala de perspectiva de cada ponta: a ponta mais perto fica mais larga), perpendicularmente ao eixo projetado; pincel
   `QLinearGradient` **atravessando a largura**, com a luz do mesmo lado que a das esferas (`_sphere_brush` do exemplo, `:92-103`, luz em
   cima à esquerda): borda escura (cor × 0,4), realce (45 % de branco) a 30 % da largura do lado da luz, cor base a 55 %, borda escura do
   outro lado. Sem tampas: as pontas ficam numa esfera ou na outra metade. Uma metade com menos de 0,5 px de comprimento projetado não
   é desenhada (vista de topo: a esfera a cobre). A chave de profundidade é a do ponto 3D do meio da metade. Fantasmas com a opacidade
   de hoje. No modo rascunho (arrasto com muitas primitivas) o pincel é liso, mas o corte na esfera continua.
3. Um renderer em arquivo próprio para as ligações se `renderer` passar de ~400 linhas (`ui/widgets/structure3d/bonds_paint.py`, novo,
   se preciso).
4. **Testes** (`tests/test_structure3d_render.py`, novo; `render_image` offscreen, sem janela):
   - geometria: o início de cada metade está a `√(r² − ρ²)` do centro, sobre o eixo; esferas que se sobrepõem até o meio → metade
     omitida; `fio` não corta;
   - **"dentro do átomo"**: a molécula de três átomos do teste (O no centro, dois H a 0,96 Å, no plano xy; texto do input no teste),
     vista ortográfica ao longo de z: o pixel do centro do O é **igual** com e sem ligações (no exemplo: `#ff0d0d` contra `#f22222`);
   - **"cilindro"**: 15 pixels atravessando uma metade fora da esfera têm ≥ 3 cores distintas, o mais claro longe das bordas e as duas
     bordas mais escuras que o centro (no exemplo: todos `#ff0d0d`); o mesmo em duas outras orientações (rotações da câmera), que é o
     "independente da posição que olho";
   - perspectiva: a ponta mais perto da câmera é mais larga que a outra.

### R3: O zoom não se desfaz

1. O duplo clique **não mexe na câmera** (sem `mouseDoubleClickEvent` de reset): ele vale como dois cliques, com as regras de seleção do
   clique simples. A vista volta ao início só por "Resetar vista" (barra da janela, R4.3) e pela tecla R.
2. A câmera só muda por: arrastar (girar; botão do meio ou Shift + arrastar: mover), roda e `+`/`-` (zoom no ponteiro / no centro), R e
   "Resetar vista", as vistas ao longo de a, b, c, x, y, z, e a **mudança da repetição** (o bloco muda de tamanho: reenquadra mantendo a
   rotação, como o exemplo). Nunca por: clicar num átomo ou no vazio, Ctrl + clique, clicar num vizinho da tabela, nem por qualquer campo
   do painel (estilo, raio, ligações, **fator de ligação**, rótulos, caixa, eixos, perspectiva, fundo, cores, visibilidade). Recalcular as
   ligações refaz a cena **sem** reenquadrar.
3. **Testes** (`tests/test_structure3d_canvas.py`, novo; a janela de R4 com `si.scf.in` e com `scf-kaolinite-slab-001-2x1x1.in`): com zoom
   e pan aplicados por eventos de roda e arrasto, `camera.zoom`, `camera.pan` e `camera.rotation` ficam iguais depois de: clique num
   átomo; `QTest.mouseDClick` num átomo (**falha sem a correção**); clique no vazio; Ctrl + clique; clique numa linha de vizinhos; mudar
   o fator de ligação (**falha sem a correção**), o estilo, o raio, uma cor e a visibilidade de uma espécie. R e "Resetar vista"
   restauram a vista inicial; mudar a repetição reenquadra.

### R4: "Visualização 3D" no menu e uma janela por clique

1. **Menu.** `ItemActions` ganha `structure_requested = pyqtSignal(Path)` e `menu(..., structure: bool = False)`; `show` passa
   `structure=True` quando o sniff em cache do arquivo tem `kind is FileKind.PW_IN` (qualquer `calculation`), lido na mesma consulta de
   `file_actions_of` (nenhuma leitura nova de disco: `FS_ALLOWED` não muda). O item "Visualização 3D" fica no grupo do topo, depois de
   "Resumo" e antes de "Gerar SCF convergido", e o separador do grupo passa a considerá-lo. Não aparece em pastas, em saídas, em inputs
   de bands.x / projwfc.x / dos.x / pp.x, nem com vários itens selecionados. Um input ainda sem sniff em cache não tem o item e pede a
   detecção (como "Plotar" hoje). Um input que o ASE não lê (`UNKNOWN`) não tem o item: limitação aceita.
2. **Controlador.** `ui/structure3d_controller.py:Structure3DController.for_window(window)` (novo) liga `item_actions.structure_requested`
   e cria a janela de cada pedido: `read_structure` em `run_task` (a GUI não lê o input), rótulo de ocupado "Lendo estrutura…" em
   `plot_workflow.busy` (chave `structure3d:<caminho>:<n>`); ao terminar, abre uma `StructureWindow` nova e emite `opened(window)`; em
   erro, `window.toast.show_message("Visualização 3D de <arquivo>: <motivo>", "warning")` e `failed(str)`, sem janela. **Cada pedido é uma
   janela nova**, também para o mesmo arquivo. Guarda as janelas abertas numa lista e tira cada uma pelo sinal `closed` que a própria
   janela emite no `closeEvent` (nunca um `partial`/lambda no `destroyed` dela). `close_dialog()` fecha todas (não há o que proteger) e
   devolve True; entra **por último** na tupla de `close_dialogs`. `cancel()` cancela as leituras pendentes e entra no passo "cancelar"
   de `steps_for`. Em `ui/main_window.py` só **uma** linha (`self.structure3d = Structure3DController.for_window(self)  # spec 43`),
   449 de 450.
3. **Janela.** `ui/widgets/structure3d/window.py:StructureWindow(QMainWindow)` (novo), **sem pai** (entrada própria na barra de tarefas;
   pode ficar atrás da principal), `WA_DeleteOnClose`, título "`<arquivo>` — `<pasta>` · Visualização 3D" (a pasta é o nome da pasta do
   arquivo), 1280 × 820. Centro: `QSplitter` com o painel (R5, 320 px) à esquerda e a vista à direita; a vista tem em cima uma barra como
   a do `PlotView` (`IconButton` "Resetar vista" e um menu "Vista ▾" com "Ao longo de a / b / c / x / y / z"). Barra de status: à esquerda
   "`scf.in` · `CH18Al8HgO36Si8` · nat = 72 · ibrav = 0"; à direita, o átomo sob o ponteiro ("C69 · Carbono") e "⚠" com os avisos do
   leitor no tooltip quando há algum. O tempo do quadro do exemplo não é mostrado.
4. **Configurações por janela.** Cada janela tem o seu `DisplayOptions`, a sua câmera e a sua seleção; nada é gravado por arquivo nem entre
   sessões. Ao abrir: os padrões do exemplo (bola e vareta, raio 1,00×, fator 1,15, ligações, repetição 1 1 1, sem rótulos, caixa, eixos,
   perspectiva) e o fundo do tema do app naquele momento (`ThemeManager.name`: `dark` → "Escuro", `light` → "Claro"); trocar o tema do app
   depois não mexe nas janelas abertas.
5. **Vista (canvas).** `ui/widgets/structure3d/canvas.py:StructureCanvas` (novo, o `Canvas` do exemplo com R2–R3): gestos e teclas do
   exemplo (arrastar gira, botão do meio ou Shift + arrastar move, roda e `+`/`-` dão zoom, R reseta, A/B/C e X/Y/Z alinham, P alterna a
   perspectiva). Clique (com ou sem Ctrl) seleciona o átomo **atual**, o que o painel "Átomo" mostra, marcado com um anel; clique no vazio
   limpa. A seleção de vários átomos do exemplo (até 4, na ordem do clique) sai: as medidas da spec 44 têm regras próprias. Os atalhos vão para a janela de atalhos: `StructureCanvas.shortcut_help()` (`staticmethod`,
   "Visualização 3D" na coluna "onde") entra nos `providers` de `HelpController.for_window`. Com foco, a vista desenha uma borda de
   1 px na cor `focus_ring` (`ThemeManager.color`); a fonte dos rótulos vem de `scaled_font`. As cores da cena (fundo, caixa, rótulos,
   eixos) são constantes do renderer por fundo (escuro/claro), como as figuras (spec 2) não seguem o tema: nenhum token novo.
6. **Testes** (`tests/test_structure3d_ui.py`, novo; fixture `main_window`, `QMenu.exec` trocado): o menu de `si.scf.in` (sniff em cache
   antes) tem "Visualização 3D" depois de "Resumo"/antes de "Gerar SCF convergido"; o de `si.scf.out`, o de `si.band.in`, o de uma pasta e
   o de dois itens não têm; acionar o item abre uma janela (espera `opened`) com o título e a barra de status esperados; acionar duas vezes
   o mesmo arquivo abre **duas** janelas, e mudar o raio, a cor de uma espécie ou o zoom numa não muda a outra; um input sem
   `ATOMIC_POSITIONS` (cópia em `tmp_path`) dá o toast e `failed`, nenhuma janela; fechar a janela principal fecha todas
   (`close_dialogs` True, lista vazia); fechar uma janela a tira da lista; a linha da vista aparece na janela de atalhos
   (`test_help.py`); `test_file_grid_menu.py` continua verde (o índice de "Abrir com" não muda para um arquivo comum).

### R5: Painel esquerdo no estilo do Lain

1. `ui/widgets/structure3d/panel.py:StructurePanel` (novo): `PanelHeader` "ESTRUTURA" e, numa `QScrollArea`, uma coluna de `Section`
   (`param_widgets.Section`, a mesma sanfona do "Ajuste do gráfico", com as variantes de QSS de lá), nesta ordem: "Átomo", ("Medidas",
   spec 44), "Exibição", "Espécies", "Célula". Abertas ao abrir a janela: "Átomo" e "Exibição"; o estado de cada uma é QSettings
   `structure3d/sections/<título>` (geral, não por janela). Largura mínima 260 px. Nenhum `QTabWidget`, nenhum `QSlider`, nenhum
   `setStyleSheet` embutido: todo campo numérico ou de escolha é `NoWheelSpinBox` / `NoWheelDoubleSpinBox` / `NoWheelComboBox`.
2. **Átomo.** Sem átomo: uma linha `text_meta` "Clique em um átomo para ver os dados." Com átomo: uma linha de título com o nome e o
   elemento ("O43 · Oxigênio") e as linhas `add_row`: "Espécie" (o rótulo do input), "Elemento" ("Oxigênio (O), Z = 8"), "Massa"
   ("15.999 u"), "Pseudopotencial", "Posição (Å)" e "Fracionária" (três números em fonte mono, texto selecionável), "Imagem" (só numa
   cópia deslocada: "(1, 0, 0)"), "Fixo (if_pos)" (só quando o input tem flags: "0 0 0"), "Magnetização inicial" (só quando há
   `starting_magnetization` da espécie), "Coordenação". Depois a tabela "Vizinhos ligados" com duas colunas, "Átomo" (`H70`, `H70(1,0,0)`)
   e "Distância (Å)" (4 casas), no máximo 12 linhas e "+N" abaixo quando há mais; clicar numa linha seleciona aquela cópia. Números com
   ponto decimal, como o resto da interface.
3. **Exibição.** "Estilo" (Bola e vareta / Vareta / Fio / Espaço cheio), "Raio" (0,20–2,50, passo 0,05, sufixo "×"), "Ligações" (caixa)
   e "Fator de ligação" (0,60–1,80, passo 0,05; desabilitado com as ligações desligadas), "Repetição" (três campos 1–5 numa linha, "a",
   "b", "c"), "Rótulos" (Nenhum / Símbolo / Número / Ambos), "Caixa da célula", "Eixos", "Perspectiva" (caixas) e "Fundo" (Escuro /
   Claro). A tecla P na vista atualiza a caixa "Perspectiva".
4. **Espécies.** Uma linha por espécie: `ColorButton` (cor Jmol ou a escolhida), o nome ("O · Oxigênio"; só o rótulo quando não há
   elemento) e a caixa "Visível"; um botão "Restaurar cores".
5. **Célula.** "a, b, c (Å)", "α, β, γ (°)", "Volume (Å³)", "a₁", "a₂", "a₃ (Å)", "ibrav", "nat", "Fórmula", "prefix", "calculation" e, só
   quando há avisos do leitor, uma linha "⚠ …" por aviso (quebra de linha, sem caixa de texto).
6. Todo campo só edita o `DisplayOptions` da janela e pede um redesenho; nenhum toca a câmera (R3).
7. **Testes** (`tests/test_structure3d_panel.py`, novo): as seções na ordem e com os títulos; nenhum `QTabWidget`/`QSlider` no painel e todos
   os campos `NoWheel*` (a roda sobre um campo não muda o valor, como `test_no_wheel.py`); selecionar o átomo 43 de
   `scf-kaolinite-slab-001-2x1x1.in` mostra "O43 · Oxigênio", e um Si fixo mostra "Fixo (if_pos)" = "0 0 0"; `ni.scf.in` mostra
   "Magnetização inicial" 0.8 e `si.scf.in` não tem a linha; clicar num vizinho seleciona a cópia; os valores de "Célula" de `si.scf.in`
   batem com `lattice_parameters`; fechar e reabrir uma janela mantém as seções abertas/fechadas; "Fator de ligação" desabilitado sem
   ligações.

## Fora de escopo

- Distância e ângulos: spec 44. O diedro e o botão "Usar imagem mais próxima" do exemplo ficam fora (a 44 decide o que entra).
- Saídas do pw.x (`.out`), geometria final e trajetória do relax, forças: outra spec (precisa de um leitor da célula da saída,
  `crystal axes`, que nenhum parser tem; relatório §2.1).
- OpenGL, densidade de carga (`.xsf`), isosuperfícies e zona de Brillouin: decisão do usuário (QPainter); relatório §9, fases 2 e 4.
- Exportar imagem (PNG/SVG) da vista: não pedido; o `render_image` do exemplo deixa o caminho aberto.
- Editar a estrutura (mover, apagar átomos): a janela só mostra.
- Lembrar as configurações de uma janela por arquivo ou entre sessões: o pedido é "cada janela as suas"; nada é gravado.
- As cores de `plot.atomos_colors` (cores das linhas da PDOS): a vista usa as cores Jmol do exemplo.
- Abrir a estrutura numa aba do workspace (relatório §7.3): o usuário pediu janela própria.
- Trocar `surface/elements.py` pelo `elements.py` novo: as duas regras ficam e um teste as compara (refatoração sem ganho agora).
- "Visualização 3D" em pastas, na seleção múltipla ou na paleta de comandos.

## Decisões assumidas (confirmar na revisão)

1. **Uma janela por clique, mesmo para o mesmo arquivo**, lendo ao pé da letra "para cada vez que abrir um scf … cria-se uma nova
   janela": dá para comparar duas vistas da mesma estrutura. Alternativa barata: trazer para a frente a janela que já mostra o arquivo.
2. **Janela sem pai**: entrada própria na barra de tarefas e não fica presa sobre a principal ("independente"). Fechar a principal fecha
   todas, sem perguntar (elas não têm o que salvar).
3. **Nada é gravado** por janela: cada uma abre com os padrões do exemplo e o fundo do tema do app daquele momento. Só o
   aberto/fechado das seções do painel é lembrado, como no painel de ajustes.
4. **Duplo clique não faz nada** além de dois cliques (antes resetava). Alternativa: centralizar no átomo sem mudar o zoom.
5. **Mudar o fator de ligação não reenquadra**; mudar a repetição continua reenquadrando (o bloco muda de tamanho).
6. **`scipy` declarado** em `pyproject.toml`: o código o importa direto (já vinha com o ASE). A alternativa é uma busca densa em blocos,
   mais lenta acima de ~1 000 átomos.
7. Um input de `relax`/`vc-relax` mostra a **geometria de entrada**, não a relaxada (a final vem com as saídas, fora de escopo).
8. As cores da cena são do renderer (paleta escura e clara), não tokens do tema; só o anel de foco usa o token `focus_ring`.
9. "Visualização 3D" fica no grupo do topo do menu, depois de "Resumo"; num input do pw.x ele é, na prática, o primeiro item.
10. O pacote se chama `core/structure3d/` (e `ui/widgets/structure3d/`) para não colidir com `core/qe/structure.py`.

## Notas de implementação

- Novos: `src/qe_studio/core/structure3d/{__init__,model,source,elements,bonds,replicate,camera,pick,options,geometry}.py`;
  `src/qe_studio/ui/structure3d_controller.py` (novo); `src/qe_studio/ui/widgets/structure3d/{__init__,window,canvas,renderer,overlay,panel}.py`
  (novos; e `bonds_paint.py`, novo, se o renderer passar de ~400 linhas); testes `tests/test_structure3d_{source,core,render,canvas,ui,panel}.py` e um
  helper `tests/structure3d_helpers.py` (novo: abrir uma janela com uma fixture, clicar num átomo pela posição projetada, girar).
- Alterados: `ui/widgets/context_menu.py` (sinal, `menu(structure=)`, `show`; 327 → ~340 linhas), `ui/main_window.py` (+1 linha, 449/450),
  `ui/shutdown.py` (`close_dialogs` e o passo "cancelar"), `ui/help_controller.py` (um provider), `pyproject.toml` e `uv.lock` (`scipy`),
  `tests/test_architecture.py` (`QT_FREE` com os módulos de `core/structure3d/`), `tests/test_properties.py` (R1.3).
- Ordem: R1 → R2 → R3 → R5 → R4 (o menu por último, quando a janela já existe).
- Limites: nenhum arquivo do exemplo passa de 400 linhas; o maior risco é o renderer com as ligações novas (separar em
  `bonds_paint.py`, novo). `ui/main_window.py` fica com 1 linha de folga: a 44 não pode tocá-lo.
- Desempenho: o quadrilátero com gradiente custa mais que a linha de hoje; meça com o teste `perf` do exemplo portado
  (`tests/test_perf_structure3d.py`, novo, marca `perf`, 500 / 2 000 / 5 000 átomos) e escreva os números aqui. Orçamento: 2 000 átomos em
  bola e vareta ≤ 80 ms por quadro (o exemplo mede 43,7 ms com linhas), e o modo rascunho continua abaixo de 50 ms.
  **Medido** (`uv run pytest -m perf -s tests/test_perf_structure3d.py`, 13/10/2026, offscreen, 1000 × 800, bola e vareta,
  mediana de 5 quadros; grafeno empilhado, 1,5 ligação por átomo):

  | átomos | primitivas | cheio | rascunho | sem ligações |
  |---:|---:|---:|---:|---:|
  | 500 | 2 315 | 16,5 ms | 8,0 ms | 5,0 ms |
  | 2 000 | 8 615 | 50,6 ms | 29,0 ms | 14,0 ms |
  | 5 000 | 21 215 | 110,5 ms | 75,5 ms | 29,9 ms |

  Dentro do orçamento (2 000: 80 / 50 ms). A primeira versão criava um `QLinearGradient` com `setStops` por metade (113 ms
  em 2 000 átomos); o gradiente agora é um por espécie, movido às bordas de cada metade antes do `setBrush`.
- Documentação ao implementar: `CLAUDE.md` (seção nova "Visualização 3D (spec 43)": pacote, janela sem pai e várias instâncias,
  `close_dialogs`, câmera que só muda pelos gestos; nota de testes com `structure3d_helpers`), `README.md` (a funcionalidade).

## Decisões na implementação

1. **`si.band.in` tem o item.** O teste de R4.6 o listava entre os que não têm, mas é um input do **pw.x** (`calculation =
   'bands'`), e R1/R4.1 pedem qualquer `calculation`. O caso "input do bands.x" é `si_bands/bands.in`
   (`test_structure3d_ui.py`). Pelo mesmo motivo `test_file_grid_menu.py` mudou: `03_bands/bands.in` do `demo_project` é o
   `al.band.in` (pw.x) e `01_relax/si.rel.in` é um relax: os dois ganham "Visualização 3D" no topo; o teste do menu exato
   usa `bands.dat.gnu`.
2. **`ui/main_window.py` em 450 linhas**, não 449: a linha do controlador precisa também do seu `import`. O limite é ≤ 450
   (`PER_FILE_LIMIT`), e a spec 44 não toca o arquivo.
3. **Vareta:** todo átomo ganha a bolinha de 1,3 ρ (com gradiente fora do rascunho); no exemplo só os átomos soltos a
   tinham, e as varetas com ponta redonda cobriam as juntas, o que o quadrilátero sem tampa não faz.
4. **`scipy.spatial.KDTree`** no lugar de `cKDTree`: o pyright não acha `cKDTree` nos stubs; o `KDTree` atual é a mesma
   implementação em C (o teste denso × árvore continua).
5. **Duplo clique no teste:** `QTest.mouseDClick` do PyQt6 manda só o evento de duplo clique (sem os press/release que a
   plataforma manda); o teste reproduz a sequência real (clique, duplo clique, soltar). `mouseDoubleClickEvent` chama
   `mousePressEvent`.
6. **`Section.add_row` devolve o rótulo** (antes `None`), para as linhas opcionais do "Átomo" se esconderem com o valor.
7. **Fixo (if_pos)** de um átomo sem flags num input que escreve flags em outros mostra `1 1 1` (o padrão do pw.x).

## Critérios de aceite e testes

- [x] Goldens e regressões de figuras passam sem regenerar (nada de `core/calculations` muda); `test_file_grid_menu.py` e `test_help.py`
      continuam verdes.
- [x] Todo input do pw.x das fixtures abre uma `Structure` igual à de `crystal_from_editor`, com flags, espécies e magnetização
      (`test_structure3d_source.py`, novo); erros dão a frase em português.
- [x] O núcleo do exemplo, portado, passa os testes portados com as fixtures do Lain (`test_structure3d_core.py`, novo) e a propriedade de
      translação das ligações (`test_properties.py`).
- [x] O centro de uma esfera tem o mesmo pixel com e sem ligações (`test_structure3d_render.py`, novo; falha com o renderer do exemplo).
- [x] Uma ligação mostra ≥ 3 tons através da largura, com as bordas mais escuras, em três orientações (`test_structure3d_render.py`, novo).
- [x] Duplo clique num átomo e mudança do fator de ligação não mexem em zoom, pan nem rotação (`test_structure3d_canvas.py`, novo; falham no
      exemplo); R e "Resetar vista" resetam; a repetição reenquadra.
- [x] "Visualização 3D" aparece só em inputs do pw.x e abre uma janela nova a cada clique, com configurações independentes; erro de leitura
      dá toast e nenhuma janela; fechar a principal fecha todas (`test_structure3d_ui.py`, novo).
- [x] O painel tem as seções sanfona do Lain, campos `NoWheel*`, e mostra átomo, vizinhos, espécies e célula como em R5
      (`test_structure3d_panel.py`, novo).
- [x] `test_main_window_import_skips_ase` verde; `FS_ALLOWED` sem chamada nova; `ui/main_window.py` ≤ 450.
- [x] Medidas de desempenho anotadas (`-m perf -s`) dentro do orçamento das notas.
- [ ] Passo manual de aceite: o usuário abre dois SCFs reais, gira, dá zoom, clica em átomos (também duas vezes seguidas) e confirma que o
      zoom fica, que as ligações parecem cilindros saindo da superfície das esferas e que o painel esquerdo ficou bom.
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
