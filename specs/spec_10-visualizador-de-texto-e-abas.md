# Spec 10: Visualizador de texto, abas do workspace e coordenadas do cursor

| | |
|---|---|
| **Prioridade** | 10 |
| **Status** | Implementada. Desvios: a leitura de coordenadas do matplotlib já aparecia no `#plotMessage` (o `set_message` do `_Navigation` ignora `coordinates`), então `coordinates=False` ficou e o trabalho do R6 é o `format_coord` por módulo; relax e SCF mostram o valor do passo/iteração mais próximo, não o Y do cursor; `SearchBar` ficou em `search_bar.py` e o `TextViewer` em `text_viewer.py` |
| **Depende de** | spec 8 (`format_coordinates`) |
| **Usada por** | spec 11 (o visualizador de input estende o `TextViewer`), spec 12 (abas de resumo), spec 16 (Ctrl+F por foco) |
| **Esforço** | M |

## Itens de origem (`report.md` §3)

> **Workspace.** **Visualizador de texto**: busca (Ctrl+F), realce (`!    total energy`, `JOB DONE`, `Error`), número de linha, "ir ao fim", **seguir arquivo**. Arquivo grande mostra só 1 MB do início + 2 MB do fim com o meio omitido (`workspace.py:23-42`): oferecer navegação paginada ou "Abrir no editor externo" no banner.
>
> **Menu de contexto da aba** (fechar outras/todas/à direita, copiar caminho, revelar no explorador) e fechar com botão do meio.
>
> **Barra do gráfico.** **Coordenadas do cursor**: `NavigationToolbar2QT(..., coordinates=False)` (`plot_view.py:109`) elimina a leitura de E/k sob o mouse. Reativar no `plotMessage`.

Decisões do usuário (30/09/2026):
- "Seguir arquivo" (parte do F10) **fica fora**.
- Os botões "Copiar imagem" / "Exportar dados" da barra do gráfico (F3) **ficam fora**.
- "Divisão do workspace" **não** será implementada.

## Situação atual

- `TextViewer` (`ui/widgets/workspace.py:81-124`):
  - `QPlainTextEdit#textViewer` somente leitura, `NoWrap`, fonte JetBrains Mono 12 px (QSS
    `workspace/viewers.qss`);
  - carrega em worker (`_LoadText`, l.61-78);
  - banner `QLabel#viewerBanner` com a propriedade `level` (warning/success/error);
  - não tem busca, realce (não há `QSyntaxHighlighter` em `src/`), margem de números de linha nem atalhos
    de navegação.
- Arquivo grande (`workspace.py:23-42`):
  - acima de `LARGE_FILE` = 4 MB, mostra os primeiros 1 MB (`HEAD_BYTES`) e os últimos 2 MB
    (`TAIL_BYTES`), com o marcador `[ … trecho omitido pelo visualizador … ]`;
  - banner: "Arquivo grande (X): exibindo o primeiro … e os últimos …". Não oferece nenhuma ação.
- `Workspace` (`workspace.py:168-262`):
  - `QTabWidget` com `setTabsClosable(True)` e `setMovable(True)`;
  - fecha só pelo X (`tabCloseRequested` → `close_tab`, l.230-241, que emite `tab_closing`);
  - sem menu de contexto e sem fechar com o botão do meio;
  - cada aba tem uma chave (`_keys`) e um tooltip, que é o caminho.
- Barra do gráfico (`ui/widgets/plot_view.py`):
  - `_Navigation(NavigationToolbar2QT)` (l.88-95) repassa `set_message` para `on_message`;
  - `PlotToolbar` cria o navegador com `coordinates=False` (l.109) e o esconde;
  - `#plotMessage` recebe só as mensagens de modo (l.139). Com o pan/zoom inativo, não há leitura de
    coordenadas.
- Atalhos atuais (`main_window.py:282-300`): F5, Ctrl+Q, Ctrl+G, Ctrl+E e Ctrl+T. Ctrl+F está livre.
- "Abrir com" e o programa padrão já existem em `core/desktop_apps.py` e `ui/widgets/context_menu.py`
  (spec 5).

## Requisitos

### R1: Busca no texto (Ctrl+F)
1. Ctrl+F com o foco num `TextViewer` (ou na aba de texto atual) abre uma barra de busca no topo do
   visualizador. Ela tem um campo, "Anterior" (Shift+Enter / Shift+F3), "Próximo" (Enter / F3), uma
   opção "Diferenciar maiúsculas", o contador "3 de 17" e "Fechar" (Esc).
2. Todas as ocorrências ficam realçadas (`ExtraSelection`, token novo `search_match_bg`), e a atual com
   um token mais forte (`search_current_bg`).
3. A busca roda sobre o texto exibido. Num arquivo grande truncado, o contador avisa "(no trecho
   carregado)".
4. O Ctrl+F **depende do foco**: no explorador ou na grade, ele é o filtro rápido da spec 16. O atalho é
   registrado com `Qt.WidgetWithChildrenShortcut` em cada área, e não como `QAction` global.

### R2: Realce de saídas do QE
1. `OutputHighlighter(QSyntaxHighlighter)` em `ui/widgets/highlighters.py`, aplicado quando o sniff em
   cache do arquivo é uma saída (`FileSniff.is_output`) ou um log de job (spec 4).
2. Regras (linha inteira ou trecho), com tokens novos nos **dois** temas:
   | Padrão | Token |
   |---|---|
   | `^!\s+total energy` | `hl_energy` (negrito) |
   | `JOB DONE`, `convergence has been achieved`, `bfgs converged`, `End of BFGS Geometry Optimization` | `hl_success` |
   | `convergence NOT achieved`, `%%%%…` (bloco de erro), `Error in routine`, `^\s*Error` | `hl_error` |
   | `Message from routine`, `Warning`/`WARNING` | `hl_warning` |
   | `the Fermi energy is`, `highest occupied`, `Final enthalpy`, `total magnetization` | `hl_info` |
   | `Program \w+ v\.` (cabeçalho) | `hl_header` |
3. O realce é por bloco (linha), sem estado entre linhas, exceto o bloco `%%%%`, que usa
   `setCurrentBlockState` para marcar as linhas entre as duas linhas de `%`.

### R3: Números de linha e navegação
1. Margem com números de linha à esquerda do texto (o widget `CodeView` subclassa `QPlainTextEdit`, com
   `LineNumberArea` no padrão do exemplo "Code Editor" do Qt). Tokens: `gutter_bg`, `gutter_fg` e
   `gutter_current_fg`.
2. Num arquivo truncado, os números do trecho final são os **reais** do arquivo. O loader conta as
   linhas do trecho omitido (contagem de `\n` em streaming no worker), e a margem soma esse
   deslocamento depois do marcador.
3. Barra pequena do visualizador (acima do texto, à direita): "Ir ao início" (Ctrl+Home), "Ir ao fim"
   (Ctrl+End) e "Ir à linha…" (Ctrl+L, diálogo com número).
4. Esta barra e a margem são a base que a spec 11 usa para os marcadores de erro de input.

### R4: Arquivos grandes
1. O banner de arquivo grande ganha dois botões:
   - **"Abrir no editor externo"**: abre com o programa padrão do tipo (`desktop_apps.default_app`,
     `QProcess.startDetached`, sem shell, como o "Abrir com" da spec 5). Sem programa padrão, usa
     `QDesktopServices.openUrl`;
   - **"Carregar tudo"**: só para arquivos de até `LOAD_ALL_LIMIT` = 64 MB. Relê o arquivo inteiro no
     worker e substitui o texto. O banner passa a mostrar "Arquivo completo (X)". Acima do limite, o
     botão fica desabilitado, com o tooltip "Arquivo grande demais para o visualizador: use o editor
     externo".
2. Durante a carga, o texto fica com o placeholder "Carregando…", como hoje, e a busca fica desabilitada.

### R5: Menu de contexto das abas e botão do meio
1. Clique direito numa aba abre:
   - "Fechar" (Ctrl+W), "Fechar outras", "Fechar à direita", "Fechar todas";
   - separador;
   - "Copiar caminho": copia o tooltip da aba (caminho do arquivo ou da pasta do gráfico);
   - "Revelar no explorador": seleciona o item na árvore e na grade (`ExplorerPanel.select_path` + a
     pasta na grade, com o arquivo selecionado).
2. Clique com o botão do meio numa aba a fecha.
3. Todo fechamento passa por `Workspace.close_tab`, então `tab_closing` continua disparando o flush do
   `.plot` (spec 3) para cada aba de gráfico fechada.
4. "Fechar à direita" segue a ordem visual das abas (que podem ter sido movidas).

### R6: Coordenadas do cursor na barra do gráfico
1. Com o mouse sobre um eixo, `#plotMessage` mostra as coordenadas formatadas pelo hook
   `CalculationModule.format_coordinates(x, y, axes_index, dataset, params)` (spec 8):
   - bandas: `k = 0.5120 · E − E_F = −1.234 eV`. Perto (±1 % do eixo) de um ponto de alta simetria,
     acrescenta o rótulo (`· X`);
   - PDOS: `E − E_F = −1.234 eV · PDOS = 0.873 est./eV`, respeitando a orientação;
   - relax: `passo 4 · |ΔE| = 1.2e-05 Ry` ou `passo 4 · F = 3.1e-04 Ry/Bohr`, conforme o painel;
   - SCF (spec 9): `iteração 6 · precisão = 2.5e-05 Ry`.
2. Implementação: `PlotView` instala `ax.format_coord` em todos os eixos depois de cada render. O
   `_Navigation` passa a ser criado com `coordinates=True`, e o texto chega por `set_message`, como hoje.
3. Fora dos eixos, a mensagem volta para a do modo (pan/zoom) ou fica vazia.
4. A fonte do `#plotMessage` já é mono (`plot_view.qss`), então os números não "pulam".

## Fora de escopo
- Seguir arquivo / atualizar sozinho (F10, adiado).
- Navegação paginada de arquivos grandes (fica o "Abrir no editor externo" + "Carregar tudo").
- Edição de texto (o visualizador continua somente leitura).
- Botões "Copiar imagem" e "Exportar dados" (F3, adiado).
- Dividir o workspace (decisão do usuário).

## Decisões assumidas (confirmar na revisão)
1. Entre paginação e editor externo, a spec escolhe **editor externo + "Carregar tudo" até 64 MB** (R4).
2. O Ctrl+F depende do foco: busca no texto ou filtro no explorador/grade (R1.4).
3. Ctrl+W fecha a aba atual (atalho novo).
4. Os números de linha reais no trecho final de arquivos truncados (R3.2) custam uma leitura completa em
   streaming no worker. Isso é aceitável porque o arquivo já é lido em parte.

## Notas de implementação
- Novos: `ui/widgets/highlighters.py` (também usado pela spec 11), `ui/widgets/code_view.py`
  (`CodeView` + margem + barra de busca), `tests/test_text_viewer.py`.
- Alterados:
  - `ui/widgets/workspace.py` (`TextViewer` usa `CodeView`, banner com ações, menu das abas, botão do
    meio);
  - `ui/widgets/plot_view.py` (`coordinates=True`, `format_coord`);
  - `ui/resources/styles/workspace/viewers.qss` e `tabs.qss`;
  - `ui/resources/themes/{dark,light}.yaml`: tokens `search_match_bg`, `search_current_bg`, `hl_energy`,
    `hl_success`, `hl_error`, `hl_warning`, `hl_info`, `hl_header`, `gutter_bg`, `gutter_fg`,
    `gutter_current_fg`.
- O realce relê as cores no `theme_changed` (método ligado, não lambda, como manda o CLAUDE.md) e chama
  `rehighlight()`.
- Teste de menu de aba: patch de `QMenu.exec`, como em `test_file_grid_menu.py`.

## Critérios de aceite e testes
- [ ] Ctrl+F num texto abre a barra de busca, e "total energy" em `al.scf.out` dá o contador correto.
      Enter avança e Shift+Enter volta. Esc fecha e limpa o realce.
- [ ] Ctrl+F com foco na grade **não** abre a barra de busca do texto.
- [ ] `OutputHighlighter`: a linha `!    total energy` recebe o formato `hl_energy`, `JOB DONE` recebe
      `hl_success`, e um bloco `%%%%` sintético recebe `hl_error` em todas as linhas.
- [ ] Margem: número de linhas = número de blocos. Num arquivo truncado sintético, o primeiro número
      depois do marcador é o número real da linha.
- [ ] "Carregar tudo" num arquivo de 5 MB substitui o texto (sem marcador). Num arquivo acima de 64 MB,
      o botão fica desabilitado.
- [ ] "Abrir no editor externo" chama `QProcess.startDetached` (monkeypatch) com o caminho como
      argumento.
- [ ] Menu da aba: "Fechar outras" com 3 abas deixa só a atual. "Fechar à direita" respeita a ordem
      visual. Fechar uma aba de gráfico com edição pendente grava o `.plot`.
- [ ] Botão do meio fecha a aba sob o cursor.
- [ ] Coordenadas: um evento de movimento sintético sobre o eixo do gráfico de bandas produz
      `k = … · E − E_F = … eV` em `#plotMessage`.
