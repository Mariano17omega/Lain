# Spec 37: Grade com o nome completo do arquivo e árvore só de pastas por padrão

| | |
|---|---|
| **Prioridade** | 37 (dois ajustes de painel, independentes entre si; depois dos defeitos e dos ganhos pequenos) |
| **Status** | Implementada (12/10/2026); ver "Decisões na implementação" |
| **Depende de** | spec 5 (cartões da grade), spec 16 (filtros), spec 19 (`font_scale`: tamanhos dos cartões vêm da métrica da fonte), spec 31 (a raiz da árvore é o projeto) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: M; R2: P) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o que a spec 19 fez com a altura dos cartões e o que a spec 7 fez com as chaves do `config.yaml`; nenhum contrato novo. |

## Itens de origem (`Ideias.md`)

> - Na visualização dos arquivos na grade, aba central, quando o nome é muito longo, não é exibido o nome completo. Quero que quando o nome for grande, quebre a linha, não use '...'.
>
> - Na arvore de pastas na aba lateral esquerda, por padrão deve ser exibido apenas as pastas. Adicione um parametro em 'config.yaml' para o usuario ajustar isso e fazer com que exibam os arquivos também na arvore de pastas.

## Situação atual

- **R1 (nome na grade).** `ui/widgets/file_card.py:127-130` desenha o nome do cartão com
  `painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideMiddle, name_rect.width())` numa linha só: `name_rect` tem
  `name_height()` de altura (`:36-37`, a altura de **uma** linha da fonte de 12 px) e largura `rect.width() − 12` (≈ 131 px a escala 1, ~18
  caracteres da fonte mono). Os nomes exportados pela spec 32 (`<projeto>-<pastas>-<tipo>.png`, até `MAX_STEM_BYTES` = 180 bytes) passam
  disso quase sempre. O cartão é de tamanho fixo: `card_size()` (`:50-52`, 148 × 86 a escala 1, fixado por
  `tests/test_font_scale.py:136-138`) vira `view.setGridSize(card_size())` em `ui/widgets/file_grid.py:219-221`
  (`IconMode`, `setWrapping(True)`) e a vista usa `setUniformItemSizes(True)` (`:96`). O modo lista (`:154-156`) também elide, mas a
  linha tem a largura toda menos a do tamanho/estado. Nenhum tooltip dá o nome inteiro (o `helpEvent` só explica o estado e os
  selos, `:_tooltip_at`).
- **R2 (árvore).** O modelo do explorador lista pastas **e arquivos** (`make_fs_model`, `ui/widgets/fs_model.py:28-34`:
  `AllDirs | Files`) e `FileFilterProxy` já tem `dirs_only` (`:52,60`; `_base_accepts`, `:175-182`: `return not self.dirs_only`), que
  **nenhum chamador usa**: `ExplorerPanel` cria `FileFilterProxy(hidden_dirs, parent=self, service=service, keep_ancestors=True)`
  (`explorer.py:205`), então a árvore mostra arquivos. `UiConfig` (`core/config.py:197-203`) só tem `theme`, `font_scale`, `hidden_dirs` e
  `paranoid_refresh`. `ExplorerPanel(theme, service, root, hidden_dirs)` é criado em `ui/main_window.py:140` e relido em `:441`
  (`apply_config(root, hidden_dirs)`, `explorer.py:268-271`); `main_window.py` tem 447 de 450 linhas.
  `select_path(path)` (`explorer.py:297-313`) pede o índice do `proxy`: um arquivo escondido não tem índice e nada acontece.
  Testes que listam a árvore: `tests/grid_helpers.py:73-81` (`tree_names`), usado em ~18 pontos (`test_project_ui.py` e outros).

## Requisitos

### R1: O nome inteiro no cartão

1. O nome do cartão **quebra linha** em vez de elidir. A quebra prefere `-`, espaço, `.` e `_` e, sem eles, ocorre em qualquer caractere
   (uma palavra mais larga que a linha não pode estourar o cartão).
2. **Altura única por pasta.** Como a grade é uniforme, o cartão cresce para o maior nome da pasta (o que está visível, depois dos
   filtros): `card_size(lines: int = 1)` soma `(lines − 1) × name_height()` à altura de hoje. Com todos os nomes numa linha o cartão é o de
   hoje (148 × 86 a escala 1). A quantidade de linhas é recalculada ao trocar de pasta, quando o modelo entrega ou tira linhas (um
   `QTimer` de um tiro junta rajadas), ao mudar o filtro, o modo (grade/lista) e a escala da fonte.
3. **Limite:** `MAX_NAME_LINES = 6` (≈ 108 caracteres): só além disso a última linha termina em `…`, e então o tooltip do cartão traz o nome
   completo. Abaixo do limite, **nenhum** `…`.
4. A conta fica em `ui/widgets/file_card.py` (precisa da métrica da fonte, então é de `ui/`): `name_lines(names, width, metrics)` mede só os
   nomes que não cabem numa linha (`horizontalAdvance(name) > width`) e devolve o máximo, limitado.
5. O modo **lista** não muda (uma linha por item; o espaço do nome é o que sobra).
6. **Testes** (`tests/test_file_card_wrap.py`, novo; `tests/test_font_scale.py` continua): nomes curtos → `gridSize()` = `card_size()` =
   148 × 86; um nome de 68 caracteres → altura `card_size(4)` e o nome inteiro nas linhas medidas (sem `…`); nome de 200 caracteres → 6
   linhas e `…` na última, com tooltip do nome inteiro; a pasta com um nome longo e a vizinha sem → volta ao tamanho de hoje; trocar o
   `font_scale` recalcula; a altura de `sizeHint` do cartão e a de `gridSize()` coincidem; arquivos que chegam depois (modelo assíncrono,
   `qtbot.waitUntil`) aumentam o cartão.

### R2: `ui.tree_show_files`

1. `UiConfig.tree_show_files: bool = False` ("mostrar arquivos na árvore de pastas"); `config.example.yaml` (raiz **e**
   `src/qe_studio/resources/`, idênticos) ganha a chave comentada em `ui:`; `tests/test_config.py` valida os dois.
2. `ExplorerPanel` recebe o valor (`dirs_only = not tree_show_files`) na construção e em `apply_config`, e "Recarregar config.yaml"
   o aplica sem reiniciar. Para `main_window.py` não crescer (447/450), o painel recebe o `UiConfig` (`hidden_dirs` e
   `tree_show_files` saem dele) no lugar de `hidden_dirs` solto.
3. Padrão: **só pastas**. A grade (`FilePanel`) **não muda**: continua mostrando arquivos e pastas.
4. `ExplorerPanel.select_path(arquivo)` com arquivos escondidos seleciona a **pasta do arquivo** (hoje o índice não existe e nada
   acontece); o arquivo continua selecionável na grade.
5. **Testes:** `test_config.py` (padrão `False`, valor `True`, a cópia empacotada idêntica); `tests/test_explorer_*` / `test_project_ui.py`:
   árvore sem arquivos por padrão e com `ui.tree_show_files: true`; recarregar o config troca sem reiniciar; `select_path(arquivo)`
   seleciona a pasta pai; o filtro por nome da árvore (spec 16) continua só nas pastas. Os testes que hoje esperam arquivos na árvore
   (`tree_names`) passam a montar a janela com `tree_show_files=True` onde isso é o objeto do teste, e os demais ganham a lista sem arquivos.

## Fora de escopo
- Nome completo no modo lista (a linha única é do modo; o tooltip do R1.3 também vale nele).
- Altura individual por cartão (a vista deixa de ser uniforme: layout mais lento e saltos ao filtrar).
- Mostrar só **alguns** arquivos na árvore (por tipo): é tudo ou nada.
- Editar a chave por uma janela (não há janela de ajustes, PRD §6).

## Decisões assumidas (confirmar na revisão)
1. **A grade fica uniforme**: todos os cartões de uma pasta têm a altura do nome mais longo dela (a alternativa, uma altura por
   cartão, pede outra vista e piora o desempenho de pastas grandes). Uma pasta de PDOS (`al.pdos_atm#1(Al)_wfc#1(s)`, 26 caracteres) ganha
   cartões de duas linhas.
2. **Há um limite** de 6 linhas: sem ele um nome de 180 bytes faria cartões de 10 linhas. Só passando dele aparece `…` (e o tooltip). Se o
   usuário quer nunca elidir, é tirar o limite.
3. A chave é `ui.tree_show_files` (booleano, padrão `false`), do grupo `ui:` onde já estão `hidden_dirs` e `paranoid_refresh`.
4. A árvore deixa de mostrar arquivos **por padrão**: quem já usa assim liga a chave. Foi o que o pedido pediu ("por padrão deve ser exibido
   apenas as pastas").

## Notas de implementação
- Novos: `tests/test_file_card_wrap.py`.
- Alterados: `ui/widgets/file_card.py` (198 linhas: `name_lines`, `card_size(lines)`, o desenho com quebra, o tooltip), `ui/widgets/file_grid.py`
  (346: recalcula `setGridSize`; `_apply_mode`, `_on_scale_changed`, `set_folder`), `ui/widgets/explorer.py` (334: `dirs_only`,
  `select_path`), `ui/main_window.py` (447/450: sem linha nova), `core/config.py` (`UiConfig`), `config.example.yaml` (as duas cópias),
  `tests/grid_helpers.py`, `tests/test_config.py`.
- Limites: `main_window.py` 447/450. A conta de linhas não pode tocar o disco (`FS_ALLOWED` não muda).
- Documentação ao implementar: `CLAUDE.md`, seção "Theme modes, font scale…" (a altura do cartão agora depende do nome) e "Navigation, filters
  and selection" (árvore só de pastas por padrão).

## Critérios de aceite e testes
- [ ] Pasta só com nomes curtos: cartões de 148 × 86 (`test_font_scale.py` sem mudança).
- [ ] Nome de 68 caracteres inteiro em 4 linhas, sem `…`; de 200 caracteres em 6 com `…` e tooltip completo.
- [ ] A altura acompanha filtros, troca de pasta e `ui.font_scale`; modo lista como antes.
- [ ] Árvore sem arquivos por padrão; com `ui.tree_show_files: true` e após "Recarregar config.yaml" com arquivos; a grade igual nos dois.
- [ ] `select_path` de um arquivo seleciona a pasta pai com a árvore só de pastas.
- [ ] `config.example.yaml` (as duas cópias) idênticas e com a chave.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` (`main_window.py` ≤ 450) e a suíte `-m "not realdata and not perf"` verdes.

## Decisões na implementação

1. As decisões 1–4 acima ficaram como estavam (altura única por pasta, limite de 6 linhas, chave `ui.tree_show_files`, árvore só de
   pastas por padrão).
2. **A linha do nome tem 125 px, não 131.** O item do cartão é a célula da grade menos `CARD_MARGIN` = 6 (o que o `sizeHint` tira), e o
   retângulo pintado entra `CARD_INSET` = 5 e deixa `NAME_SIDE` = 12 de ar: `name_width()` = `scaled(148) − 6 − 5 − 12`. Com 131, a
   linha estourava o cartão e o `drawText` cortava as letras das pontas (visto numa captura da grade). Em escala 1 cabem 17 caracteres
   da fonte mono, não 18; os testes derivam o número de caracteres por linha da métrica, nunca de uma constante.
3. **`sizeHint` e `gridSize()` coincidem pela mesma conta, não no valor:** `sizeHint` = `card_size(linhas) − (CARD_MARGIN, CARD_MARGIN)`
   (como já era) e `gridSize()` = `card_size(linhas)`; ambos mudam juntos com `FilePanel.name_lines`.
4. **Onde quebrar:** depois do último `-`, `_`, `.` ou espaço que deixe a linha mais da metade cheia; um separador cedo demais
   (`a-xxxxxxxx…`) não gasta a linha: quebra no último caractere que cabe. Sem separador, em qualquer caractere.
5. **Custo da conta de linhas:** só os nomes mais largos que uma linha são quebrados (cerca de 35 µs cada; 10 000 nomes ≈ 0,35 s). Por
   isso as linhas que chegam depois (o modelo lê numa thread, em rajadas) medem **só os nomes novos**, uma vez, e o recálculo da
   listagem inteira fica para a troca de pasta, linhas removidas e mudança de filtro; um `QTimer` de 30 ms junta as rajadas.
6. **O nome fica no alto do cartão e o estado embaixo** (alinhado entre os cartões de uma linha da grade); a conta de linhas usa a fonte
   em negrito (a do selecionado), a mais larga, para o cartão não mudar de altura ao selecionar.
7. **Tooltip:** o nome inteiro, uma linha em branco e, se houver, a explicação do selo ou do estado. Vale também no modo lista, quando a
   linha elide (o modo lista segue com uma linha por item).
8. **A árvore:** só o filtro do proxy (`dirs_only`) esconde os arquivos; o modelo continua lendo-os como antes (nenhum custo novo no
   disco, e a troca por "Recarregar config.yaml" não depende de o modelo reler as pastas). `ExplorerPanel` recebe o `UiConfig` inteiro:
   `main_window.py` ficou com 447 linhas.
9. **`select_path(arquivo)`** com a árvore só de pastas seleciona a pasta e emite `file_selected(arquivo)`: a grade seleciona o
   arquivo, e "Revelar no explorador" de uma aba de arquivo segue selecionando o arquivo na grade.
10. **Testes:** `test_file_card_wrap.py` (a conta pura com Hypothesis, a janela: curtos, 4 linhas, 6 linhas com `…` e tooltip, voltar
   ao tamanho, filtro, arquivos que chegam depois, escala, modo lista) e `test_tree_show_files.py` (padrão, ligado, grade igual, recarga,
   `select_path` de um arquivo); `window_factory(ui=...)` e a fixture `tree_files_window` em `conftest.py`. Os testes que listavam arquivos
   na árvore passaram a usá-la (`test_file_filter_ui`, `test_main_window`) ou a esperar só pastas (`test_project_ui`, `test_workspace_tabs`).
