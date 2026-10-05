# Spec 31: Projetos na pasta raiz (`local_root`)

| | |
|---|---|
| **Prioridade** | 31 (independente das specs 28–30; pode ser feita antes delas) |
| **Status** | Proposta |
| **Depende de** | spec 16 (histórico, breadcrumb, favoritos/recentes), spec 17 e 27 (escopo do sync e push), spec 18 (paleta, primeira execução), spec 26 (local padrão de "Criar cálculo") |
| **Usada por** | nenhuma |
| **Esforço** | M/G |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): mudança transversal (explorador, grade, breadcrumb, histórico, favoritos, paleta, sync, push, primeira execução, "Criar cálculo") com estado compartilhado entre controladores, e `main_window.py` já está com 496 de 500 linhas: a implementação precisa extrair código para um controlador novo sem quebrar o resto. |

## Itens de origem (ideias de 05/10/2026)

> # Organização em "Projetos"
> - A pasta raiz do Programa é definida em 'config.yaml' usando o parâmetro "local_root".
> - Na pasta 'local_root' as pastas devem ser reconhecidas como "Projetos" isolados entre si, sem interdependência entre "Projetos".
> - Cada pasta de "Projetos" pode ter várias pastas e subpastas que organizam e agrupam as "Unidades de Simulação". O Programa deve ser capaz de reconhecer todas as "Unidades de Simulação" dentro de um "Projeto" mesmo dentro de subpastas.
> - Por exemplo: 'local_root/ilita' é um Projeto chamado 'ilita'. E dentro dessa pasta tem as seguintes pastas "Analise_1", "Analise_2", "Analise_3", etc. E dentro de cada 'Analise' tem as "Unidades de Simulação" tipo "Bandas", "PDOS", "Relax".
> - Na interface, acima da árvore de "Projetos", deve ter um botão Dropdown com o nome "Projeto" e os valores devem ser os nomes dos Projetos. Esse Dropdown deve ser capaz de filtrar a árvore de "Projetos" para mostrar apenas o Projeto selecionado. [...]
> - Uma das opções da lista de Dropdown deve ser 'Criar Projeto', que quando selecionado, abre uma pequena janela de diálogo que pede para o usuário inserir o nome do novo projeto. Esse nome será usado como nome da pasta do projeto criada em 'local_root'.

**Respostas do usuário (05/10/2026):** "unidades de simulação" são pastas normais: elas continuam visíveis pela
árvore e pela grade como hoje, **sem** lista, aba ou marca nova (a árvore filtrada já mostra todas as subpastas do
projeto, em qualquer profundidade). "Sincronizar projeto" passa a valer para o projeto selecionado; com "Todos os
projetos", para a raiz inteira.

## Situação atual

- **"Projeto" hoje é a raiz inteira.** Título da janela `"[Projeto: {root}]"` (`ui/main_window.py:125,478`);
  `PUSH_ROOT` "…o projeto inteiro não é enviado" (`core/sync/request.py:18`), rótulo "projeto inteiro"
  (`request.py:106`), "Sincronizar projeto inteiro" (`request.py:127`, `ui/actions.py:55`, ação `sync.project` →
  `MainWindow.start_project_sync` → `sync.start(self.root)`, `main_window.py:489-491`); primeira execução "Pasta do
  projeto não encontrada" (`ui/first_run.py:97-98`), "Escolher a pasta do projeto" (`ui/dialogs/first_run.py:16,40`);
  `OUTSIDE_PROJECT` "Fora da pasta do projeto…" (`core/calc_create/preview.py:37-39`).
- **Explorador** (`ui/widgets/explorer.py`, 322 linhas): de cima para baixo, `PanelHeader("Explorador")` com
  "Recolher tudo" e "Atualizar (F5)" (`:183-186`), `NavSection` Favoritos e Recentes (`:189-190`), `FilterBar`
  (`:195-198`) e a árvore `#explorerTree` (`:203-217`). Modelo próprio `make_fs_model(root)` + `FileFilterProxy`
  (`ui/widgets/fs_model.py`); `set_root` (`explorer.py:253-257`) muda o root do proxy, do modelo e o
  `setRootIndex`; `select_path` (`:288-301`) não confere se o caminho está sob a raiz da árvore.
- **Grade:** `FilePanel.set_folder` (`file_grid.py:135-146`); `..` só abaixo de `proxy.root` (`fs_model.py:162-166`);
  `go_up` não passa de `proxy.root` (`file_grid.py:263-266`); a navegação da grade passa sempre pela árvore
  (`files.folder_activated` → `explorer.select_path`, `main_window.py:209`).
- **Escopo por `local_root`:** `FolderMemory.set_root` (chaves relativas), `NavigationStore` (favoritos e recentes
  por raiz resolvida, `nav_store.py:46-64`; `NavigationController.set_root` limpa o histórico,
  `navigation_controller.py:77-85`), `GridStore` (caminhos relativos; exportações em `<local_root>/plots/grid_*`,
  `core/calculations/grid/data.py:36-42`), paleta (`list_folders(window.root, …)`, `palette_controller.py:93-104`),
  breadcrumb (`core/navigation.py:20-33`: primeiro segmento = nome da raiz), `explorer/last_folder`
  (`main_window.py:253-262,276`). `CompoundStore` é global.
- **`plots/` na raiz:** não está em `ui.hidden_dirs` (padrão `["tmp", "*.save"]`, `core/config.py:181`); só a detecção
  o ignora (`IGNORED_SUBDIRS`, `core/calculations/base.py:44`). Com grids exportados, aparece como pasta de 1º nível.
- **Sync:** `sync_scope` (`request.py:144-163`) e `prepare_sync` aceitam a raiz; `prepare_push` recusa a raiz
  (`:66-68`); `remote_dir_for` (`core/sync/rsync.py:47-56`) mapeia qualquer pasta sob a raiz para `paths.remote_root`.
  `SyncCoordinator.show_scope` (`ui/sync_coordinator.py:118-136`) mantém os textos de `sync.start`, `sync.project`,
  `sync.push`.
- **"Criar cálculo":** local padrão = `window.current_folder()` (pasta do explorador, ou a raiz da árvore sem seleção)
  (`ui/calc_create_controller.py:110-132`); aviso `OUTSIDE_PROJECT` se o local está fora da raiz
  (`setup_page.py:179-180`).
- **Nomes de pasta seguros:** `writer.validate_suffix` (`[A-Za-z0-9._-]+`); `unique_names.make_new_dir`;
  `ui/dialogs/rename.py` (76 linhas) é o padrão de diálogo de nome.
- **`main_window.py` tem 496/500 linhas** (`tests/test_architecture.py:14`).

## Requisitos

### R1: Projetos no core (`core/projects.py`, Qt-free)
1. `list_projects(root, hidden_dirs) -> list[Project(name, path)]`: as pastas de 1º nível de `root`, sem nomes com
   `.` inicial, sem as que casam `ui.hidden_dirs`, sem `plots` (exportações de grids) e sem links simbólicos (regra de
   `core/folder_index.py`); ordenadas por nome sem caixa/acentos. Roda em worker (`run_task`).
2. `project_of(path, root) -> str | None`: o projeto de um caminho (o 1º componente relativo à raiz), `None` para a
   própria raiz ou fora dela.
3. `validate_project_name(name, existing) -> list[str]`: não vazio; `[A-Za-z0-9._-]+`; sem `.` inicial; não `plots`
   nem um padrão de `hidden_dirs`; não repete um projeto existente, **sem diferenciar maiúsculas** ("Ilita" e "ilita"
   seriam confusos e quebram em sistemas de arquivos sem caixa).
4. `create_project(root, name) -> Path` (worker): `mkdir(exist_ok=False)` (nunca reaproveita uma pasta; corrida →
   erro "Já existe uma pasta com esse nome"), nada além da pasta.

### R2: Dropdown "Projeto"
1. `ui/widgets/project_combo.py:ProjectCombo` no `ExplorerPanel`, entre o cabeçalho e Favoritos, com rótulo
   "Projeto". Itens: **"Todos os projetos"**, separador, os projetos de R1.1, separador, **"Criar projeto…"**.
   `objectName "projectCombo"`, QSS em `navigation/explorer.qss` (o estilo de `QComboBox` de `controls/inputs.qss` já
   vale).
2. A lista é recarregada (R1.1 em worker) ao abrir o app, no F5, ao aplicar uma config com outra raiz, depois de
   criar um projeto e depois de `rename_path` de uma pasta de 1º nível. Enquanto carrega, o combo mostra a última
   lista.
3. A escolha fica em QSettings `explorer/project` (nome do projeto ou vazio = Todos) e volta ao reabrir. Projeto que
   sumiu (apagado ou renomeado fora do Lain) → "Todos os projetos" e mensagem no rodapé "Projeto <nome> não
   encontrado".
4. Com `local_root` inválido (estado `missing_root` da spec 18), o combo fica desabilitado.

### R3: Projeto selecionado = raiz de visualização
Com um projeto escolhido, a interface se comporta como se a raiz fosse `local_root/<projeto>`; os **dados** continuam
por `local_root` (`FolderMemory`, `NavigationStore`, `GridStore`, `CompoundStore` não mudam de chave). "Todos os
projetos" é exatamente o comportamento de hoje.
1. **Árvore:** `setRootIndex` na pasta do projeto: mostra todas as subpastas do projeto, em qualquer profundidade,
   e nada dos outros projetos nem dos arquivos soltos da raiz.
2. **Grade:** `..` e `go_up` param na pasta do projeto.
3. **Breadcrumb:** começa no projeto (primeiro segmento = nome do projeto).
4. **Favoritos e Recentes:** as seções mostram só as pastas do projeto (os outros continuam guardados).
5. **Paleta (Ctrl+K):** linhas de pasta só do projeto; ações, abas e o índice (um só, da raiz) não mudam.
6. **Navegar para fora do projeto** (voltar/avançar no histórico, link de outra origem como "Revelar no explorador",
   pasta criada por "Criar cálculo" em outro lugar, F5 com `explorer/last_folder` em outro projeto): o combo troca
   sozinho para o projeto da pasta (ou para "Todos" se ela estiver na própria raiz) e só então a pasta é
   selecionada. O histórico não é apagado ao trocar de projeto.
7. Trocar de projeto pelo combo seleciona a pasta do projeto (como um clique na árvore: `on_folder_selected`,
   histórico, grade, escopo do sync).

### R4: "Criar projeto…"
1. Escolher o item abre `ui/dialogs/new_project.py` (modal, padrão de `rename.py`): título "Criar projeto", campo
   "Nome do projeto", mensagem de validação ao vivo (R1.3) sob o campo, "Criar" habilitado só sem problemas,
   "Cancelar".
2. "Criar" → `create_project` em worker (spinner "Criando projeto…"); sucesso: lista recarregada, combo no projeto
   novo, árvore nele, toast `success` "Projeto <nome> criado"; falha: `QMessageBox.warning` com o motivo.
3. Cancelar (ou Esc) não cria nada e o combo volta ao item que estava selecionado.
4. Ação `project.create` em `ACTIONS` (menu "Arquivo ▸ Criar projeto…", sem atalho), que a paleta lista sozinha.

### R5: Sync e push
1. `sync.project`: com um projeto selecionado, "Sincronizar projeto <nome>" e sincroniza `local_root/<projeto>`;
   com "Todos os projetos", "Sincronizar tudo" e sincroniza a raiz (como hoje). O tooltip e o cabeçalho do diálogo
   (`sync_scope`) dizem o mesmo.
2. `prepare_push` recusa também a pasta de um projeto: "Escolha uma pasta de cálculo: o projeto inteiro não é
   enviado." (o push é de uma pasta de cálculo, spec 27); a ação `sync.push` fica desabilitada nela com esse motivo.
3. O mapeamento remoto não muda (`remote_dir_for`: `remote_root/<projeto>/…`).

### R6: Termos e "Criar cálculo"
1. Onde "projeto" significa `local_root`, o texto passa a dizer **"pasta raiz"**: primeira execução ("Pasta raiz não
   encontrada", "Escolher a pasta raiz"), `PUSH_ROOT` ("a pasta raiz inteira não é enviada"), `OUTSIDE_PROJECT`
   ("Fora da pasta raiz…"). Título da janela: "[Projeto: ilita]" com um projeto, "[Raiz: <caminho>]" com "Todos".
2. "Criar cálculo": sem pasta selecionada, o local padrão é o projeto selecionado (decorre de R3.1, a raiz da
   árvore); aviso âmbar quando o local é a própria `local_root`: "A pasta será criada fora de um projeto e aparecerá
   como um projeto novo."

### R7: Organização do código
1. `ui/project_controller.py:ProjectController.for_window(window)`: lista (worker), combo, QSettings, troca
   automática (R3.6), "Criar projeto…" e o escopo de visualização entregue ao explorador, grade, breadcrumb, seções e
   paleta por métodos pequenos (`set_scope(path)`), sem que esses widgets conheçam "projeto". Sinal
   `project_changed(Path | None)`.
2. `main_window.py` fica < 500 linhas: o que a spec exigir ali sai para o controlador (ex.: `_restore_folder` e
   `start_project_sync`).
3. Nenhuma leitura de disco na GUI: a lista de projetos e a criação passam por `run_task`.

## Fora de escopo
- Lista, aba, contagem ou marca de "unidades de simulação" (decisão do usuário: são pastas normais).
- Dados por projeto (favoritos, grids, mapeamentos e seleção de átomos continuam por raiz ou globais).
- Mover exportações de grids de `<local_root>/plots/` para dentro de um projeto.
- Renomear ou apagar projetos pelo combo (renomear continua pelo menu de contexto, spec 5).
- Projetos em várias raízes ou raiz por projeto no `config.yaml`.

## Decisões assumidas (confirmar na revisão)
1. Existe o item "Todos os projetos" (o comportamento de hoje), primeiro da lista e padrão na primeira execução.
2. Favoritos, recentes e a paleta são filtrados pelo projeto; a troca automática (R3.6) evita "sumir" com a pasta
   para onde o usuário navegou.
3. O breadcrumb começa no projeto, não na raiz.
4. Nome de projeto com as mesmas regras dos nomes de pasta de "Criar cálculo"; nome existente é recusado (sem `_1`).
5. `plots/` na raiz nunca é projeto; outros diretórios (inclusive pastas de cálculo antigas soltas na raiz) são.
6. Arquivos soltos na raiz só aparecem em "Todos os projetos".

## Notas de implementação
- Novos: `core/projects.py` (em `QT_FREE`), `ui/project_controller.py`, `ui/widgets/project_combo.py`,
  `ui/dialogs/new_project.py`.
- Alterados: `ui/widgets/explorer.py` (combo e `set_scope`), `ui/widgets/file_grid.py` / `fs_model.py` (limite do
  `..`), `ui/widgets/breadcrumb.py` / `core/navigation.py` (raiz do breadcrumb), `ui/navigation_controller.py`
  (filtro das seções), `ui/palette_controller.py` (filtro das pastas), `core/sync/request.py` (escopo e push),
  `ui/sync_coordinator.py` (textos), `ui/actions.py` (`project.create`), `ui/first_run.py` e `ui/dialogs/first_run.py`
  (termos), `core/calc_create/preview.py` e `setup_page.py` (aviso da raiz), `ui/main_window.py` (registro e
  extrações), `ui/resources/styles/navigation/explorer.qss`.
- Ordem de foco: o combo entra na região do explorador (`FocusController`) e recebe o `accessibleName` "Projeto".
- `CLAUDE.md`: seção nova "Projetos (spec 31)" ao implementar.

## Critérios de aceite e testes
- [ ] Core: `list_projects` ignora `.ocultas`, `tmp`, `*.save`, `plots` e links; ordena sem caixa; `project_of` da
      raiz é `None`; `validate_project_name` recusa vazio, `a/b`, `.x`, `plots`, `Ilita` com `ilita` existente.
- [ ] Combo: itens "Todos os projetos", projetos, "Criar projeto…"; escolha persiste após reiniciar
      (`window_factory`); projeto apagado → "Todos" + mensagem.
- [ ] Escopo: com `ilita`, a árvore só tem o conteúdo de `ilita` (inclusive subpastas profundas); a grade não sobe
      além de `ilita`; o breadcrumb começa em `ilita`; favoritos/recentes/paleta só de `ilita`.
- [ ] Troca automática: voltar no histórico para uma pasta de outro projeto troca o combo e seleciona a pasta;
      "Revelar no explorador" idem.
- [ ] Criar projeto: diálogo patchado → pasta criada em `local_root`, combo e árvore nela, toast; cancelar não cria
      nada e restaura a seleção; nome repetido mantém "Criar" desabilitado.
- [ ] Sync: com `ilita`, `sync.project` diz "Sincronizar projeto ilita" e sincroniza `local_root/ilita` (host-less
      `Endpoint`); com "Todos", "Sincronizar tudo" e a raiz; push recusado na pasta do projeto.
- [ ] Termos: primeira execução e título com "pasta raiz"/"[Projeto: …]"; "Criar cálculo" avisa quando o local é a
      raiz.
- [ ] `test_architecture.py`: `main_window.py` < 500 linhas; nada de `open(`/`read_text` em `ui/`; `core/projects.py`
      sem PyQt6.
