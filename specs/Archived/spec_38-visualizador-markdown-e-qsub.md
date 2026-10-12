# Spec 38: Visualizador — Markdown renderizado e scripts `.qsub` com realce e verificação de escrita

| | |
|---|---|
| **Prioridade** | 38 (dois itens do mesmo visualizador; independentes das specs de gráficos) |
| **Status** | Implementada (12/10/2026); ver "Decisões na implementação" |
| **Depende de** | spec 10 (`TextViewer`, `read_preview`), spec 11 (`InputView`, `LintIssue`, `InputHighlighter`), spec 26 (R6: `ShellHighlighter`; `descricao.md`), spec 19 (tokens de tema) |
| **Usada por** | spec 39 (a edição no modo Avançado reaproveita a verificação do script) |
| **Esforço** | G (R1: M; R2: M) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho da spec 11 (lexer/lint no `core/`, realce e linha de problemas na `ui/`); nenhum contrato usado em vários lugares. |

## Itens de origem (`Ideias.md`)

> - Arquivos markdown, quando abertos na aba de visualização, deve ser rendezinados como markdown, não como texto puro.
>
> - Os arquivos '.qsub' são visualizados como arquivo de texto puro na aba lateral. Os scripts '.qsub' devem ser visualizados como com realce, erros de escrita, e coisas do tipo igual como é com os arquivos de input.

## Situação atual

- **Markdown.** `".md"` está em `TEXT_SUFFIXES` (`core/file_kinds.py:15-19`), então `viewer_kind` dá `"text"` e a aba é um `TextViewer`
  (`ui/widgets/workspace.py:160`) com `CodeView` (`QPlainTextEdit` com margem de números). Não há nenhum tratamento de Markdown em
  `text_viewer.py`, `text_preview.py` ou `highlighters.py`. O arquivo que o Lain mesmo gera é `descricao.md` (spec 25 R7 / spec 26 R4.7).
  `read_slice` entrega o arquivo inteiro até 4 MB, senão início + fim com marcador (`core/textfile.py`).
- **`.qsub`.** `".qsub"` também está em `TEXT_SUFFIXES`; `read_preview` (`core/text_preview.py:50-94`) só marca `highlight` para saída
  de QE ou log de job e `is_input` para o que `looks_like_input` reconhece, então um script não ganha nada: texto puro
  (`ui/widgets/text_viewer.py:176-192`). Já existe o realce: `ShellHighlighter` com `SHELL_RULES` (`ui/widgets/highlighters.py:141-167`:
  palavras-chave do shell, strings, variáveis, comentários e as diretivas `#$` com a opção em negrito), usado só na prévia de "Criar
  cálculo" (`ui/dialogs/calc_create/preview.py:31`). A spec 26 R6.2 deixou o visualizador de `.qsub` para depois
  (`specs/Archived/spec_26-criar-calculo-janela.md:148`). **Não existe verificação de escrita de scripts**: o lint é só de input
  (`core/qe/input_lint.py`, `LintIssue` em `core/qe/input_lexer.py:81-86`: `line` 1-based, `col_start` / `col_end` 0-based, `severity`,
  `message`). `InputView` (`ui/widgets/input_view.py`, 174 linhas) mostra a linha "N problemas de escrita no input" (F8 / Shift+F8) e os
  chips; `InputHighlighter.set_issues` (`highlighters.py:121-123`) sublinha em onda e `CodeView.set_diagnostics` põe a marca na margem.
- **Os scripts de referência** (`Documentation/Referencia_de_scripts_QSUB/*.qsub`, 6 arquivos) e os que "Criar cálculo" gera
  (`resources/templates/qsub/*.qsub.j2`: 7 tipos sobre o cabeçalho `_base`) usam: `#!/usr/bin/env bash`, diretivas `#$ -N "nome"`, `#$ -pe physica 64`, `#$ -cwd`,
  `#$ -j y`, variáveis `${MPICOMMAND}`, heredocs (`cat > "proj.in" << EOF … EOF`, com aspas simples dentro), `mkdir -p`, `mv … 2>/dev/null`,
  `exit 0`. Nenhum tem `if` / `for` / `case`.
- **Limites:** `text_viewer.py` 264 linhas, `highlighters.py` 167, `input_view.py` 174, `text_preview.py` 94.

## Requisitos

### R1: Markdown renderizado

1. `.md` e `.markdown` (`".markdown"` entra em `TEXT_SUFFIXES`) abrem **renderizados** por padrão num novo
   `ui/widgets/markdown_view.py:MarkdownView(QTextBrowser)`: `setMarkdown` com `MarkdownDialectGitHub | MarkdownNoHTML` (tabelas, listas de
   tarefas, código; HTML cru **não** é interpretado). `read_preview` marca `is_markdown` (sufixo; nunca para log de job nem saída de QE).
2. **Alternar Texto / Renderizado:** um botão de duas posições na barra do visualizador; "Texto" é o `CodeView` de hoje (números de linha,
   busca, "Ir para a linha"). A escolha vale para o programa todo e fica no QSettings (`viewer/markdown_rendered`, padrão `true`).
3. **Tema:** cores só de tokens existentes (`text`, `text_secondary`, `accent`, `card`, `border`, `workspace`), aplicadas por **uma
   passada de formatos sobre o documento** logo depois do `setMarkdown` (a folha de estilo do `QTextDocument` só vale para
   `setHtml`: ver "Decisões na implementação") e refeitas em `theme_changed`; a fonte do texto é a de UI e a do código é a mono
   (`ui_font`, `mono_font`). Nenhum token novo (os de contraste de `test_theme_contrast.py` já cobrem).
4. **Links:** `setOpenLinks(False)`; `http(s)://` abre em `QDesktopServices.openUrl`; âncoras `#titulo` rolam; qualquer outro destino
   (arquivo local, `file:`) **não abre** e o rodapé diz "Link não aberto: …". **Imagens** relativas se resolvem na pasta do arquivo
   (`setSearchPaths`), nada é baixado da rede.
5. **Arquivos grandes:** acima de `MARKDOWN_RENDER_LIMIT = 1 MB` (ou truncado pelo `read_slice`), abre em "Texto" com o banner de
   arquivo grande de hoje e o botão de renderizar desabilitado com o motivo.
6. **Ctrl+F / F3 no modo renderizado** passam para "Texto" e abrem a busca (a busca é do `CodeView`).
7. **Testes** (`tests/test_markdown_view.py`, novo): `.md` abre renderizado e `.txt` não; títulos, listas, tabela e bloco de código saem como
   estrutura (`document().toHtml()` tem `<h1`, `<table`, e o texto visível não tem `#` nem `**`); `<script>` e HTML cru não viram HTML;
   um clique em `https://…` chama `QDesktopServices.openUrl` (trocado por teste) e em `outro.md` / `file:///…` não abre; imagem relativa
   carrega; alternar mostra o texto original com números de linha; a escolha persiste ao reabrir; `theme_changed` refaz a folha de estilo;
   arquivo de 2 MB abre em "Texto" com banner; `descricao.md` gerado por `create_folder` abre renderizado.

### R2: Scripts `.qsub` com realce e verificação

1. **Realce:** `read_preview` marca `is_script` para `.qsub` (que não é log de job nem saída de QE) e o `TextViewer` usa `ShellHighlighter`
   (como `InputHighlighter` para inputs). `ShellHighlighter` ganha `set_issues({bloco: [LintIssue]})` e o sublinhado em onda de
   `InputHighlighter`, subindo os dois para a base (`ThemedHighlighter`) para não duplicar.
2. **Verificação de escrita**, Qt-free, em `core/qsub_lint.py`: `lint_script(text) -> list[LintIssue]`, que **nunca levanta** e não
   executa nada (sem `bash -n`: o lint não pode depender do shell do usuário). O corpo de um heredoc (`<< EOF … EOF`) não é
   verificado como shell. Regras (severidade entre parênteses):
   - fim de linha CRLF: o bash do cluster lê `\r` como parte do comando (erro, uma vez por arquivo, na 1ª linha com `\r`);
   - aspas `"` ou `'` abertas e não fechadas até o fim do arquivo (erro, na linha onde abriu);
   - `${` sem `}` na linha (erro);
   - `if`/`fi`, `for`/`while`/`until`/`do`/`done`, `case`/`esac` sem par, em posição de comando (erro, na linha do que sobrou);
   - `\` no fim da linha seguido de espaço: a continuação quebra (aviso);
   - diretiva `#$` com opção fora do conjunto do `qsub` do SGE (`-N -pe -cwd -wd -V -v -S -j -o -e -q -l -m -M -t -hold_jid -b -r -P -A -p
     -R -w -binding -h -a`, mais `-hard -soft -tc -notify -shell -ckpt …`: `SGE_OPTIONS`): aviso "opção desconhecida"; `-pe` sem
     ambiente **ou** sem número de slots, ou `-N` sem nome: erro;
   - sem `#!` na primeira linha (aviso).
3. **A linha de problemas:** `InputView` ganha `bind_issues(issues, noun)` ("N problemas de escrita no script", F8 / Shift+F8 como no
   input); os chips e o "Comparar com…" ficam ocultos para script. `CodeView.set_diagnostics` pinta a margem.
4. Limite de leitura: acima de `INPUT_READ_LIMIT` só o realce e o banner "Script grande: a escrita não foi verificada" (como no input).
5. **Testes** (`tests/test_qsub_lint.py`, novo; `tests/test_properties.py`): **os 6 scripts de referência e os 7 tipos renderizados por
   `core/calc_create` (`tests/calc_helpers.py`) não têm problema nenhum**; um exemplo mínimo para cada regra (com a linha e as
   colunas); o heredoc com aspas desbalanceadas dentro não gera erro; `lint_script` nunca levanta e é rápido em texto aleatório
   (propriedade, Hypothesis). `tests/test_text_viewer.py`/`test_qsub_viewer.py` (novo): `.qsub` abre com `ShellHighlighter`, a linha de
   problemas conta e navega, o sublinhado cobre o trecho, `.sh` sem a extensão `.qsub` continua texto puro.

## Fora de escopo
- `.sh`, `.pbs` e `.slurm` (estão em `TEXT_SUFFIXES`, mas o pedido foi o `.qsub`; basta somar a extensão a `is_script` depois).
- Validar nomes de programas, caminhos ou `-pe <ambiente>` contra o cluster (o lint olha só como está escrito, como o de input).
- Editar o arquivo no visualizador (continua somente leitura; a edição é da spec 39, na janela de criação).
- Renderizar LaTeX, diagramas ou HTML dentro do Markdown.
- Realce de `$VAR` fora do que `SHELL_RULES` já cobre.

## Decisões assumidas (confirmar na revisão)
1. **Renderizado por padrão**, com botão para ver o texto: é o que o pedido diz ("rendenizado como markdown, não texto puro") e o texto
   continua a um clique para quem edita à mão.
2. HTML cru dentro do Markdown **não** é interpretado e links locais **não** abrem: o visualizador abre arquivos de pastas
   sincronizadas do cluster, que o usuário não escreveu.
3. A verificação do script é **por regras escritas** (lista de R2.2), não por `bash -n`: determinística, testável sem shell e sem rodar nada.
   A lista é a que se escreve errado sem ambiguidade; falta de regra não é prova de script correto.
4. O conjunto de opções `#$` é o do `qsub` do SGE que eu conheço; uma opção fora dele é **aviso**, não erro (o cluster pode ter uma
   extensão). **Não verificado** contra a documentação do SGE do cluster do usuário.
5. Renderiza até 1 MB; acima abre em texto (o `QTextDocument` não é feito para megabytes).
6. A busca no modo renderizado passa para "Texto" (a busca do visualizador é do `CodeView`).

## Notas de implementação
- Novos: `ui/widgets/markdown_view.py`, `core/qsub_lint.py` e `core/markdown_links.py` (entram em `QT_FREE` de
  `tests/test_architecture.py`), `tests/test_markdown_view.py`, `tests/test_markdown_links.py`, `tests/test_qsub_lint.py`,
  `tests/test_qsub_viewer.py`.
- Alterados: `core/file_kinds.py` (`.markdown`), `core/text_preview.py` (94: `is_markdown`, `is_script`, as `issues`), `ui/widgets/text_viewer.py`
  (264: a pilha `CodeView` | `MarkdownView`, o botão, a escolha do realce), `ui/widgets/highlighters.py` (167: `set_issues` na base),
  `ui/widgets/input_view.py` (174: `bind_issues`), `tests/test_properties.py`.
- Limites: nenhum arquivo passa de ~330 linhas depois. A leitura e o lint rodam no worker (`read_preview`); a GUI só pinta.
- Documentação ao implementar: `CLAUDE.md`, seções "Text viewer and tabs (spec 10)" (Markdown) e "Input viewer (spec 11)" (script).

## Critérios de aceite e testes
- [x] `.md` abre renderizado (títulos, listas, tabela, código, links), alterna para o texto original e lembra a escolha.
- [x] HTML cru não é interpretado; link `http(s)` abre no navegador; link local não abre; arquivo > 1 MB abre em texto com banner.
- [x] `.qsub` abre com realce e a linha de problemas; cada regra do R2.2 com um exemplo; os scripts de referência e todos os gerados
      passam limpos.
- [x] `lint_script` nunca levanta (propriedade) e `test_properties.py` continua verde.
- [x] `test_architecture.py` (`QT_FREE`, 500 linhas), `ruff check`, `ruff format --check`, `pyright`, `test_theme_contrast.py` e a suíte
      `-m "not realdata and not perf"` verdes.

## Decisões na implementação

1. As decisões 1–6 acima ficaram como estavam (renderizado por padrão, HTML cru e links locais não abrem, verificação por regras
   escritas, aviso para opção desconhecida, limite de 1 MB, a busca passa para "Texto").
2. **A folha de estilo não vale para o Markdown.** `QTextDocument.setDefaultStyleSheet` só alcança o `setHtml`: o importador do
   Markdown escreve os formatos direto (medido: o link continua `#0000ff` com a folha e sem ela). O tema é uma passada sobre o
   documento depois do `setMarkdown` (`MarkdownView._style`: links, código em linha, blocos de código, bordas das tabelas), que
   `theme_changed` refaz a partir do texto guardado. Custo medido em 1 MB: 0,19 s de `setMarkdown` + 0,27 s da passada, na thread da
   GUI (por isso o limite). Cor do texto e fundo são o QSS de `#markdownView`, com o token `workspace` (o do `#textViewer`) em vez de
   `window`.
3. **Os títulos não têm nome de âncora** na importação do Qt, então `#titulo` não rola sozinho: `core/markdown_links.heading_slugs`
   (estilo GitHub, `-1` nos repetidos) dá os nomes e `MarkdownView.scroll_to_heading` acha o bloco. A regra de quais links abrem fica
   em `core/markdown_links.link_action`, sem Qt, e é o que o teste de tabela exercita.
4. **De 1 a 4 MB não havia banner** (o de "arquivo grande" só aparece com truncamento, acima de 4 MB): `read_preview` ganhou o
   "Markdown grande (N): exibido como texto, sem renderizar."; um arquivo truncado pelo leitor mantém o seu banner e também não é
   renderizado.
5. **`.qsub` e `.md` são julgados pelo nome, nunca como input.** O `PDOS.qsub` de referência tem um heredoc com `&PROJWFC`, que o
   `looks_like_input` (só o início do arquivo) poderia tomar por input.
6. **O conjunto de opções `#$` ficou maior que o da spec** (`-hard -soft -tc -notify -shell -ckpt -c -i -u -sync -terse -verify -ac
   -dc -sc -js -jc -masterq -now -pty -clear -C -dl -ar -xdv -hold_jid_ad -help`, da `qsub(1)` do SGE): um aviso falso custa mais
   que um que falta. **Continua não verificado contra a documentação do cluster do usuário.** Um `#$` é lido onde estiver, dentro de
   um heredoc também (o SGE lê o arquivo todo); `-pe` pede os dois valores e `-N` um nome não vazio.
7. **`#$ -p -5`:** `-5` é valor, não opção (a opção é `-[A-Za-z_]+`).
8. **Ctrl+F / F3 no modo renderizado** mostram o texto *daquela aba* e não gravam a escolha (um Ctrl+F não vira a preferência do
   programa). Um clique em Texto / Renderizado grava `viewer/markdown_rendered` **e** muda as outras abas de texto abertas
   (`Workspace._sync_render_mode`): "vale para o programa todo". Ctrl+L não faz nada no modo renderizado (não há números de linha).
9. **Defeito que o teste achou:** o importador deixa o cursor, e com ele a vista, no fim do documento; `set_source` termina com
   `go_start`. `go_end` leva a barra ao máximo (o cursor só precisa estar visível).
10. **`TextViewer`** passou de 264 para ~380 linhas, abaixo das 500 da regra; `main_window.py` ganhou 1 linha (448 de 450).
11. **Medida do lint:** 1 MB de script em 0,13 s (`test_lint_script_of_a_big_script_is_quick`, `-m perf -s`); uma linha sem aspas,
    barras, `$`, `#` nem operadores é tokenizada por `split()` e não pelo laço de caracteres.
