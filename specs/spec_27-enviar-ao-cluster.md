# Spec 27: Enviar ao cluster (push seguro, só arquivos novos)

| | |
|---|---|
| **Prioridade** | 27 (fecha o fluxo "criar cálculo → enviar → rodar → baixar") |
| **Status** | Implementada. Desvios:<br>- **`--rsync-path` só na transferência** (e só com host): a dry-run não cria nada no cluster antes de "Enviar" (o rsync, em dry-run, finge o `mkdir` do destino, inclusive com pais ausentes; testado pelo `ssh_server`). Sem host (testes), o rsync local ignora `--rsync-path` e cria só o último nível.<br>- **`--omit-dir-times`** na transferência: nem a data de uma pasta que já existe no cluster muda.<br>- **`-i`** (decisão do usuário): arquivos idênticos (tamanho e data) não aparecem na prévia; os diferentes aparecem em "Já existem no cluster". Pasta toda idêntica → "Nada a enviar".<br>- Base comum: `core/sync/_process.py:RsyncRun` (hooks `_reset`, `_dry_run_command`, `_build_plan`, `_use_plan`, `_accepted`, `_discard_partial`, `_report`); o plano vive em `core/sync/push_plan.py` (sem Qt) e `PushReport` em `report.py`. `push.py` não importa Qt.<br>- A prévia vem de `core/sync/preview.py:describe_plan` (modelo `Preview` para pull e push); `PreviewPage` só desenha. A seção "Já existem" fica recolhida e em `text_meta`; o título de "Serão enviados" leva contagem e tamanho; a coluna de data diz "Data local".<br>- `prepare_push` também recusa pasta inexistente; a ação `sync.push` fica desabilitada na raiz (tooltip = motivo).<br>- `main_window.py`: `bind_actions(self._actions)` + `bind_menu(self.item_actions)` (+1 linha). `SyncDialog` não conecta mais `conflict_needed` (o coordenador liga a `await_decision` no pull).<br>- Inclui o lembrete adiado da spec 26 R5.3 (`created_notice(..., sync=)`). |
| **Depende de** | spec 17 (prévia do plano, `SyncDialog` em páginas, toast); spec 15 (`SyncCoordinator`) |
| **Usada por** | spec 26 (o toast da criação sugere o envio) |
| **Esforço** | M |

## Itens de origem

> -- A criação desses calculos é feita localmente, o usuario deve enviar os arquivos gerados para o cluster usando a ferramenta de sincronização. (`Ideias.md`)

A ferramenta de sincronização do Lain é **só pull** (PRD §5: "Upload (*push*) is deferred to future versions";
`report.md` F16: "Só com pré-visualização e confirmação por arquivo (integridade §7)"). Decisão do usuário nesta
rodada: criar uma spec própria de **push seguro**, que só **acrescenta** arquivos novos ao cluster.

## Situação atual

- Os dois comandos do rsync têm o cluster como **origem** e a pasta local como destino
  (`core/sync/rsync.py:131-173`: `dry_run_command` termina em `remote.spec(), str(local_dir)/` e
  `transfer_command` idem; não há parâmetro de direção). A dry-run usa `-n -rt -i --modify-window=1`
  `--out-format=%i|%l|%M|%n`; a transferência usa `-t --info=progress2 --files-from=- --from0`; nunca há `--delete`.
  `_common` (l.122-128) dá `--no-h`, `--timeout`, `--protect-args` abaixo de 3.2.4 e o `-e ssh …`, valendo para os dois
  sentidos. `Endpoint.spec()` (l.39-44) e `remote_dir_for(local_folder, config)` (l.47-56) são simétricos;
  `child_env` (l.95-108) põe a senha só no `SSH_ASKPASS` do ambiente do filho.
- `SyncController` (`core/sync/controller.py`, 368 linhas): `start(local_dir, remote)` →
  `_check_version` (`rsync --version`) → dry-run → `_plan` (worker) → `_use_plan` → `plan_ready` / `confirm_plan` →
  conflitos (`conflict_needed` / `resolve`) → `_start_transfer` (cria a pasta local, l.232) → `_finish`; `_step()`
  garante que exceção vira FAILED; `_remove_temp_files` (l.319) limpa temporários locais do rsync.
- `core/sync/planner.py`: `Action` = NEW / UPDATE / LOCAL_NEWER; `build_plan` (l.100-121) compara mtime remoto e
  local; `ConflictResolver`; `LARGE_FILE_BYTES`. `preview.py` (`plan_groups`, `plan_summary`, `large_summary`) e
  `report.py` (`SyncReport`) têm textos de "Baixar".
- `core/sync/request.py`: `prepare_sync(config, folder) -> SyncRequest | SyncRefusal` (l.32-44) e `SyncScope`
  ("Baixar do cluster…").
- UI: `ui/sync_coordinator.py` (200 linhas) dono do fluxo; `ui/dialogs/sync_dialog.py` + `sync_pages.py`
  (busca, prévia, transferência) com os textos "Sincronizando com o cluster" e "Baixar" fixos; `ui/actions.py`
  tem `sync.start`/`sync.project`; `ui/dialogs/rename.py:20-23` (`SYNC_NOTE`).
- `SyncConfig` (`core/config.py:112-119`): `exclude` (padrão `DEFAULT_EXCLUDES`: `tmp/`, `*.save/`, `*.wfc*`,
  `*.mix*`, …), `rsync_binary`, `ssh_binary`, `confirm_plan`. `config.example.yaml` tem cópia idêntica em
  `src/qe_studio/resources/` (`test_config.py`).
- Testes de sync (CLAUDE.md): `rsync` e `ssh` **reais**; `tests/ssh_server.py` (paramiko) serve `remote_root`,
  executa `exec` como subprocesso **sem shell** de uma lista permitida (`rsync --server …`, `true`, `echo`; o
  resto recebe status 127 e é registrado). Um push chega como `rsync --server` (sem `--sender`), então o
  servidor já o aceita; **`mkdir -p … && rsync` não** (precisa de shell).
- `main_window.py` tem 475/500 linhas; tudo novo entra por `SyncCoordinator`/controladores.
- O cluster usa, pelos scripts de referência, Intel oneAPI sobre uma distribuição de servidor: o `rsync` remoto
  pode ser antigo (< 3.2.3), então `--mkpath` não pode ser exigido.

## Requisitos

### R1: Comandos de envio (`core/sync/rsync.py`)
1. `push_dry_run_command(config, remote, local_dir, version, extra=None)`: igual à dry-run atual com os
   operandos trocados (`str(local_dir)/ → remote.spec()`), `-n -rt -i --out-format=%i|%l|%M|%n` e
   **sem** `--ignore-existing`, para a prévia conseguir listar também os arquivos que já existem no cluster.
   Exclusões: `config.sync.exclude` + `config.sync.push_exclude` (R5).
2. `push_transfer_command(config, remote, local_dir, version, extra=None)`: `-t --info=progress2 --files-from=-
   --from0 --ignore-existing` + `_common`; **só** os arquivos NEW da prévia vão em `--files-from`, e
   `--ignore-existing` fica como cinto e suspensório (o rsync nunca atualiza um arquivo que já existe no
   destino, mesmo se alguém criou o arquivo remoto entre a prévia e o envio). **Nunca** `--delete`, `--remove-*`,
   `--update`/`-u` ou `--inplace`.
3. Pasta remota inexistente (pasta de cálculo nova): `--rsync-path="mkdir -p <dir> && rsync"` (universal,
   independe da versão do rsync remoto), com `<dir>` = `shlex.quote` do caminho remoto vindo de
   `remote_dir_for` (config + caminho relativo; nunca de conteúdo de arquivo). `--mkpath` **não** é usado.
   É o único comando remoto novo além do `rsync --server`.
4. Os dois comandos usam `Endpoint`/`child_env`/askpass como o pull (senha nunca em argv ou log; chave de host
   desconhecida sempre recusada).

### R2: Plano de envio (`core/sync/planner.py`, `core/sync/push.py`)
1. `build_push_plan(records, local_dir) -> PushPlan`, sem Qt: de cada registro da dry-run de envio, código com
   `+++++++++` (item novo) → `PushAction.NEW` (a enviar); qualquer outro código (já existe, difere em tamanho ou
   data) → `PushAction.EXISTS` (**não será enviado**, informativo). Itens locais com tamanho e mtime vêm do
   disco (`stat`).
2. `PushPlan.new`, `.exists`, `.large` (mesmo `LARGE_FILE_BYTES`), `total_bytes`. Plano sem `new` →
   "Nada a enviar" (UP_TO_DATE de envio): sem prévia, vai direto ao fim.
3. **Integridade (PRD §7):** nenhuma ação do plano de envio altera ou apaga algo no cluster. `EXISTS` nunca vira
   envio, e **não há conflito a resolver** (nada de `ConflictDialog` no envio).

### R3: Controlador de envio (`core/sync/push.py:PushController`)
1. Controlador irmão do `SyncController`, que reaproveita seus ajudantes (`_launch`, `_step`, `_finish`,
   `_report_progress`; extrair para uma base comum `core/sync/_process.py` se preciso, mantendo
   `controller.py` abaixo de 500 linhas). Estados: `rsync --version` → dry-run de envio → plano (worker) →
   `plan_ready(PushPlan)` → espera `confirm_plan(bool)` → transferência → relatório.
2. A prévia é **sempre** exibida quando há algo a enviar; **`sync.confirm_plan: false` não vale para o envio**
   (o envio escreve no cluster; confirmar é a regra). Cancelar na prévia termina como CANCELLED sem enviar nada.
3. Não cria a pasta local, não remove temporários locais e não mexe em arquivos locais.
4. `PushReport` reaproveita a estrutura de `SyncReport` com os textos de envio ("12 arquivo(s) enviado(s).";
   "3 já existiam no cluster e não foram alterados.").

### R4: Escopo, UI e fluxo
1. `core/sync/request.py:prepare_push(config, folder) -> PushRequest | SyncRefusal`: sync ligado, pasta dentro do
   projeto (`remote_dir_for`), senha pedida quando necessária (como `prepare_sync`). Enviar a **raiz do projeto
   inteira** é recusado ("Escolha uma pasta de cálculo; o projeto inteiro não é enviado"), para impedir um envio
   gigante acidental. `SyncScope` ganha direção (`pull`/`push`) e o texto "Enviar para o cluster: <pasta relativa>
   (e subpastas)".
2. `SyncCoordinator.push(folder)`: mesma sequência do pull (senha de sessão, `PushController`, `SyncDialog`, relatório,
   toast); `finish`, `notice` e `scope_changed` seguem o padrão. `cluster_changed` e o `ConnectionMonitor` são os
   mesmos.
3. `SyncDialog`/`sync_pages.py` recebem o texto do título e do botão de confirmação por parâmetro:
   "Enviando para o cluster" / "Enviar" (pull continua "Sincronizando com o cluster" / "Baixar"). A prévia de
   envio agrupa por ação e pasta como a de pull, com **duas seções**: "Serão enviados (N · tamanho)" e "Já
   existem no cluster, não serão alterados (M)" (recolhida, cinza). Itens grandes continuam destacados.
4. Pontos de entrada:
   - ação `sync.push` em `ui/actions.py` ("Cluster ▸ Enviar pasta ao cluster…", `start_push` no coordenador) para a
     pasta atual do explorador; tooltip e texto acompanham `show_scope` como `sync.start`;
   - item **"Enviar ao cluster"** no menu de contexto de **uma pasta** (`ItemActions.menu`, sinal
     `push_requested(Path)`), abaixo de "Abrir com"; desabilitado com o motivo quando o sync está desligado;
   - nenhum botão novo nas barras.
5. Fim: DONE → toast `success` ("5 arquivo(s) enviado(s)", "Detalhes"); UP_TO_DATE → "Nada a enviar"; FAILED →
   `QMessageBox.critical` sobre o `SyncDialog`, como no pull. O envio **não** dispara pull nem atualização do
   explorador (nada local mudou).

### R5: Configuração
1. `SyncConfig.push_exclude: list[str]` (padrão `["plots/", "*.plot"]`): o que nunca sobe (figuras e ajustes são
   locais). O envio usa `exclude` + `push_exclude` (padrão: `tmp/`, `*.save/`, `*.wfc*` etc. também não sobem).
   Documentado em **ambas** as cópias de `config.example.yaml`.
2. Sem chave para desligar a prévia do envio nem para permitir sobrescrever.

### R6: Documentação
1. PRD §5 (`spec_0-PRD.md`) e `CLAUDE.md` ("Sync (PRD §5, pull only)" → "pull; push seguro de arquivos novos") dizem
   que há um push limitado, nunca sobrescreve, sempre com prévia. Um parágrafo sobre `ssh_server` aceitar
   `mkdir -p … && rsync` (R7).
2. O `SYNC_NOTE` de `ui/dialogs/rename.py` não muda (renomear continua só local).

### R7: Servidor SSH de teste
`tests/ssh_server.py` passa a aceitar `exec` no formato `mkdir -p <dir> && rsync --server …`: cria `<dir>` (dentro
do `remote_root`, recusando caminho fora dele), registra em `server.log` e executa o `rsync --server`. Qualquer
outro comando continua com status 127. O servidor testa esta regra em `test_ssh_server.py`.

## Fora de escopo
- Atualizar (sobrescrever) arquivos no cluster, apagar remoto (`--delete`), push do projeto inteiro.
- Submeter o job (`qsub`) ou acompanhar a execução (F11), sincronizar ao terminar o job.
- Selecionar na prévia quais arquivos enviar (aceita ou cancela tudo, como a spec 17).
- Conflito e merge de arquivos que já existem no cluster.
- Chave do host e senha pela interface (decisões já tomadas; ver spec 17).

## Decisões assumidas (confirmar na revisão)
1. Envio **só de arquivos novos** (decisão do usuário): arquivo que já existe no cluster nunca é alterado, mesmo
   que o local seja mais novo. Para reenviar uma versão nova, o usuário a coloca numa pasta nova (o "Criar cálculo"
   já faz `_1`) ou apaga o arquivo no cluster por fora.
2. Prévia sempre; `confirm_plan: false` não se aplica ao envio.
3. **Raiz do projeto não é enviada**; só pastas de cálculo.
4. Exclusões do envio = `sync.exclude` (as do pull) + `push_exclude` (`plots/`, `*.plot`).
5. `mkdir -p` via `--rsync-path` (não `--mkpath`), porque o rsync do cluster pode ser anterior a 3.2.3; o caminho
   é escapado com `shlex.quote` e vem da configuração, nunca de arquivos.
6. Sem conflitos no envio: arquivo existente aparece como "já existe, não será alterado" na prévia, sem diálogo.
7. O envio não atualiza o explorador local nem faz pull.
8. O item de menu de contexto aparece só para **pastas** (um item), não para arquivos soltos nem multi-seleção.

## Notas de implementação
- Novos: `core/sync/push.py` (`PushController`, `PushAction`, `PushPlan`, `PushReport` — dividir se passar de ~300 linhas),
  `core/sync/_process.py` (base comum extraída de `controller.py`, se necessário).
- Alterados: `core/sync/rsync.py` (dois comandos + `--rsync-path`), `core/sync/planner.py` (`build_push_plan`) ou
  `push.py`, `core/sync/request.py` (`prepare_push`, `SyncScope` com direção), `core/sync/preview.py` e `report.py`
  (textos por direção), `core/config.py` (`push_exclude`), as duas cópias de `config.example.yaml`,
  `ui/sync_coordinator.py` (`push`), `ui/dialogs/sync_dialog.py` e `sync_pages.py` (textos por parâmetro),
  `ui/actions.py` (`sync.push`), `ui/widgets/context_menu.py` (item e sinal), `ui/main_window.py` (≤ 2 linhas),
  `tests/ssh_server.py` (R7), `specs/spec_0-PRD.md` e `CLAUDE.md` (R6).
- `core/sync/controller.py` fica sem mudar de comportamento; a extração da base comum só move código e não pode
  alterar os testes do pull (`test_sync_*`, `test_sync_coordinator.py`).
- O `rsync` precisa estar presente nos testes (como hoje); sem ele, testes pulam.

## Critérios de aceite e testes
- [ ] Comandos: `push_dry_run_command` tem `str(local)/` e depois `remote.spec()` e **não** tem `--ignore-existing`;
      `push_transfer_command` tem `--ignore-existing`, `--files-from=-`, e nenhum de `--delete`, `--remove-source-files`,
      `-u`/`--update`, `--inplace`; `--rsync-path` com `mkdir -p` e caminho escapado (`shlex.quote`: espaços e
      aspas); a senha nunca aparece em argv.
- [ ] Planner (sem Qt): `+++++++++` → NEW, outros códigos → EXISTS; plano só com EXISTS → "nada a enviar".
- [ ] Controlador (rsync real, `Endpoint` sem host): com 2 arquivos novos e 1 já existente, `plan_ready` traz
      `len(new) == 2` e `len(exists) == 1`; **nada** é enviado até `confirm_plan(True)`; `confirm_plan(False)` →
      CANCELLED e remoto intacto.
- [ ] Integridade: arquivo remoto existente com conteúdo diferente (e mtime mais antigo **e** mais novo) permanece
      idêntico depois do envio; nenhum arquivo remoto apagado; arquivos locais intactos; a pasta remota
      inexistente é criada.
- [ ] Corrida: arquivo criado no remoto entre a prévia e o envio não é sobrescrito (`--ignore-existing`).
- [ ] Servidor SSH (`ssh_server`): envio por chave e por senha (askpass) funcionam; `mkdir -p … && rsync` aceito e
      confinado ao `remote_root`; comando fora da lista continua 127 e registrado.
- [ ] `prepare_push`: raiz do projeto → recusa; pasta fora do projeto → recusa; sync desligado → mensagem de
      configuração; pasta de cálculo → `PushRequest`.
- [ ] UI (`test_sync_ui`-style): prévia com as duas seções; Esc/X na prévia = "Cancelar"; DONE → toast `success`
      sem `QMessageBox`; FAILED → `QMessageBox.critical`; menu de contexto de pasta mostra "Enviar ao cluster"
      (desabilitado sem sync); ação `sync.push` na paleta.
- [ ] Pull inalterado: `test_sync_integration.py`, `test_sync_ssh.py`, `test_sync_ui.py`, `test_sync_dialog.py`,
      `test_sync_coordinator.py` passam sem mudança de comportamento.
- [ ] `config.example.yaml` idêntico nas duas cópias e com `push_exclude`.
- [ ] `test_architecture.py`: arquivos < 500 linhas (`controller.py`, `main_window.py`), `core/sync/push.py` sem Qt
      fora do que `controller.py` já usa (adicionar à lista `QT_IN_CORE` só se usar `QProcess`).
