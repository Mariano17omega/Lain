# Relatório: visualização 3D da estrutura atômica (estilo XCrySDen)

Data: 2026-10-13 · Base: `main` @ a340224 · Escopo: levantamento de opções para uma aba 3D da estrutura (a partir
do SCF), com painel de informações à esquerda, medidas e repetição de células. **Nenhum arquivo do repositório
foi alterado**; este documento é o único produto.

**Método.** Leitura dirigida do código (§2), quatro provas descartáveis rodadas na máquina do usuário (scripts em
diretório temporário, fora do repositório), consulta aos metadados do PyPI e leitura do código-fonte das wheels de
vispy 0.17.0, pyqtgraph 0.14.0, pyvista 0.49.1 e pyvistaqt 0.13.1. Cada afirmação diz como foi obtida:

- **Medido**: número obtido por execução nesta sessão (§4).
- **Verificado**: lido no código instalado ou nas wheels baixadas.
- **Leitura**: lido no código do Lain, ou conhecimento geral da biblioteca, não reproduzido aqui.
- **Verificar**: depende de algo que não foi possível checar (não instalei VTK, não consultei a documentação do
  XCrySDen). A lista final está no Apêndice B.

Máquina das medições: Linux 6.17 (X11), NVIDIA RTX 3050 Laptop (driver 580, OpenGL 4.6), Python 3.11.14,
PyQt6 6.11.0 / Qt 6.11.2, matplotlib 3.11.2, ASE 3.29.0. Em outra GPU ou driver os números mudam; a ordem de
grandeza e as conclusões qualitativas não deveriam.

Escala de esforço: **P** = horas, **M** ≈ 1 dia, **G** = vários dias.

---

## 0. Resumo

**Recomendação.** Construir a visão em **PyQt6 puro, sem dependência nova**, em duas camadas:

1. **Núcleo sem Qt em `core/`** (cena, ligações, medidas, repetição de células, câmera e seleção por raio). É a
   maior parte do trabalho, é testável sem GL e serve a qualquer renderer.
2. **Renderer OpenGL próprio** (`QOpenGLWidget`, esferas por *impostor* instanciadas) como principal, com um
   **renderer QPainter** como reserva para onde não há GL (VM, X remoto) e como único que roda nos testes
   `offscreen`.

PyVista/VTK passa a ser a melhor escolha **somente** se a meta incluir isosuperfícies ou volume (a densidade de
carga em `.xsf` que "Criar cálculo" já gera, specs 29–30). Custa ~140 MB de wheel e mais um grupo de problemas
(§3.G, §8).

| # | Opção | Dependência nova | Desempenho medido | Roda no teste `offscreen` | Esforço | Veredito |
|---|---|---|---|---|---|---|
| A | Programa externo (XCrySDen, VESTA, `ase gui`) | nenhuma | — | — | P | Complemento barato, não atende o pedido |
| B | matplotlib `mplot3d` | nenhuma | 66 ms com 2 000 átomos | sim | M | Descartar (qualidade) |
| C | `QPainter` (projeção própria em numpy) | nenhuma | 44–65 ms com 2 000; 215–330 ms com 10 000 | sim | M | Bom MVP e reserva |
| D | `QOpenGLWidget` próprio (PyQt6) | nenhuma | ≈ 6 ms de 2 000 a 100 000; 41 ms com 1 M | **não** | G | **Recomendado (principal)** |
| E | `pyqtgraph.opengl` | PyOpenGL + pyqtgraph (~5 MB) | não medido | não | M | Descartar |
| F | `vispy` | vispy + freetype-py + hsluv (~3 MB) | não medido | não | M | Alternativa razoável a D |
| G | PyVista + pyvistaqt + VTK | **vtk 140 MB** + pyvista, pyvistaqt, qtpy | não medido | não (sem OSMesa/xvfb) | M | Só se houver isosuperfície/volume |
| H | Qt Quick 3D (QML) | nenhuma (já instalado) | não medido | não | G | Descartar (§3.H) |
| I | QtWebEngine + 3Dmol.js / NGL | PyQt6-WebEngine **+116 MB** + JS | não medido | frágil | M | Descartar |

---

## 1. O que se quer

Da mensagem do usuário:

1. Uma **aba do lado direito** (o workspace) com a estrutura em 3D, a partir do SCF, parecida com o XCrySDen.
2. **Zoom** e rotação.
3. **Clicar em um átomo** e ver as informações dele em um painel do **lado esquerdo**.
4. **Distância e ângulo** entre átomos.
5. **Repetição de células**, só para visualização.

Interpretação adotada: a "aba da direita" é uma aba do `Workspace` (como "Resumo" ou um gráfico) e a "aba da
esquerda" é uma página do painel esquerdo, ao lado de "Árvore" e "Ajuste do gráfico" (§2.2). A alternativa, um
painel dentro da própria aba (um `QSplitter` interno), está discutida em §7.3.

"A partir do SCF" é lido como: o **input** do SCF (`.in`) ou a **saída** do pw.x. O código é o mesmo para qualquer
input ou saída do pw.x (relax, vc-relax, bands…), então vale generalizar de saída.

---

## 2. O que o projeto já tem

### 2.1 Dados da estrutura

| Fonte | Onde | O que dá | Lacuna |
|---|---|---|---|
| Input do pw.x | `core/qe/lattice.py:196` `crystal_from_editor` → `Crystal(cell Å, labels, frac)`; `core/calc_create/scf_info.py` `ScfInfo.crystal` / `read_scf` (worker) | Célula de **qualquer `ibrav`** (port do `latgen` do QE 7.1) e de `ibrav = 0`; posições em `crystal`, `alat`, `bohr`, `angstrom` | `crystal_sg` não suportado (`StructureError`) |
| `if_pos` | `core/calc_create/surface/model.py:24` `Model(cell, labels, frac, flags)`, `model_of(scf)` | Flags 0/1 dos átomos fixos | — |
| Elemento e raio | `core/calc_create/surface/elements.py` `element_of`, `covalent_radius` (regra `label_to_symbol` do ASE; `ase.data` importado só no primeiro uso, ~8 ms) | `Fe1`, `Fe_up` → Fe; raio covalente em Å | Levanta `SurfaceError` sem elemento; mora no pacote `surface` |
| Ligações e imagens | `core/calc_create/surface/geometry.py` `pair_images`, `vacuum_gaps`, `skewed` | Imagens −1…1 sobre as frações como escritas | Só −1…1 (§8, P6) |
| Saída do pw.x | `core/qe/structure.py:54` `read_sites` | Posições cartesianas (Å) dos átomos, em streaming | **Sem a célula** (só `alat`) |
| Geometria final | `core/qe/final_structure.py` `read_final_structure` | `Begin/End final coordinates`, com `if_pos` e, no vc-relax, `CELL_PARAMETERS` | Linhas como impressas, sem conversão de unidade |
| Célula por passo (vc-relax) | `core/qe/relax.py` `RelaxStep.cell` | Célula de cada passo BFGS | `parse_relax` **não guarda posições** por passo |
| Célula da saída | cabeçalho do pw.x: `crystal axes: (cart. coord. in units of alat)` (verificado em `tests/fixtures/si_bands/si.scf.out:58`) | `a(1)…a(3)` em unidades de `alat` | **Nenhum parser lê** |
| ASE | `core/qe/pw_output.py:216` `read_structure` | `ase.Atoms` da saída | Falha de propósito em fixtures (`al.scf.out`); não confiável |

Conclusão: o **input** já entrega tudo (célula, posições, espécies, flags). A **saída** exige um parser novo
pequeno (`crystal axes` + `alat` + `read_sites`). Trajetória de relaxamento exige estender um parser (§6, Fase 3).

### 2.2 Interface

- `ui/main_window.py` (`_build`): o painel esquerdo é um `QStackedWidget` com a árvore (índice 0) e o
  `ParamsPanel` (índice 1). O `splitter` guarda `left | grade | workspace`.
- `ui/layout_controller.py:18` `PARAMS_PAGE = 1`; `set_left_mode(mode)` (linha 89) só conhece `"tree"` e
  `"params"`; `plot_shown()` compara o índice com `PARAMS_PAGE`. O botão do `ActivityBar`
  (`ui/widgets/bars.py:148`) reflete o modo.
- `ui/widgets/plot_params.py:ParamsPanel`: **um corpo por plot aberto** num `QStackedWidget` (`bind(session)`,
  `discard(key)` quando a aba fecha). É o padrão a copiar para um painel "Estrutura" por aba 3D.
- `ui/widgets/workspace.py:193` `open_summary(path)`: o padrão de uma aba que não é arquivo de texto
  (`Workspace.add(key, widget, title, icon)`, chave `summary:<path>`; uma aba aberta é mostrada de novo).
  As abas são **movíveis** (`setMovable(True)`, linha 113: relevante para o contexto GL, §8 P2).
- `ui/widgets/context_menu.py:108` `file_actions_of` + `menu(...)`: "Plotar" e "Resumo" entram por aqui, a partir
  do sniff em cache (a GUI nunca lê arquivo).
- `ui/widgets/atom_table.py:AtomTable(rows, selected, unit, count_format)` (spec 30): tabela com caixa, #,
  elemento e coordenadas, "Marcar todos / Inverter / Só espécie ▸". **Reaproveitável** como lista de átomos do
  painel, sincronizada com a seleção 3D.
- `ui/actions.py:ACTIONS`, `ui/shutdown.py`, `ui/focus_controller.py`, `ui/theme/` (tokens em `dark.yaml` e
  `light.yaml`, teste de contraste WCAG).

### 2.3 Regras do projeto que moldam a solução

| Regra | Efeito aqui |
|---|---|
| `core/` não importa `qe_studio.ui` e não usa PyQt6 (só `sync/_process`, `sync/controller`, `sync/monitor`, `tasks`) | Câmera, seleção por raio, medidas e ligações em **numpy**, sem Qt |
| `ui/` não lê disco; `test_architecture.FS_ALLOWED` só diminui | Carregar estrutura em `run_task` (worker); nenhum `exists()`/`stat()` na GUI |
| Nenhum `.py` com mais de 500 linhas | Renderer, câmera, painel e controlador em módulos separados |
| `test_perf_detection.py`: `ase` e `jinja2` não carregam no import da janela (spec 14) | Qualquer biblioteca 3D só no primeiro uso, com teste equivalente |
| `tests/conftest.py` força `QT_QPA_PLATFORM=offscreen` | **`QOpenGLWidget` não renderiza ali** (§4, §8 P1) |
| Strings de usuário em português; identificadores internos `qe_studio` | Novos nomes de QSettings sob `qe_studio` (`structure/*`) |
| "Nenhum arquivo de `ui/` conhece um módulo de cálculo" | A visão não pode ter `kind == "scf"`; recebe uma estrutura |
| Dependências novas são raras (jinja2 entrou na spec 25; pymatgen saiu na 27-2) | Preferir zero dependências novas |

---

## 3. Opções de implementação

Todas as opções compartilham o mesmo núcleo (§7). O que muda é o renderer e o que ele traz pronto.

### A. Programa externo (XCrySDen, VESTA, `ase gui`)

**O que é.** Não desenhar nada: abrir o arquivo no programa que o usuário já usa. O Lain já tem "Abrir com"
(`core/desktop_apps.py`, spec 5), que lista os programas registrados para o tipo do arquivo. XCrySDen abre input e
saída do pw.x por linha de comando (`--pwi`, `--pwo`; de memória, **Verificar**). `ase gui` precisa de `tkinter`.

- **Prós**: custo mínimo (item de menu "Abrir no XCrySDen" quando o executável existe, ~30 linhas); zero risco.
- **Contras**: não é uma aba, não tem o painel esquerdo, não lê as espécies do Lain, não une a medida ao resto
  do app; depende do que está instalado.
- **Veredito**: **fazer como Fase 0**, mas não substitui o pedido.

### B. matplotlib `mplot3d`

**O que é.** `Axes3D` com `scatter` (átomos) e `Line3DCollection` (ligações), no `FigureCanvasQTAgg`. matplotlib
já é dependência, e o app já embute canvases.

- **Prós**: zero dependência; roda no teste `offscreen`; exporta PNG/SVG/PDF do jeito do resto do app.
- **Contras**:
  - Sem z-buffer: cada coleção é ordenada por profundidade média; **ligações atravessam átomos** e o desenho
    muda conforme a rotação (limitação conhecida do `mplot3d`, Leitura).
  - Marcadores planos, sem sombreamento; o tamanho não acompanha a perspectiva.
  - Cada rotação é um redesenho completo em Python. **Medido** (só `canvas.draw()` em Agg, átomos + 1,5 ligação
    por átomo): 100 → 23 ms, 500 → 32 ms, 2 000 → 66 ms, 5 000 → 135 ms. Em tela soma-se a cópia para o Qt.
  - Seleção (`pick_event`) em `Path3DCollection` é imprecisa; sem rótulos 3D reais; zoom é `set_xlim`, não câmera.
- **Veredito**: **descartar** como visão interativa. Serve, no máximo, como figura estática exportada.

### C. `QPainter` com projeção própria em numpy

**O que é.** Um `QWidget` que projeta as posições com uma matriz de câmera (numpy), ordena por profundidade
(algoritmo do pintor) e desenha círculos com gradiente radial e linhas/capas para as ligações.

- **Prós**:
  - Zero dependência, zero GL: roda em qualquer ambiente, **inclusive nos testes `offscreen`** (`widget.grab()`
    devolve a imagem; dá para comparar pixels).
  - Seleção trivial (a ordem de pintura já é a de profundidade; teste de proximidade em 2D).
  - **Exportação vetorial** (SVG via `QSvgGenerator`, PDF via `QPdfWriter`) com o mesmo código de desenho: algo
    que o OpenGL não dá.
  - Rótulos e medidas com o mesmo `QPainter`, com a fonte e o tema do app.
- **Contras**:
  - Algoritmo do pintor falha quando **esferas se interpenetram** (modo espaço-cheio com raios de van der Waals,
    ou átomos muito próximos); ligações têm de ser quebradas ao meio para ordenar certo.
  - Desempenho linear: **medido** (átomos + 1,5 ligação por átomo como linhas; 1000×800 px; `Antialiasing`):

    | átomos | cor lisa | gradiente radial |
    |---:|---:|---:|
    | 500 | 14 ms | 18 ms |
    | 2 000 | 44 ms | 65 ms |
    | 5 000 | 109 ms | 171 ms |
    | 10 000 | 215 ms | 333 ms |
    | 20 000 | 437 ms | 658 ms |

    A projeção em numpy custa < 1 ms; o tempo é do `QPainter`. Até ~2 000 átomos a rotação fica fluida (15–20 fps);
    acima disso exige modo "rascunho" durante o arrasto (sem ligações, sem gradiente).
- **Veredito**: **bom MVP e reserva obrigatória** (§7.4). Insuficiente sozinho para espaço-cheio e para cenas
  de dezenas de milhares de átomos (célula 5×5×5 de um slab).

### D. `QOpenGLWidget` próprio com `PyQt6.QtOpenGL` (sem PyOpenGL)

**O que é.** Um `QOpenGLWidget` com contexto OpenGL 4.1 core, um VAO, um buffer por instância
(`centro.xyz, raio, cor`) e **esferas como *impostors***: um quad de 4 vértices por átomo (`glDrawArraysInstanced`),
com o fragment shader calculando a normal da esfera e escrevendo `gl_FragDepth`. Ligações como cilindros-impostor
ou quads. Seleção **na CPU** por raio–esfera vetorizado (numpy), sem leitura de volta da GPU. Rótulos por um
`QWidget` transparente sobreposto ou `QPainter` em `paintGL`. PNG por `grabFramebuffer()`.

**Viabilidade verificada** (Apêndice A): PyQt6 6.11 expõe `QOpenGLFunctions_2_0`, `_2_1` e `_4_1_Core` e
`QOpenGLVersionFunctionsFactory`; `glDrawArraysInstanced` e `glVertexAttribDivisor` existem; `QOpenGLContext` **não**
tem `functions()` em PyQt6 (usar a fábrica). Shaders por `QOpenGLShaderProgram`, buffers por `QOpenGLBuffer`. Uma
prova de conceito de ~80 linhas compilou, linkou e desenhou. Medido: 2 000 e 100 000 esferas a ≈ 6,4 ms por quadro
(constante: o piso parece ser sincronização com o compositor, não o desenho), 1 000 000 a 41 ms.

- **Prós**:
  - **Nenhuma dependência nova**; combina com a política do projeto.
  - Desempenho de sobra (100 mil átomos a ~130 quadros/s medidos) e esferas **corretas** (interpenetração, sombreamento por
    pixel), o que cobre espaço-cheio e repetições grandes.
  - Controle total: câmera estilo XCrySDen, perspectiva/ortográfica, cortes, cores por tema.
  - Evita PyOpenGL, que tem problemas de plataforma sob Wayland/EGL (`PYOPENGL_PLATFORM`; Leitura).
- **Contras**:
  - É código nosso: ~600–900 linhas de Python e GLSL (renderer, câmera, shaders, ligações). Nada vem pronto
    (rótulos, medidas, eixos, caixa da célula).
  - **Não roda no teste `offscreen`** (§4, §8 P1): precisa de renderer de reserva e/ou `xvfb` + Mesa no CI.
  - Problemas típicos de GL: contexto recriado ao reparentar a aba (abas movíveis), janela inteira composta por
    textura, falta de GL em VM/X remoto (§8 P2–P4).
  - Só OpenGL 2.0/2.1/4.1 core estão expostos; 4.1 core é o que Mesa, NVIDIA e Intel dão no Linux e o teto do macOS.
- **Veredito**: **recomendado como renderer principal**, atrás de uma interface (`SceneRenderer`) para poder
  trocar por F ou G sem mexer no resto.

### E. `pyqtgraph.opengl` (`GLViewWidget`, PyOpenGL)

**O que é.** Parte 3D do pyqtgraph: `GLViewWidget`, `GLMeshItem`, `GLScatterPlotItem`, `GLLinePlotItem`,
`GLTextItem` (verificado na wheel).

- **Prós**: pequeno (1,9 MB + PyOpenGL 3,2 MB); API simples; câmera orbital pronta; `GLTextItem` para rótulos;
  `MeshData.sphere(rows, cols)` gera a malha de uma esfera.
- **Contras**:
  - `pyqtgraph.opengl` importa `OpenGL.GL` (**PyOpenGL**) no topo de `GLViewWidget.py` (verificado) e **não** declara
    PyOpenGL como dependência na metadata (só `numpy` e `colorama`): é um extra a instalar à parte.
  - Uma esfera = um `GLMeshItem` (draw call por átomo): lento acima de poucas centenas. A alternativa
    `GLScatterPlotItem` (`pxMode=False`) desenha *sprites* planos, não esferas (Leitura).
  - Avisa que é "principalmente testado contra OpenGL Desktop" e exige GL ≥ 2.1 (verificado); usa pipeline legado.
  - Sem seleção por objeto pronta para esse caso; câmera e medidas seriam nossas de qualquer jeito.
  - Mesmos problemas de teste/ambiente de D, mais PyOpenGL sob Wayland.
- **Veredito**: **descartar**: troca a dependência nova por uma de manutenção incerta e rende menos que D.

### F. `vispy`

**O que é.** Biblioteca de visualização científica sobre OpenGL (`vispy.scene`). O backend `pyqt6` usa
`QOpenGLWidget` (verificado em `vispy/app/backends/_qt.py`), e `SceneCanvas.native` é um `QWidget` embutível.

- **Prós**:
  - Já traz o que D escreveria: `visuals.Markers(spherical=True)` (esferas sombreadas; verificado), `Sphere`,
    `InstancedMesh`, `Tube`, `Line`, `Text`, `XYZAxis`, `Isosurface`, `Volume` (verificado na lista de visuals).
  - Câmeras `Turntable`/`Arcball`; seleção por pixel (`canvas.visual_at(pos)`, `canvas.render()`; verificado).
  - Pequeno (2,2 MB wheel; dependências `freetype-py`, `hsluv`, `kiwisolver`, `numpy`, `packaging`).
  - Tem caminho para isosuperfície/volume (`Isosurface`, `Volume`) sem VTK.
- **Contras**:
  - Abstração `gloo`/GLIR própria: depurar sombreamento ou profundidade exige aprender vispy.
  - O `Markers` esférico é um *sprite* com profundidade ajustada, não uma esfera geométrica; a qualidade
    em primeiros planos grandes e a interpenetração precisam de teste visual (**Verificar**).
  - Projeto mantido por comunidade pequena (a 0.17.0 saiu em 2026-09, ativo, mas a base de usuários é menor
    que a do VTK).
  - Mesmos problemas de teste e ambiente de D (§8 P1, P4).
  - Nada foi medido: não instalei.
- **Veredito**: **alternativa válida a D** se se preferir escrever menos GLSL. Pior encaixe em uma interface
  `SceneRenderer` pequena, porque o vispy quer ser dono da cena.

### G. PyVista + pyvistaqt (VTK)

**O que é.** VTK é o motor científico de referência. PyVista é a API pythônica; `pyvistaqt.QtInteractor` é um
widget Qt. Esferas por `glyph`/`render_points_as_spheres`, seleção por `enable_point_picking`, medidas por
widgets do VTK (Leitura), `contour` para isosuperfícies.

- **Prós**:
  - O conjunto de recursos mais completo **sem escrever renderer**: picking, rótulos de ponto, eixos, widgets de
    medida (distância/ângulo; **Verificar** nome e comportamento), `screenshot`, isosuperfície e volume.
  - É o caminho natural se a densidade de carga (`.xsf` de "Criar cálculo") for entrar: marching cubes e
    volume rendering prontos.
  - Maduro, muito usado em ciência.
- **Contras**:
  - **Peso**: wheel do `vtk` 139,6 MB (cp311 manylinux, PyPI hoje); PyQt6 já ocupa 261 MB instalados, então é
    um aumento grande para um app de desktop pequeno. Descompactado é bem maior (**Verificar**, não medi).
  - **Pins frágeis**: `pyvista` exige `vtk>=9.3.1,<9.8` e `!=9.4.0`, `!=9.4.1` (verificado); `pyvistaqt` exige
    `qtpy` e escolhe a binding por ambiente (`QT_API`), uma camada extra; Python novo costuma ter wheel de VTK
    mais tarde.
  - Quatro pacotes novos de peso diferente (`vtk`, `pyvista`, `pyvistaqt`, `qtpy`) + `scooby`, `pooch`,
    `cyclopts`, `pyvista-validation` (verificado na metadata).
  - Teclado/mouse e aparência VTK (estilo de interação, fontes) fora do QSS do app; o tema não chega nele.
  - Teste `offscreen`: VTK precisa de contexto GL (X, EGL ou OSMesa: **Verificar** que wheel serve ao CI).
  - Tempo de importação do VTK/pyvista não medido (**Verificar**); tem de ser tardio como o `ase`.
  - Identidade do átomo: o picking devolve ids de ponto/célula; mapear para (átomo, imagem) é código nosso.
- **Veredito**: **só com isosuperfície/volume no escopo**. Para esferas, rótulos e medidas, o ganho sobre D não
  paga o peso.

### H. Qt Quick 3D (QML)

**O que é.** Cena 3D declarativa do Qt (`View3D`, `Model { source: "#Sphere" }`, PBR, controlador orbital),
dentro de um `QQuickWidget`. `PyQt6.QtQuick3D` já está instalado (verificado, sem pip).

- **Contras decisivos**:
  - O binding do PyQt6 6.11 expõe só `QQuick3D`, `QQuick3DGeometry`, `QQuick3DObject`, `QQuick3DTextureData`
    (verificado): **sem `QQuick3DInstancing`**. Instanciar por QML (`InstanceList`) cria um objeto QML por átomo;
    uma malha única custom (`QQuick3DGeometry`) obriga a escrever a seleção por conta própria.
  - O projeto não tem QML nem `QQuickWidget`; o tema (QSS) não alcança a cena; arquivos `.qml` novos como
    recurso.
  - Backend de software do Quick não suporta Quick3D (Leitura): sem teste offscreen.
- **Prós**: sem dependência pip; RHI funciona em Vulkan/Metal/D3D além de GL; materiais e luzes PBR.
- **Veredito**: **descartar**: custo de um segundo toolkit sem o ganho esperado.

### I. QtWebEngine + 3Dmol.js / NGL

**O que é.** Um `QWebEngineView` carregando um visualizador molecular em JavaScript, empacotado localmente, e
`QWebChannel` para ligar ao Python.

- **Prós**: 3Dmol.js já traz rótulos, medidas, célula unitária, repetição e isosuperfícies de cubo; seleção e
  estilos prontos.
- **Contras**: `PyQt6-WebEngine-Qt6` pesa **116,3 MB** (PyPI) e traz um Chromium; dois processos extras e
  centenas de MB de RAM; sandbox do Chromium em contêineres/root; encerramento limpo da página antes do
  `QApplication` (o Lain usa `os._exit` quando há tarefas vivas); dois mundos (JSON entre Python e JS) para
  mostrar `if_pos`, magnetização, Hubbard etc.; a aba não herda o tema; testes frágeis. Licença do JS a
  conferir (BSD-3 de memória).
- **Veredito**: **descartar**.

### J. Outras, não adequadas

| Biblioteca | Por quê |
|---|---|
| Qt3D (`PyQt6-3D`, 1 MB + libs) | Em manutenção; a Qt recomenda Quick 3D; instancing limitado (Leitura) |
| Open3D | Wheel de 400,8 MB; janela própria, integração com Qt fraca |
| Mayavi | Camada traits + VTK; suporte a PyQt6 historicamente atrasado |
| moderngl | Boa para GL sem Qt; dentro de um `QOpenGLWidget` é D com uma dependência a mais |
| pygfx / wgpu-py | Jovens (wgpu 0.32), WebGPU/Vulkan; ainda pouco convencionais para um app científico de desktop |
| nglview, py3Dmol, k3d, pythreejs | Feitos para Jupyter; só rodariam via WebEngine (I) |
| `ase.visualize.plot` | matplotlib 2D, não interativo |

Licenças: o projeto já é PyQt6 (GPLv3/comercial); VTK, PyVista, vispy, pyqtgraph, PyOpenGL são BSD/MIT
(Leitura). Nenhuma das opções cria conflito novo.

---

## 4. Medições

Scripts descartáveis (não estão no repositório). Máquina e versões no cabeçalho.

### 4.1 Desenho por quadro

| Teste | Átomos | Tempo por quadro |
|---|---:|---:|
| QPainter, cor lisa + ligações | 500 / 2 000 / 5 000 / 10 000 / 20 000 | 14 / 44 / 109 / 215 / 437 ms |
| QPainter, gradiente radial + ligações | 500 / 2 000 / 5 000 / 10 000 / 20 000 | 18 / 65 / 171 / 333 / 658 ms |
| matplotlib `mplot3d` (Agg, `draw()`) | 100 / 500 / 2 000 / 5 000 | 23 / 32 / 66 / 135 ms |
| OpenGL 4.1 core, impostors instanciados (PyQt6) | 2 000 / 100 000 / 1 000 000 | 6,4 / 6,3 / 40,9 ms |

A linha OpenGL é o tempo de `paintGL` com `glFinish()`, 1000×800, MSAA 4×, janela real em X11. É sem ligações e
sem seleção. O valor de 6,4 ms para 2 000 e 100 000 átomos indica que o piso vem de algo fixo (sincronização com o
compositor), não do número de átomos.

### 4.2 `QOpenGLWidget` na plataforma `offscreen` (a do `conftest.py`)

| Situação | Resultado |
|---|---|
| `QT_QPA_PLATFORM=offscreen` com `DISPLAY` | `QOpenGLWidget is not supported on this platform.` / `No fbo, cannot render`; contexto 2.0 sem perfil |
| `offscreen` **sem** `DISPLAY` (CI) | `QOpenGLWidget: Failed to create context`; `grabFramebuffer()` devolve imagem **0×0** |
| `offscreen` sem `DISPLAY` + `LIBGL_ALWAYS_SOFTWARE=1` | O mesmo |
| `xcb` com a GPU real | Contexto 4.6 válido, `grab` 200×200 |

Ou seja, **nenhum teste de widget GL passa na configuração atual do projeto**.

### 4.3 Custo de importar o que o núcleo usaria

| Import | Tempo |
|---|---:|
| `ase.data` | 0,08 s |
| `ase.neighborlist` + `ase.geometry` + `ase.data` | 0,29 s |

`scipy` 1.17.1 está instalado, mas só como dependência transitiva do ASE (`Requires-Dist: scipy>=1.8.1`, verificado;
não declarada no `pyproject.toml` do Lain).

### 4.4 Pacotes (PyPI, wheel cp311 manylinux x86_64, 2026-10-13)

| Pacote | Versão | Wheel |
|---|---|---:|
| vtk | 9.7.1 | 139,6 MB |
| pyvista / pyvistaqt | 0.49.1 / 0.13.1 | 2,7 MB / 0,1 MB |
| pyqtgraph / PyOpenGL | 0.14.0 / 3.1.10 | 1,9 MB / 3,2 MB |
| vispy | 0.17.0 | 2,2 MB |
| PyQt6-WebEngine + PyQt6-WebEngine-Qt6 | 6.11.0 / 6.11.2 | 0,3 MB + 116,3 MB |
| PyQt6-3D | 6.11.0 | 1,0 MB (+ libs) |
| open3d | 0.20.0 | 400,8 MB |
| moderngl / pygfx / wgpu | 5.13.0 / 0.17.0 / 0.32.0 | 0,3 / 1,2 / 3,5 MB |

Instalados hoje no `.venv`: PyQt6 261 MB, matplotlib 30 MB, numpy 35 MB, ase 15 MB.

---

## 5. Comparação (critérios do projeto)

| Critério | B mplot3d | C QPainter | D GL próprio | E pyqtgraph | F vispy | G PyVista | H Quick 3D | I Web |
|---|---|---|---|---|---|---|---|---|
| Dependência nova | não | não | **não** | sim | sim | **sim, 140 MB** | não | **sim, 116 MB** |
| Esferas corretas (interpenetração) | não | não | **sim** | sim (malha) | quase | sim | sim | sim |
| Escala (átomos fluidos) | ~2 mil | ~2 mil | **100 mil+** | ~300 | 100 mil (esperado) | 100 mil+ | ~1 mil | ~10 mil |
| Teste `offscreen` | sim | **sim** | não | não | não | não | não | frágil |
| Exportação vetorial | sim | **sim** | não | não | não | parcial | não | não |
| Isosuperfície/volume | não | não | a escrever | não | sim | **sim** | não | sim |
| Tema do app (QSS) | parcial | **sim** | via tokens | parcial | parcial | não | não | não |
| Código nosso | pouco | médio | **muito** | médio | médio | pouco | médio | médio |
| Risco de manutenção | baixo | baixo | baixo | médio | médio | médio | médio | alto |

---

## 6. Funcionalidades possíveis

A coluna "XCrySDen" é de memória; **não consultei a documentação** nesta sessão. As fases estão no §9.

| Funcionalidade | XCrySDen | Dados / como | Fase |
|---|---|---|---|
| Rotacionar (arrastar), mover (botão do meio/Shift), zoom (roda) com foco no ponteiro, resetar | sim | Câmera arcball/orbital em numpy | 1 |
| Vistas ao longo de a, b, c e de x, y, z; perspectiva ⇄ ortográfica | parcial | Matrizes fixas de câmera | 1 |
| Estilos: bola-e-vareta, vareta, fio, espaço-cheio | sim | Raio = fator × raio covalente (`elements.covalent_radius`) ou van der Waals (`ase.data.vdw_radii`) | 1 |
| Cores por elemento (Jmol/CPK) e cor por espécie editável | sim | `ase.data.colors.jmol_colors` (110 entradas); reaproveitar `plot.atomos_colors` do Lain | 1 |
| Ligações automáticas por soma de raios covalentes × fator ajustável | sim | `core/structure/bonds.py` (§8 P9) | 1 |
| Caixa da célula, setas de a, b, c, triedro de eixos | sim | `Crystal.cell` | 1 |
| **Clique no átomo → painel esquerdo** com: nº (1-based, o do `pdos_atm#N`), rótulo, elemento, Z, posição cartesiana (Å) e fracionária, `if_pos`, `starting_magnetization`, Hubbard U, arquivo do pseudopotencial, vizinhos com distância, número de coordenação | parcial | `ScfInfo.value(...)`, `species_rows`, `Model.flags` | 1 |
| Seleção múltipla (Ctrl/Shift), caixa de seleção, "só espécie ▸", marcar/inverter | parcial | `AtomTable` + picking | 1 |
| **Distância** (2 átomos), **ângulo** (3), **diedro** (4), tabela de medidas, copiar | sim ("Tools ▸ Distances") | `core/structure/measure.py`, sobre (átomo, deslocamento) | 1 |
| **Repetir células** n1×n2×n3 (só visual), com átomos das bordas | sim ("Modify ▸ number of units drawn") | Deslocamentos inteiros; ligações replicadas, não recalculadas | 1 |
| Rótulos: símbolo, índice, ambos; mostrar/ocultar por espécie | sim | Overlay | 1–2 |
| Marcar átomos fixos (`if_pos = 0`) | não | `Model.flags` | 1 |
| Exportar PNG (e SVG/PDF no renderer QPainter) | sim | `grabFramebuffer()` / `QSvgGenerator` | 2 |
| Copiar posições da seleção como linhas de `ATOMIC_POSITIONS` | não | `Crystal` + unidade escolhida | 2 |
| Relaxamento: animar os passos BFGS, deslizador; célula por passo no vc-relax | sim (animação) | Estender o streaming de `parse_relax` com posições (§8 P8) | 3 |
| Setas de forças (`Forces acting on atoms`) e de magnetização | sim (forças) | Parser novo (streaming, cancelável) | 3 |
| Comparar entrada × geometria final: setas de deslocamento | não | `read_final_structure` | 3 |
| **Prévia na janela "Criar cálculo"** (Slab, Supercélula, Molécula): ver a estrutura gerada antes de "Criar" | não | `surface.model.Model` já é o dado; a janela hoje só mostra texto | 3 |
| Densidade de carga (`.xsf`): isosuperfícies ±iso, cortes | sim ("Data Grid") | Leitor de XSF + marching cubes (próprio, ou VTK/vispy) | 4 |
| Zona de Brillouin e pontos k da entrada | sim ("k-path selection") | Voronoi (`scipy.spatial`); o spec 27-2 decidiu que nada *sugere* caminho, então só mostraria o que o usuário digitou | 4 |

Fora de escopo por decisão sugerida: **editar** a estrutura (mover/apagar átomos). A visão é somente leitura,
como o resto do app (nunca grava na pasta da simulação sem o usuário pedir).

---

## 7. Arquitetura proposta

Independente do renderer. Respeita o §2.3.

### 7.1 `core/` (sem Qt, testável sem GL)

```
core/structure/
  scene.py      Structure: cell Å, labels, elements, frac, cart, flags, origem (input | saída), fórmula
  source.py     structure_of_input(path) [read_scf → crystal_from_editor], structure_of_output(path)
                [alat + `crystal axes` + read_sites], final_structure(path)   (workers, cancel.check)
  elements.py   element_of / covalent_radius / vdw_radius / color (extraído de surface/elements.py: §8 P7)
  bonds.py      cutoff por par; busca por lista de células/cKDTree; ligações da célula central
  replicate.py  deslocamentos (n1,n2,n3) e átomos das bordas; ligações replicadas por translação
  measure.py    distância, ângulo, diedro sobre pontos (índice, shift); imagem mais próxima
  camera.py     Camera (arcball/orbital, perspectiva/ortográfica, matrizes) em numpy
  pick.py       raio da tela → esferas (vetorizado) → (índice, shift), com profundidade
```

`Atom` é identificado por `(índice, (n1, n2, n3))`: a **cópia** em que o usuário clicou, não só o índice. É o que
torna distâncias e ângulos não ambíguos em células repetidas (§8 P6).

### 7.2 `ui/`

```
ui/widgets/structure_view/
  view.py            StructureView(QWidget): a aba; câmera, seleção, modos; emite selection_changed, measured
  renderer.py        SceneRenderer (Protocol): set_scene, set_camera, render, pick_ray, grab
  renderer_gl.py     QOpenGLWidget + shaders (D)
  renderer_paint.py  QPainter (C): reserva, testes e SVG/PDF
  overlay.py         rótulos, medidas, triedro (QPainter)
ui/widgets/structure_panel.py   página do painel esquerdo, um corpo por aba (padrão ParamsPanel)
ui/structure_controller.py      for_window(window): carrega em run_task, abre a aba, ligações com o painel
```

Pontos de integração (nada disso exige mudar o contrato dos módulos de cálculo):

| Onde | Mudança |
|---|---|
| `ui/widgets/workspace.py` | `open_structure(path)` como `open_summary`; chave `structure:<path>`; `cancel_load` na aba |
| `ui/widgets/context_menu.py` | Item "Visualizar estrutura" em input pw.x (`looks_like_input`) e em saída pw.x (`sniff.is_output`), depois de "Resumo" |
| `ui/actions.py` | Ação `structure.open` (menu, paleta de comandos Ctrl+K, atalho) |
| `ui/layout_controller.py` | `STRUCTURE_PAGE = 2`; `set_left_mode("structure")`; `plot_shown()` e restauração continuam valendo |
| `ui/widgets/bars.py` | Sem botão novo no `ActivityBar`: o painel abre quando a aba 3D fica ativa (como o de ajustes de um plot) |
| `ui/focus_controller.py` | Ordem de Tab inclui o painel; atalhos Ctrl+1..4 já cobrem a esquerda |
| `ui/shutdown.py` | `Workspace.cancel_loads` já chama `cancel_load()` das abas; só garantir que a visão tem |
| `ui/theme/*.yaml` + `test_theme_contrast.py` | Tokens: fundo, caixa da célula, seleção, rótulo, medida; ambos os temas |
| QSettings | `structure/style`, `structure/projection`, `structure/bond_factor`, `structure/background` (por visão do usuário, não por simulação) |

### 7.3 Painel esquerdo: duas formas

- **Página do painel esquerdo** (recomendado): coerente com "Ajuste do gráfico" e com o que o usuário descreveu.
  Cada aba 3D tem seu corpo (lista de átomos, seleção, medidas, exibição, espécies), e a página mostra o da aba ativa.
- **Painel dentro da aba** (`QSplitter` interno): não toca `LayoutController`, mas gasta largura do workspace
  e foge do padrão do app. Só vale se a mudança em `LayoutController` for considerada invasiva.

Seções do painel: **Átomo selecionado** (campos do §6), **Seleção e medidas** (lista de átomos selecionados,
distância/ângulo/diedro, "copiar"), **Célula** (a, b, c, α, β, γ, volume, `ibrav`, nº de átomos, fórmula),
**Exibição** (estilo, escala dos raios, fator de ligação, repetição n1/n2/n3, rótulos, caixa, fundo),
**Espécies** (cor, raio, visível).

### 7.4 Dois renderers por trás de uma interface

O `SceneRenderer` é pequeno (receber a cena e a câmera, desenhar, devolver uma imagem). Ter **GL e QPainter** custa
manter dois desenhos, mas dá:

- um fallback real onde GL não existe (§8 P4), escolhido em tempo de execução por `context().isValid()`;
- cobertura de teste do widget inteiro, já que o QPainter roda no `offscreen`;
- exportação vetorial pelo QPainter;
- uma troca barata por F (vispy) ou G (VTK) se o requisito mudar.

Ordem sugerida: núcleo + QPainter primeiro (valida a UX e os testes sem risco de GL), depois GL.

### 7.5 Testes

| Arquivo | Cobre |
|---|---|
| `test_structure_source.py` | Input (todos os `ibrav` das fixtures, `kao_surface_inputs`), saída (`si_bands/si.scf.out`, `kao_*`), unidades |
| `test_structure_bonds.py`, `_measure.py`, `_replicate.py`, `_pick.py` | Núcleo: propriedades com Hypothesis (distância invariante a translação de rede; ângulo em [0, π]) |
| `test_structure_view.py` | Visão com o renderer QPainter no `offscreen` (`grab()`, seleção por clique, painel) |
| `test_structure_gl.py` | `skipif` sem GL (marcador `gl`); `xvfb` + Mesa no CI, se se quiser |
| `test_architecture.py` | `QT_FREE` ganha `core/structure/*`; `FS_ALLOWED` não sobe |
| `test_perf_detection.py` | Novo teste: importar a janela e `core.structure` não carrega `ase`/GL/VTK |

---

## 8. Problemas e riscos

| # | Sev. | Problema | Origem | Mitigação |
|---|---|---|---|---|
| P1 | **Alto** | Testes: `QOpenGLWidget` não renderiza no `offscreen` (§4.2); o CI é headless | Medido | GL fino (só desenhar); toda a lógica em `core/`; renderer QPainter nos testes; `skipif` + marcador `gl`; `xvfb-run` com Mesa no CI (**Verificar**) |
| P2 | **Alto** | Abas movíveis: reparentar um `QOpenGLWidget` recria o contexto; os buffers somem | Leitura (comportamento do Qt) | Manter os arrays na CPU; recriar recursos em `initializeGL`; ligar `aboutToBeDestroyed`; **testar arrastar a aba** |
| P3 | Médio | Uma janela com `QOpenGLWidget` passa a ser composta por textura (RHI) no Qt 6: custo de repintura e *flicker* em alguns drivers/compositores | Leitura | Medir a repintura da grade com uma aba GL aberta; o fallback QPainter evita |
| P4 | Médio | Ambientes sem GL bom: SSH -X, VNC, WSL, VM, contêiner. GL 4.1 core pode falhar | Leitura | Detectar na inicialização; cair em QPainter; mensagem na barra; `QT_OPENGL=software` documentado |
| P5 | Médio | `QSurfaceFormat` (versão, MSAA, perfil) e HiDPI | Leitura | `widget.setFormat(...)` por instância, não global; `devicePixelRatioF` no viewport **e no picking**; raio dos átomos não escala com `font_scale` |
| P6 | Médio | Identidade e imagem periódica: o clique cai numa cópia; "distância" pode ser a da cópia ou a da imagem mínima. Em célula muito oblíqua, `pair_images` (−1…1 sobre frações escritas) pode não achar a mínima | Leitura (`surface/geometry.py`) | Medir **entre as cópias escolhidas** (identidade `(índice, shift)`); botão "imagem mais próxima" com busca −2…2; avisar quando a célula é oblíqua (`skewed`) |
| P7 | Médio | Espécie sem elemento (`X`, rótulos livres): `element_of` levanta `SurfaceError`, e mora em `calc_create/surface` | Verificado | Fallback cinza (raio 1,0 Å) + aviso; extrair `elements` para `core/structure/` ou `core/qe/` e deixar `surface` reexportar |
| P8 | Médio | Saída: o parser não lê a célula; `RelaxStep` não guarda posições; saídas de relax chegam a centenas de MB; o leitor do ASE falha em fixtures de propósito | Verificado | Parser novo em streaming com `cancel.check()`; trajetória lida sob demanda, por passo; não depender de `ase.io` |
| P9 | Médio | Ligações: O(N²) (2 000 átomos = 4 M pares) e pior ainda replicado (27×). `scipy` é transitiva, não declarada | Medido/Leitura | Ligações só da célula central e **replicadas** por translação; `cKDTree` sobre as 27 imagens; declarar `scipy` ou usar `ase.neighborlist` (0,29 s, tardio) |
| P10 | Médio | Cenas grandes: 100 átomos × 5×5×5 = 12 500; QPainter ≈ 270 ms/quadro | Medido | Modo rascunho no arrasto; limite e aviso de repetição; GL principal |
| P11 | Médio | Partida: bibliotecas pesadas no import da janela quebram o orçamento da spec 14 | Verificado (teste existente) | Import tardio; teste `test_structure_import_is_lazy` |
| P12 | Médio | Regras de arquitetura: 500 linhas, `core/` sem Qt, `ui/` sem disco, `FS_ALLOWED` | Verificado | Módulos pequenos (§7); I/O em `run_task` |
| P13 | Baixo | Tema e acessibilidade: tokens em ambos os YAML, contraste WCAG, foco por teclado na visão | Verificado | Navegação por teclado na seleção (Tab entre átomos, setas para a câmera); tokens testados |
| P14 | Baixo | Encerramento: contexto GL destruído antes do `QApplication`; `os._exit` quando há tarefa viva | Leitura | `cancel_load` da visão; liberar GL em `closeEvent` da aba |
| P15 | Baixo | `crystal_sg`, `space_group`, `ibrav` não suportado: sem estrutura | Verificado | Mensagem no lugar da cena (como "Estrutura ilegível: …" de `model_of`) |
| P16 | Baixo | Rótulos de texto em GL (atlas de fonte) | Leitura | Overlay `QWidget` transparente com `QPainter`, não GL |

---

## 9. Plano em fases

Estimativas grosseiras (linhas aproximadas, sem testes), em ordem de entrega.

| Fase | Entrega | Esforço | Observação |
|---|---|---|---|
| 0 | Item "Abrir no XCrySDen/VESTA" quando o executável existe (A) | P | Independente de tudo |
| 1 | Núcleo (`core/structure/`, ~700 linhas) + aba com **renderer QPainter** + painel esquerdo + medidas + repetição + estilos (~1 000 linhas de UI) | G | Já cobre tudo o que o usuário pediu; testável no `offscreen` |
| 2 | **Renderer OpenGL** (impostors, ligações, MSAA), escolha GL/QPainter na execução, rótulos, PNG, SVG/PDF | G | P1–P5 aparecem aqui |
| 3 | Trajetória do relax, forças/magnetização, entrada × final, **prévia em "Criar cálculo"** | M cada | Parser em streaming; reaproveita `surface.model.Model` |
| 4 | Densidade de carga (XSF) e zona de Brillouin | G | **Reavaliar G (PyVista)** ou F (vispy) aqui |

Cada fase vira uma spec (`specs/spec_N-*.md`) pelo fluxo `spec-sdd` do projeto.

---

## 10. Decisões em aberto (do usuário)

1. **Entrada**: só SCF, ou qualquer input/saída do pw.x (recomendado: qualquer um; é o mesmo código)?
2. **Painel esquerdo**: página do painel esquerdo (recomendado) ou painel dentro da aba?
3. **Densidade de carga** (XSF das specs 29–30) está no horizonte? Se sim, muda a escolha do renderer (F ou G).
4. **Exportar imagem** em PNG basta, ou precisa de vetor (SVG/PDF) para publicação? Vetor favorece manter o QPainter.
5. **Dependência de ~140 MB** (VTK) é aceitável? Se não, G sai da mesa e a decisão é D (± F).
6. **Fundo da visão**: segue o tema do app ou é sempre claro como as figuras (spec 2)? Afeta a exportação.
7. **Edição** da estrutura (mover/apagar átomos) fica fora de escopo?

---

## Apêndice A. API do PyQt6 que a prova de conceito usou (opção D)

Verificado por execução, PyQt6 6.11.0 / Qt 6.11.2, janela real (`xcb`), GL 4.1 core:

```python
fmt = QSurfaceFormat(); fmt.setVersion(4, 1)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
fmt.setDepthBufferSize(24); fmt.setSamples(4)          # widget.setFormat(fmt) por instância

# initializeGL
f = QOpenGLVersionFunctionsFactory.get(QOpenGLVersionProfile(self.context().format()), self.context())
# QOpenGLContext.functions() NÃO existe em PyQt6. Expostos: QOpenGLFunctions_2_0, _2_1, _4_1_Core.
hasattr(f, "glDrawArraysInstanced"), hasattr(f, "glVertexAttribDivisor")   # True, True

prog = QOpenGLShaderProgram(self)
prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VS)
prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FS)
prog.link()

vao = QOpenGLVertexArrayObject(self); vao.create(); vao.bind()
quad = QOpenGLBuffer(); quad.create(); quad.bind(); quad.allocate(quad_np.tobytes(), quad_np.nbytes)
f.glEnableVertexAttribArray(0); f.glVertexAttribPointer(0, 2, GL_FLOAT, 0, 8, 0)
inst = QOpenGLBuffer(); inst.create(); inst.bind(); inst.allocate(inst_np.tobytes(), inst_np.nbytes)
f.glEnableVertexAttribArray(1); f.glVertexAttribPointer(1, 4, GL_FLOAT, 0, 28, 0); f.glVertexAttribDivisor(1, 1)
f.glEnableVertexAttribArray(2); f.glVertexAttribPointer(2, 3, GL_FLOAT, 0, 28, 16); f.glVertexAttribDivisor(2, 1)

# paintGL: f.glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, n)
```

Vertex shader: quad no espaço da câmera, `gl_Position = proj * (view * centro + vec4(canto * raio, 0, 0))`.
Fragment shader: descarta `dot(uv, uv) > 1`, `n = (uv, sqrt(1 - d²))`, ponto = `vc + n * raio`,
`gl_FragDepth` pela projeção do ponto, sombreamento difuso com uma luz fixa. O vertex shader repassa ao fragment
`uv` (canto do quad), `col`, `rad` e `vc` (centro no espaço da câmera).

---

## Apêndice B. O que não foi verificado

| Afirmação | Estado |
|---|---|
| Tempo de importação e tamanho descompactado do VTK/pyvista | Não instalei (wheel de 140 MB) |
| `vtk` sem display (EGL/OSMesa) serve ao CI do projeto | Não verificado |
| Nomes e comportamento dos widgets de medida do VTK/PyVista; `render_points_as_spheres` | De memória |
| Desempenho do vispy (`Markers` esférico, `InstancedMesh`) e do pyqtgraph | Não medido |
| Qualidade visual do `Markers(spherical=True)` do vispy com primeiros planos grandes | Não verificado |
| Que a janela inteira passa a ser composta por RHI com um `QOpenGLWidget`, e o custo disso aqui | Leitura do Qt 6, não medido |
| Recriação do contexto ao arrastar abas com `QOpenGLWidget` | Leitura, não reproduzido |
| Quick 3D: instancing por Python ausente em PyQt6 6.11 | **Verificado** (só 4 classes `QQuick3D*`); o restante do Quick 3D, não testado |
| Funcionalidades e atalhos do XCrySDen (§6, coluna "XCrySDen"); opções `--pwi`/`--pwo` | De memória, sem a documentação |
| Licenças (VTK, PyVista, vispy, pyqtgraph, PyOpenGL, 3Dmol.js) | De memória |
| Desempenho do QPainter em tela real (não só em `QImage`) | Não medido |
