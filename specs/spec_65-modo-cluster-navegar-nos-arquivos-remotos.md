# Spec 65: modo cluster: a árvore e a grade mostram os arquivos do cluster, com fundo vermelho, e "Baixar" no menu

| | |
|---|---|
| **Prioridade** | 65: a maior da rodada; vem depois das pequenas (61–63) e da 64, de que usa a folga em `main_window.py` e o executor de comandos remotos |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 64 (R0: folga em `ui/main_window.py`; R1: `core/sync/command.py`, novo nela), spec 62 (o botão "Árvore" alterna a página da árvore que estiver valendo), spec 17 (pull com prévia e escopo), spec 27-3 (`recheck_local`), spec 31 (projeto selecionado), spec 15 (tarefas em worker), spec 19 (tokens com contraste AA) |
| **Usada por** | spec 66 (plotar no modo cluster) |
| **Esforço** | G |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): modelos e painéis novos ligados em vários pontos da janela (página da árvore, painel da grade, rodapé, F5, menu), um caminho novo de listagem pelo ssh e as regras de segurança do sync |

## Itens de origem (`Ideias.md`, 25/10/2026)

> - Melhorar sincronização, add um novo botão de sincronização para quando clicado nele, a aba esqueda 'Tree' e a aba central 'Grid' mudam a cor de fundo, e passam e exibir as pastas e arquivos do cluster, e só voltam a exibir as pastas e arquivos locais quando o botão for clicado novamente.
> - A mundança a cor do plano de fundo acontece apenas visualmente, para indicar que o Lain está exibindo os arquivos do cluster, e que o usuario não está visualizando os arquivos locais.
> - No menu do botão direito do mouse, invez de aparecer a opção upload, tem a opção download, para baixar os arquivos do cluster para o computador local.
> - Para lidar com o delay na interação quando está visualizando arquivos remotos, adicione uma animação para indicar que o Lain está processando a requisição.
> - As funções de plot continua funcionando na visualização de arquivos e pastas remotas, mas apenas para a leitura, ou seja, os arquivos são copiados para o computador local antes de serem plotados. Ou seja, plotar um grafico no ambiente remoto baixa automaticamente o conteudo necesario para a plotagem para o computador local.
> - Para a cor de fundo, no ambiente remoto, use a cor de fundo com tom vermelho.

O item das funções de plot é a spec 66. "Upload" é o "Enviar ao cluster" do menu de hoje; "download" é "Baixar" (glossário da spec 52).

## Situação atual

- **Os painéis só conhecem o disco local.** A árvore (`ui/widgets/explorer.py:227`) e a grade (`ui/widgets/file_grid.py:95`) usam
  `make_fs_model` (`ui/widgets/fs_model.py:27`, um `QFileSystemModel`) com `FileFilterProxy`; os selos e estados vêm da detecção, que lê
  os arquivos. Tudo o que a janela passa adiante é um `Path` local (`MainWindow.on_folder_selected`, abrir, plotar, renomear).
- **Composição.** O painel esquerdo é um `QStackedWidget` com a árvore (página 0) e os ajustes do gráfico (página 1,
  `ui/layout_controller.py:18`, `PARAMS_PAGE`; `set_left_mode` em `:89-93` troca por índice). O painel do meio é o próprio `FilePanel`:
  `LayoutController` exige o tipo (`:72`) e o mostra e oculta como um todo. `FilePanel` (`file_grid.py:75-107`) empilha cabeçalho, filtro e
  a vista no mesmo layout.
- **Nada lista o cluster.** O rsync só roda em dry run e transferência (`core/sync/rsync.py:151-232`). **Medido** com o rsync 3.5.0
  local (`LC_ALL=C.UTF-8`, `TZ=UTC`): `rsync --list-only --no-h <pasta>/` imprime uma linha por entrada,
  `permissões tamanho AAAA/MM/DD HH:MM:SS nome`, com `.` para a própria pasta, tamanho sem separador (sem `--no-h` sai `1,234,567`, e em
  `pt_BR` `1.234.567`) e o nome com espaços intacto; uma pasta que não existe dá código 23 e "No such file or directory". Pelo ssh, o lado
  do cluster roda `rsync --server --sender …`, que o servidor dos testes já permite (`tests/ssh_server.py:327`); a listagem ponta a ponta
  por ele **não foi verificada**. A versão do rsync do cluster não foi verificada.
- **Baixar.** `SyncCoordinator.start(folder)` (`ui/sync_coordinator.py:212`) faz o pull de uma pasta local (dry run, prévia, perguntas,
  `recheck_local`, transferência) e o "Rsync" da barra lateral o chama com a pasta atual. **Medido:** o dry run para uma pasta local que
  não existe funciona (imprime "created directory …", que `parse_itemize_line` ignora) e `_start_transfer` cria a pasta
  (`core/sync/controller.py`, `mkdir(parents=True)`). **Medido** também o filtro de um arquivo só: `--include=/<nome> --exclude=*` com
  `\` antes de `[`, `*`, `?` e `\` traz exatamente `a[1].in`, `x*y.out` e `com espaço.out`, sem o `sub/a1.in` homônimo.
- **Menu de contexto local.** `ui/widgets/context_menu.py:205` põe "Enviar ao cluster" nas pastas; o menu é um `QMenu` (nos testes,
  `QMenu.exec` precisa ser trocado).
- **Espera.** `ui/widgets/spinner.py:16` (`CircularProgress`), `StatusBar.set_busy` (`ui/widgets/bars.py:331`) e `ui/busy.py:10`
  (`BusyTracker`).
- **Cores.** Não há token de fundo vermelho; o mais perto é `error_soft` (`rgba(244, 63, 94, 0.15)`). **Medido** o contraste WCAG com os
  tokens de texto: no escuro, `#2a1216` dá `text` 13,6, `text_secondary` 10,3, `text_muted` 5,5, `text_meta` 6,0, `error` 4,8; no claro,
  `#fdecee` dá `text` 15,7, `text_secondary` 9,1, `text_meta` 4,8, mas `text_muted` só 4,2 (abaixo de 4,5): no claro um vermelho visível
  reprova o `text_muted` (só `#fff7f8`, quase branco, chega a 4,5). `tests/test_theme_contrast.py:14` lista os fundos de leitura.
- **Ícones vendorizados:** `cloud_done`, `cloud_off` e `download` existem (`scripts/fetch_assets.py:ICONS`); um nome novo exige rodar
  `fetch_assets.py` com rede. `ui/file_types.py:28` (`file_visual(path, is_dir)`) escolhe o ícone só pelo nome.
- Tamanhos: `ui/widgets/file_grid.py` 426, `ui/layout_controller.py` 193, `ui/widgets/bars.py` 373 (mais o que a 64 acrescenta),
  `ui/widgets/context_menu.py` 382, `ui/sync_coordinator.py` 332, `core/sync/request.py` 207, `core/sync/rsync.py` 383,
  `ui/main_window.py` cerca de 432/450 depois da spec 64.

## Requisitos

### R1: listar uma pasta do cluster

1. `core/sync/rsync.py`: `list_command(config, remote_dir) -> list[str]`: `rsync --list-only` com as opções comuns (`_common`: `--no-h`,
   `--timeout`, `-e` com o `ssh_command`) e `user@host:<remote_dir>/`.
2. Novo `core/remote/listing.py` (Qt-free, em `QT_FREE`): `RemoteEntry(name: str, is_dir: bool, size: int, mtime: float, link: bool)`;
   `parse_listing(stdout, hidden_dirs) -> list[RemoteEntry]` (divide em no máximo cinco campos; ignora `.`; nome por
   `decode_rsync_name`; `l` nas permissões é link: o nome é o que vem antes de ` -> `, `is_dir` falso; esconde nomes com ponto e pastas que
   casam com `ui.hidden_dirs`, pela mesma regra de `core/paths.is_hidden`); `list_remote(config, remote_dir, password) -> list[RemoteEntry]
   | RemoteFailure` com `run_command` (spec 64 R1), `child_env` e tempo `connect_timeout + 30` s. `RemoteFailure(message, connection, auth,
   missing)`; `missing` para "No such file or directory".
3. **Testes** (`tests/test_remote_listing.py`, novo): o texto medido acima (pasta, arquivo de 1234567 bytes, nome com espaço, `a[1].in`),
   link, nome com `\#ooo`, `.` e pastas ocultas fora; falhas classificadas; ponta a ponta pelo `tests/ssh_server.py` com chave, listando
   uma pasta temporária.

### R2: o estado do modo cluster, sem Qt

1. Novo `core/remote/browser.py` (Qt-free, em `QT_FREE`): `RemoteBrowser(config, view_root: Path)`. `top` é o lado do cluster da pasta
   que a janela mostra como topo (o projeto selecionado ou a raiz, spec 31), por `remote_dir_of`; `mirror_of(remote_dir) -> Path` é a
   pasta local de mesmo caminho relativo (pode não existir); `remote_of(local_folder) -> str`; `parent(remote_dir)` nunca sobe acima de
   `top`.
2. Cache da sessão, em memória: `put(remote_dir, entries, now)`, `get(remote_dir)`, `needs_refresh(remote_dir, now)` (mais velho que
   `STALE_SECONDS = 60`), `invalidate(remote_dir | None)`.
3. **Testes** (`tests/test_remote_browser.py`, novo): mapeamento local ↔ cluster com e sem projeto; `parent` preso ao topo; cache e
   validade com relógio injetado.

### R3: o botão e a troca dos painéis

1. `ui/widgets/bars.py:ActivityBar`: novo `self.remote = ActivityButton(theme, "cloud_done", _("Cluster"), …, checkable=True)` logo
   depois do "Rsync", sinal `remote_toggled(bool)`. Tooltip: "Ver os arquivos do cluster (clique de novo para voltar aos locais)";
   desabilitado, com o tooltip `SYNC_OFF` (`core/sync/request.py`), quando o sync não está configurado. `ui/actions.py:ACTIONS` ganha
   `ActionSpec("remote.toggle", MENU_CLUSTER, _("Ver arquivos do cluster"), "remote.toggle")`.
2. Novo `ui/remote_controller.py:RemoteController.for_window(window)` (uma linha em `MainWindow._build_controllers`): `active`,
   `toggle()`, `set_active(bool)`. Ligado:
   - o painel esquerdo mostra o `RemoteTreePanel` (página nova de `window.left`); `LayoutController` ganha `tree_page` (o explorador por
     padrão), usado por `set_left_mode("tree")` e pelo `_tree_shown()` da spec 62 no lugar do índice 0;
   - o painel do meio mostra o `RemoteFilePanel`: `FilePanel.show_alternate(widget | None)` põe o conteúdo de hoje numa página de um
     `QStackedWidget` interno e o painel remoto em outra (o `FilePanel` continua sendo o painel "grid" do `LayoutController`);
   - a pasta inicial é o lado do cluster da pasta local atual; se o cluster não a tem (`missing`), sobe até a primeira que lista, no máximo
     até `top`;
   - o caminho clicável e os botões de histórico da barra superior ficam desabilitados; o rodapé mostra `usuario@host:/caminho/remoto`.
3. Desligado: as páginas locais voltam como estavam (pasta, seleção, filtro); nada local foi lido nem mudado.
4. "Recarregar config.yaml" desliga o modo (rodapé: "Modo cluster desligado: a configuração mudou."); trocar de projeto com o modo
   ligado muda o `top` e volta para o topo do projeto.
5. **Testes** (`tests/test_remote_ui.py`, novo, com `list_remote` trocado por um falso que devolve entradas fixas e pode atrasar): o botão
   liga e desliga e as duas páginas trocam; o "Árvore" da spec 62 alterna a árvore remota; desabilitado sem cluster; recarregar o config
   desliga; a pasta inicial sobe quando o cluster não tem a atual.

### R4: os painéis remotos, a cor e a espera

1. Novos `ui/widgets/remote_model.py` e `ui/widgets/remote_panels.py`:
   - `RemoteTreePanel`: cabeçalho "Cluster" com `usuario@host` e o botão "Atualizar"; um `QTreeView` só de pastas (como a árvore local por
     padrão) num `RemoteTreeModel` que lista sob demanda (`canFetchMore` / `fetchMore` pedem ao controlador; nada é listado antes de a
     pasta ser aberta);
   - `RemoteFilePanel`: cabeçalho "Arquivos do cluster" com o caminho remoto; uma lista com as colunas "Nome", "Tamanho" e
     "Modificado" (pastas primeiro, ordem natural), o item ".." abaixo do topo e o ícone de `file_visual`. Duplo clique ou Enter numa pasta
     entra; Backspace e Alt+↑ sobem. Duplo clique num arquivo não faz nada (só leitura; a 66 traz o plot). Seleção múltipla
     (`ExtendedSelection`), para a 66.
   - Sem selos de cálculo nem estado OK/INCOMPLETO (dependem do conteúdo).
2. Cor: tokens novos nos dois temas: `remote_panel` (fundo dos dois painéis e das suas vistas) e `remote_accent` (faixa de 2 px no topo
   dos cabeçalhos; decorativo, sem texto em cima). Valores iniciais: escuro `#2a1216` / `#f43f5e`; claro `#fdecee` / `#dc2626`. QSS em
   `ui/resources/styles/remote/remote.qss` (novo), pelos `objectName` `remoteTreePanel` e `remoteFilePanel`. **Os painéis remotos não
   pintam `text_muted`** (no claro reprova, medido acima): metadados em `text_meta`.
3. Espera: enquanto a pasta mostrada não tem resposta, um `CircularProgress(theme, 32)` centrado sobre a lista e, no rodapé,
   `BusyTracker` com "Listando no cluster…". Uma pasta em cache aparece na hora; mais velha que `STALE_SECONDS`, é listada de novo em
   segundo plano só com o indicador do rodapé. Clicar noutra pasta substitui o pedido pendente (`TaskGroup` com chave por painel; pool
   privado de 2 threads, sem pai Qt).
4. Falha: a lista mostra a mensagem (`explain_failure`) e "Tentar de novo"; falha de conexão chama `window.sync.monitor.report(False)` e
   sucesso `report(True)`. `auth: password` sem senha conhecida pede uma vez (`SyncCoordinator.session_password(ask=True)`, da spec 64);
   login recusado esquece a senha e não tenta sozinho de novo.
5. F5 e "Atualizar" no modo cluster invalidam o cache da pasta atual e listam de novo (`MainWindow.refresh` ganha uma linha que pergunta ao
   controlador antes do refresh local).
6. **Testes** (`tests/test_remote_ui.py`, `tests/test_theme_contrast.py`): o indicador aparece durante a listagem lenta e some no fim;
   cache mostrado sem nova listagem e relistado depois de 60 s; um clique novo cancela o pendente; falha mostra "Tentar de novo" e deixa o
   LED `offline`; `text`, `text_secondary` e `text_meta` passam AA sobre `remote_panel` nos dois temas (novo
   `test_remote_panel_text_passes_aa`) e um teste confere que o QSS remoto não usa `text_muted`.

### R5: "Baixar" no menu do cluster

1. Clique direito num item remoto abre um menu próprio (`QMenu`, construído no `RemoteController`): "Baixar" e "Copiar caminho" (o caminho
   remoto, para a área de transferência). Não há "Enviar ao cluster", "Renomear", "Abrir com" nem "Abrir local de origem".
2. "Baixar" de uma **pasta**: `SyncCoordinator.start(<espelho local>)`, o pull de hoje com dry run, prévia, perguntas de conflito e
   `recheck_local`; a pasta local é criada se não existe. "Baixar" de um **arquivo**: `SyncCoordinator.start(<espelho da pasta dele>,
   only=<nome>)`, que passa `only_file_rules(nome)` (novo, `core/remote/download.py`: `--include=/<nome escapado>` e `--exclude=*`) ao
   `SyncController`; a prévia e o título dizem o arquivo ("Baixar do cluster: <pasta>/<nome>", `SyncScope` com `file`).
3. Com mais de um item selecionado, "Baixar" fica desabilitado com o tooltip "Selecione um item para baixar.". Com um sync em andamento,
   desabilitado com o motivo de hoje.
4. Depois de um "Baixar" que trouxe arquivos, a árvore e a grade **locais** são atualizadas (`synced`, como hoje); o modo cluster
   continua.
5. **Testes** (`tests/test_remote_download.py`, novo; rsync real com pastas locais como "cluster", como `tests/test_sync_integration.py`):
   pasta que não existe localmente é criada e preenchida depois de confirmar a prévia; um arquivo local diferente pergunta (nunca
   sobrescreve sozinho); "Baixar" de `a[1].in` traz só ele, não o homônimo da subpasta; `only_file_rules` escapa `[`, `*`, `?` e `\`; o menu
   não tem "Enviar ao cluster" (com `QMenu.exec` trocado).

### R6: fechamento

1. O passo "cancelar" de `ui/shutdown.py:steps_for` chama `window.remote.cancel()` (cancela as listagens; o `ssh` morre pelo
   `run_command`); `close_dialogs` não muda (o modo não tem diálogo próprio).
2. **Testes:** fechar a janela com uma listagem pendurada termina dentro do orçamento (`tests/test_shutdown.py`, novo caso).

## Fora de escopo

- Plotar no modo cluster: spec 66.
- Abrir um arquivo do cluster no visualizador, renomear, apagar ou enviar algo pelo modo cluster: só leitura e "Baixar".
- Selos de cálculo e estado dos arquivos no modo cluster: dependem do conteúdo.
- Histórico Alt+←/→, caminho clicável, filtro, favoritos e paleta Ctrl+K no modo cluster: desabilitados ou só locais.
- Reaproveitar a conexão ssh entre listagens (`ControlMaster`): medir primeiro; outra spec se a espera incomodar.
- O "Rsync" da barra lateral continua puxando a pasta **local** atual (decisão 4).

## Decisões assumidas (confirmar na revisão)

1. **Botão na barra lateral**, logo abaixo do "Rsync", rótulo "Cluster", ícone `cloud_done` (já vendorizado), checável; também no menu
   "Cluster" ("Ver arquivos do cluster").
2. **A grade remota é uma lista** (nome, tamanho, data), não cartões: os cartões existem para selos e estados que o cluster não dá sem
   baixar.
3. **Vermelho no claro é pálido** (`#fdecee`) e os painéis remotos trocam `text_muted` por `text_meta`, para passar AA; a faixa
   `remote_accent` no topo dos cabeçalhos é o que deixa o modo evidente.
4. **"Rsync" não muda no modo cluster:** fazê-lo puxar a pasta remota mostrada exigiria mudar `MainWindow.current_folder`, usado por
   plotar, criar cálculo e o estado salvo. "Baixar" no menu cobre o caso.
5. **Um item por "Baixar"** na primeira versão; vários itens seriam vários pulls em fila.
6. **Cache de 60 s por pasta**, só em memória; F5 e "Atualizar" forçam.
7. **A pasta local do "Baixar" é o espelho** (mesmo caminho relativo sob `local_root`), como o "Rsync" faz hoje.

## Notas de implementação

- Novos: `core/remote/__init__.py`, `core/remote/listing.py`, `core/remote/browser.py`, `core/remote/download.py` (novos, Qt-free, em
  `QT_FREE`); `ui/remote_controller.py`, `ui/widgets/remote_model.py`, `ui/widgets/remote_panels.py` (novos);
  `ui/resources/styles/remote/remote.qss` (novo); `tests/test_remote_listing.py`, `tests/test_remote_browser.py`,
  `tests/test_remote_ui.py`, `tests/test_remote_download.py` (novos).
- Alterados: `core/sync/rsync.py` (`list_command`), `core/sync/request.py` (`SyncScope.file`), `core/sync/controller.py` (regras extras de
  um arquivo, pelas `extra_args` que já existem), `ui/sync_coordinator.py` (`start(folder, only=None)`), `ui/widgets/bars.py` (botão),
  `ui/actions.py`, `ui/layout_controller.py` (`tree_page`), `ui/widgets/file_grid.py` (`show_alternate`), `ui/main_window.py`
  (`self.remote`, uma linha no `refresh`), `ui/shutdown.py`, os dois temas (`remote_panel`, `remote_accent`),
  `tests/test_theme_contrast.py`, `tests/test_architecture.py` (`QT_FREE`), catálogo `lain.po`/`.mo`.
- Ordem: R1 e R2 (sem Qt) → R3 → R4 → R5 → R6.
- Limites: `ui/widgets/file_grid.py` 426 → cerca de 440; `ui/main_window.py` ganha 2 linhas (cerca de 434/450). Nenhum `ui/` novo toca o
  disco: listagens em worker, pastas locais criadas pelo pull.
- Documentação ao implementar: `README.md` (seção "Modo cluster": o botão, o fundo vermelho, o cache, "Baixar"); `CLAUDE.md`, "Sync
  safety": "o modo cluster só lista (`rsync --list-only`) e baixa pelo pull de sempre, com prévia"; PRD §5.1 (uma linha sobre a listagem).
- i18n: textos novos em `_()`, depois `scripts/i18n.py update`, tradução e `compile`.

## Critérios de aceite e testes

- [ ] Com o modo desligado nada muda: a suíte existente passa sem mudar expectativas (painéis, sync, contraste).
- [ ] O botão liga e desliga o modo e a árvore e a grade mostram o cluster e voltam ao local (`tests/test_remote_ui.py`).
- [ ] A listagem lê o formato medido e funciona pelo ssh real (`tests/test_remote_listing.py`).
- [ ] Fundo vermelho nos dois painéis, com contraste AA do texto que aparece neles (`test_remote_panel_text_passes_aa`).
- [ ] Indicador de espera durante a listagem; cache; cancelamento do pedido antigo (`tests/test_remote_ui.py`).
- [ ] "Baixar" passa pela prévia e pelas perguntas de conflito, traz uma pasta inteira ou um arquivo só (`tests/test_remote_download.py`).
- [ ] Fechar com listagem pendurada respeita o orçamento (`tests/test_shutdown.py`).
- [ ] Passo manual de aceite: no cluster real, abrir o modo, navegar três níveis, "Baixar" um `scf.out` e ver o arquivo na árvore local.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
