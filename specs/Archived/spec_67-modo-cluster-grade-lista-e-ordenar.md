# Spec 67: modo cluster: "Grade", "Lista" e "Ordenar" nos arquivos do cluster, iguais aos do local

| | |
|---|---|
| **Prioridade** | 67: ajuste pequeno do modo cluster (65); independente das demais |
| **Status** | Implementada (25/10/2026). Sem desvios do plano: `FileCardDelegate` ganhou a base `CardDelegate` (a contagem de `is_dir` em `file_card.py` ficou em 2, `FS_ALLOWED` não mudou); `RemoteFileModel` manteve as três colunas e o `headerData` (o `tests/i18n_probe.py` lê os cabeçalhos); nenhum texto novo, só as linhas `#:` do catálogo mudaram |
| **Depende de** | spec 65 (`RemoteFilePanel`, `RemoteController`, `RemoteFileModel`, `remote.qss`), spec 5 (os botões e o desenho da grade local), spec 37 (cartões tão altos quanto o nome mais longo) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a 65 abriu; o único cuidado é a extração do desenho dos cartões, coberta pelos testes de grade do local |

## Itens de origem (pedido de 25/10/2026)

> No modo remoto, a exibição dos arquivos só mostra os arquivos como lista, não tem os botões de 'list', 'grid' e 'sort' como no modo local para mudar a forma de exibição dos aquivos na aba 'Grid'. Quero que o usuario possa alternar o modo de exibição no modo remoto igual como é no modo local.

Decisões do usuário na conversa: (1) a escolha é **uma só** para o local e o cluster (estado compartilhado); (2) "Lista" no cluster são **linhas como no local**
(ícone, nome e, à direita, `tamanho · data`), numa só vista, não a tabela de colunas. Isto substitui a "decisão assumida 2" da spec 65 ("a grade
remota é uma lista").

## Situação atual

- **R1 (sem botões).** `RemoteFilePanel` (`ui/widgets/remote_panels.py`) era um `QTreeView` com as colunas "Nome", "Tamanho" e "Modificado" e um cabeçalho
  só com título e contagem. `FilePanel` (`ui/widgets/file_grid.py`) criava no cabeçalho `grid_button`, `list_button` e `sort_button` (menu Nome,
  Tamanho, Data), guardava `grid_mode` e aplicava o modo em `_apply_mode` (`IconMode` com `card_size(name_lines)` ou `ListMode`).
- **R2 (desenho preso ao painel local).** `FileCardDelegate` (`ui/widgets/file_card.py`) lia `panel.proxy` (caminho, `is_dir`, `is_up`, `_meta_for`) dentro
  do `paint`: nenhuma outra vista podia reusá-lo.
- **R3 (ordem).** `sort_entries` (`core/remote/listing.py`) só ordenava por pastas primeiro e nome natural; o cache do `RemoteBrowser` guarda essa ordem.
- **R4 (persistência).** `LayoutController.restore/save` (`ui/layout_controller.py:213-225`) guardam `files/grid_mode` e `files/sort` a partir do `FilePanel`.
- Tamanhos antes: `file_grid.py` 441, `file_card.py` 306, `remote_panels.py` 303, `remote_controller.py` 465 (limite 500).

## Requisitos

### R1: os três botões, uma vez só

1. `ui/widgets/view_controls.py` (novo): `ViewControls(theme, header, token="text_muted")` cria `grid_button`, `list_button` (checáveis) e `sort_button`
   ("Grade", "Lista", "Ordenar"; menu "Nome", "Tamanho", "Data" com `SORT_NAME`, `SORT_SIZE`, `SORT_DATE` de `fs_model.py`). Guarda `grid_mode` e
   `sort_column`; `mode_changed(bool)` e `sort_changed(int)` são emitidos **só quando o valor muda**; os botões acompanham `set_grid_mode` sempre (um
   clique no botão marcado o desmarcaria).
2. `FilePanel` usa `ViewControls` (`controls`); `grid_button`, `list_button`, `sort_button` e `_sort_actions` continuam como atributos, `grid_mode` e
   `sort_column` viram propriedades, `set_grid_mode` e `set_sort` delegam. O proxy local é ordenado em `_apply_sort`.
3. **Testes:** os de grade do local passam sem mudança (`test_file_grid_menu.py`, `test_file_card_wrap.py`, `test_focus.py`, `test_main_window.py`).

### R2: o desenho dos cartões e das linhas, reaproveitado

1. `ui/widgets/file_card.py`: `CardItem(title, icon, token, meta, meta_token, is_dir)`, `CardPanel` (Protocol: `theme`, `grid_mode`, `name_lines`),
   `CardDelegate` (`sizeHint`, `paint`, lê `describe(index)`) e `apply_view_mode(view, grid, lines)`. `FileCardDelegate(CardDelegate)` mantém `_meta`,
   `_meta_for`, `helpEvent`, `_tooltip_at` e `_name_cut`; o painel passa a ser `self.files`.
2. `ui/widgets/remote_card.py` (novo): `RemoteCardDelegate(CardDelegate)`; `remote_meta(entry, grid)`: na grade, pasta "pasta" e arquivo `human_size`; na
   lista, pasta `format_mtime` e arquivo `human_size · format_mtime`; cor `text_meta`; `..` é "pasta acima". Sem selos nem estados (dependem do conteúdo).
3. **Testes:** `tests/test_remote_view.py` (`remote_meta`, `describe` de `..`, pasta e arquivo em grade e lista).

### R3: ordenar a listagem

1. `sort_entries(entries, by="name")` (`core/remote/listing.py`, Qt-free): pastas sempre primeiro; `"name"` em ordem natural; `"size"` o maior arquivo
   primeiro (pastas por nome); `"date"` o mais novo primeiro; empate pelo nome natural, então a ordem não depende da de entrada. `parse_listing` segue com
   `"name"`: o cache e a árvore não mudam.
2. **Testes:** `tests/test_remote_listing.py::test_entries_sort_by_size_and_date_with_folders_first`.

### R4: o painel remoto e a ligação com o local

1. `RemoteFilePanel`: `QTreeView` → `GridView` com `RemoteCardDelegate`, `setMouseTracking(True)`, `setUniformItemSizes(True)`; `controls =
   ViewControls(theme, header, token="text_meta")` (a regra dos painéis vermelhos: nada de `text_muted`); `show_entries` ordena
   (`SORT_KEYS` liga `SORT_NAME/SIZE/DATE` a `"name"/"size"/"date"`), mede `name_lines` e aplica o modo (`_fill`); a seleção e o item atual por nome
   ficam; trocar a ordem ou a escala reaplica sem tocar na contagem, na página nem no indicador de espera.
2. `RemoteController._share_view()`: o `controls` de cada painel liga `mode_changed` e `sort_changed` ao `set_grid_mode` e `set_sort` do outro (métodos,
   não lambdas) e o remoto começa como o local. Nenhuma chave nova no QSettings: o que `LayoutController` guarda vale para os dois, e o cluster abre no
   modo do local (grade por padrão).
3. `remote.qss`: `#remoteFileList` só com fundo, borda, `outline` e `padding` (como `#fileGrid`); saem `::item` e `QHeaderView::section` dele.
4. **Testes** (`tests/test_remote_view.py`): botões e grade como abertura; Grade/Lista trocam `viewMode()`; a escolha vale nos dois sentidos, para modo e
   ordem; o cluster abre como o local; ordenar por Tamanho e Data mantém pastas primeiro e a seleção; `..` primeiro em qualquer ordem; ordenar durante a
   espera não some com o indicador; nome longo deixa os cartões mais altos. `test_main_window.py`: depois de reabrir, o painel remoto começa no modo e na
   ordem salvos.

## Fora de escopo

- Selos de cálculo, estados OK/INCOMPLETO e contagem de itens das pastas no cluster: dependem do conteúdo (spec 65).
- Filtro por nome e por tipo (`FilterBar`) nos arquivos do cluster: outra spec, se o usuário pedir.
- Ordem e modo independentes para o cluster: decisão do usuário foi compartilhar.

## Decisões assumidas (confirmar na revisão)

1. **Decididas pelo usuário:** estado compartilhado; "Lista" em linhas como no local.
2. **Assumida:** o cluster abre em grade quando o local está em grade (padrão do local); as pastas ficam por nome em "Tamanho"; em "Data" pastas e arquivos
   vão do mais novo para o mais velho.
3. **Assumida:** `Enter` com várias linhas marcadas no cluster não faz nada (o `GridView` emite `enter_many`, ninguém ouve); antes entrava na pasta atual.
4. **Assumida:** a data da linha é `format_mtime` (`dd/mm/aaaa hh:mm:ss`), a mesma da coluna "Modificado" de antes; encurtar para a lista é a alternativa.

## Notas de implementação

- Novos: `ui/widgets/view_controls.py`, `ui/widgets/remote_card.py`, `tests/test_remote_view.py`.
- Alterados: `core/remote/listing.py`, `ui/widgets/file_card.py`, `ui/widgets/file_grid.py`, `ui/widgets/remote_panels.py`, `ui/remote_controller.py`,
  `ui/resources/styles/remote/remote.qss`, `tests/test_remote_listing.py`, `tests/test_main_window.py`, o catálogo (`#:` das mensagens movidas).
- Limites depois: `file_grid.py` 414, `file_card.py` 368, `remote_panels.py` 335, `remote_controller.py` 477, `view_controls.py` 89.
- Documentação: `specs/README.md`; `CLAUDE.md` e `README.md` não mudam.

## Critérios de aceite e testes

- [x] Os testes da grade local passam sem regenerar goldens (`test_file_grid_menu.py`, `test_file_card_wrap.py`, `test_focus.py`, `test_main_window.py`).
- [x] O cabeçalho do cluster tem "Grade", "Lista" e "Ordenar" e abre em grade (`tests/test_remote_view.py`).
- [x] A escolha de modo e de ordem vale para o local e o cluster nos dois sentidos e sobrevive a reabrir (`test_remote_view.py`, `test_main_window.py`).
- [x] Ordenar por Tamanho e Data mantém pastas primeiro, `..` primeiro e a seleção (`test_remote_view.py`, `test_remote_listing.py`).
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte `-m "not realdata and not perf"` verdes.
