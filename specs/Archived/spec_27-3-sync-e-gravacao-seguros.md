# Spec 27-3: Sincronização e gravação seguras (chave do host, renomear, corrida do pull, escrita atômica)

| | |
|---|---|
| **Prioridade** | 27-3 |
| **Status** | Implementada |
| **Depende de** | spec 15 (controladores), spec 17 e 27 (sync e push), spec 5 (renomear) |
| **Usada por** | spec 31 (a folga de linhas em `main_window.py` que esta spec abre) |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): integridade de dados e concorrência (corrida entre prévia e transferência, escrita atômica com duas instâncias, `renameat2`), uma invariante de segurança que os testes atuais não enxergam e uma extração de código de `main_window.py` que mexe em sete arquivos de teste. |

## Itens de origem (`specs/report-04-10-26.md`)

- **S1 (Médio):** `StrictHostKeyChecking` não é fixado; a regra "chave desconhecida é sempre recusada" depende do `~/.ssh/config`.
- **B2 (Médio):** `rename_path` não confere sync/push (nem outras tarefas) em andamento na pasta.
- **B7 (Baixo):** (a) pull: entre a prévia e a transferência um arquivo local pode mudar e ser sobrescrito; (b) `PlotSettingsStore.flush_now`: escrita antiga na fila
  pode sobrescrever a nova depois de um tempo esgotado.
- **S2 (Baixo):** escrita atômica sem nome temporário único, sem `fsync`, sem trava de instância.
- **S3 (Baixo):** `rename_item` tem uma janela entre a verificação e o `rename`.

## Situação atual

- **S1.** `core/sync/rsync.py:59-77` (`ssh_command`) monta `-p`, `ConnectTimeout`, `ServerAliveInterval`, `ServerAliveCountMax` e `BatchMode=yes` (chave, com `-i` e
  `IdentitiesOnly`) ou `NumberOfPasswordPrompts=1` (senha). Não há `StrictHostKeyChecking` em `src/`. Único chamador: `_common` (`rsync.py:127`), que serve às quatro
  montagens de comando (`dry_run_command` `:147`, `transfer_command` `:169`, `push_dry_run_command` `:193`, `push_transfer_command` `:225`). O `CLAUDE.md` e a spec 17 dizem
  "chave desconhecida é sempre recusada"; hoje isso vale pelo padrão `ask` do ssh (sem TTY recusa) e por `core/sync/askpass.py:19-21` (responde "no" a qualquer pergunta
  `yes/no`). Um `StrictHostKeyChecking no` ou `accept-new` no `~/.ssh/config` do usuário para o host aceita em silêncio. Os testes não veem isso: `tests/ssh_server.py:ssh_binary()`
  fixa um `-F` temporário com `UserKnownHostsFile`, `GlobalKnownHostsFile /dev/null`, `StrictHostKeyChecking {strict}` etc., e `Strict = Literal["yes", "ask"]` (`:35`).
  Testes atuais: `test_sync_ssh.py:106` (`test_unknown_host_key_is_refused`: `(key,yes)`, `(key,ask)`, `(password,ask)`, `known_hosts="empty"`; exige FAILED, "Chave do host"
  na mensagem, nenhuma pasta local e `server.attempts == [] and server.log == []`), `:125` (`test_changed_host_key_is_refused`), `test_sync_rsync.py:39-50` (argv).
- **B2.** `ui/main_window.py:371-407` (`rename_path`, 37 linhas): `ask_rename` → `plot_settings.flush_now(inside=path)` → `plot_workflow.wait_for_exports()` (até 10 s, **retorno
  ignorado**) → `rename_item` (com `QMessageBox.warning` em `OSError`) → `workspace.close_tabs_under`, `navigation.rename`, `memory.rename`, `grids.rename`,
  `service.invalidate(path.parent)`, seleção e mensagem. Nenhum teste de `self.sync.running`. `SyncCoordinator.running` (`sync_coordinator.py:75-77`) é
  `controller is not None and controller.running` e cobre pull e push (ambos estendem `RsyncRun`, `_process.py:72`), mas **não expõe a pasta**: só `self.scope`
  (`SyncScope.relative`, relativo à raiz; `None` quando ocioso). Outras tarefas sobre uma pasta: exportação (`PlotExporter`), `DeriveController._tasks` (chave
  `scf:{saída}`), `CalcCreateController.create` (`run_task(create_folder, …)` fora de `TaskGroup`, chave `calc:create`), cargas de gráfico. `BusyTracker`
  (`ui/busy.py`) só expõe `labels`, sem pasta. Os testes de renomear patcham `qe_studio.ui.main_window.ask_rename` em sete arquivos (`test_navigation_ui:179`,
  `test_bands_dos_ui:133`, `test_file_grid_menu:324`, `test_favorites_ui:171`, `test_summary_view:204`, `test_grid_workflow:109`, `test_input_view:592`) e
  `test_file_grid_menu.py:~353` patcha `qe_studio.ui.main_window.rename_item` e `QMessageBox.warning`.
- **B7 (a).** `core/sync/controller.py`: `resolve` `:41`, `_use_plan` `:63`, `_begin_conflicts` `:77`, `_next_conflict` `:81` → `_start_transfer` (`:91-101`) monta
  `files = [item.path for item in self._plan.new + approved]` (`:93`), cria a pasta e envia por `--files-from=-`. Nada reconfere os arquivos locais. `PlanItem`
  (`planner.py:31`) tem `local_mtime` (preenchido em UPDATE e LOCAL_NEWER; `None` em NEW). O push é imune (`--ignore-existing`).
- **B7 (b).** `ui/plot_settings.py:87-95` `flush_now`: `self._pool.waitForDone(DRAIN_MS)` (`DRAIN_MS = 5000`, retorno ignorado) e depois escreve na GUI thread; o pool é um
  `QThreadPool` privado de 1 thread; uma escrita ainda na fila roda depois com o `params` antigo.
- **S2.** `core/appdirs.py:32-36` `atomic_write_text`: `tmp = path.with_name(f".{path.name}.tmp")`, `write_text`, `os.replace`; sem `fsync`. Chamadores: `folder_memory.py:149`,
  `nav_store.py:115`, `compounds.py:166`, `grid_store.py:219` e `plotting/plot_file.py:62` (`.plot`, dentro das pastas dos cálculos). Não há `QLockFile`,
  `QSharedMemory`, `flock` nem teste direto de `atomic_write_text`.
- **S3.** `core/file_ops.py:41-47`: `rename_item` chama `rename_error` e `_taken` e depois `path.rename(target)`; no POSIX o `rename` sobrescreve um arquivo (ou
  diretório vazio) que apareça entre os dois passos. Único chamador: `main_window.py:388`; o diálogo usa `rename_error` (`ui/dialogs/rename.py:61`). Testes: `test_file_ops.py`
  (`test_rename_error`, `test_rename_file_and_folder`, `test_rename_never_overwrites`).

## Requisitos

### R1: Chave do host sempre estrita (S1)
1. `ssh_command` acrescenta `-o StrictHostKeyChecking=yes` nos dois modos (chave e senha), logo nos quatro comandos (pull e push). Uma opção `-o` na linha de comando vence
   o `ssh_config`; o `known_hosts` do usuário continua valendo. A mensagem de falha e a dica (`FAILURE_HINTS`, "conecte uma vez pelo terminal") continuam as mesmas
   ("Host key verification failed").
2. `askpass.py` mantém a resposta "no" (defesa em profundidade); o comentário do teste "ssh asks through SSH_ASKPASS" é atualizado.
3. `tests/ssh_server.py`: `Strict = Literal["yes", "ask", "no", "accept-new"]` (o `ssh_config` do teste pode ser permissivo).
4. Testes: (a) `test_sync_rsync.py` exige `"StrictHostKeyChecking=yes"` no argv de pull e push, com chave e com senha; (b) novo, parametrizado em
   `strict` ∈ {`no`, `accept-new`} com `known_hosts="empty"`: o pull **falha**, `server.attempts == []`, o arquivo `known_hosts` continua vazio e nenhuma pasta local
   é criada; o mesmo para push.
5. `CLAUDE.md` (seção de sync) passa a dizer que a regra é imposta pelo Lain (`-o StrictHostKeyChecking=yes`), não pela configuração do ssh do usuário.

### R2: Renomear com algo em andamento (B2) e extração do controlador
1. `ui/rename_controller.py:RenameController` (`for_window(window)`, como `derive_controller.py`) recebe o corpo de `rename_path`; `MainWindow.rename_path(path)` fica como
   fachada de uma linha (os testes e `scripts/screenshot.py` a chamam). Isso tira ≈ 35 linhas de `main_window.py`.
2. Antes de pedir o novo nome, `blocked(path) -> str | None` devolve o motivo (Português) quando:
   - há sync ou push rodando cuja pasta **contém** o caminho, **está dentro** dele ou é a raiz do projeto (`SyncCoordinator.running` e nova propriedade
     `SyncCoordinator.folder: Path | None` = `root / scope.relative`, `None` ocioso): "Há uma sincronização em andamento em <pasta>. Espere terminar ou cancele.";
   - há exportação de figura em andamento (`PlotExporter` passa a ter `running`), ou `wait_for_exports()` voltou `False` (hoje ignorado): "Exportação em andamento…";
   - `DeriveController` tem tarefa cuja saída está sob o caminho (`DeriveController.active_under(path)`) ou `CalcCreateController` está criando uma pasta sob o caminho
     (`CalcCreateController.creating_under(path)`).
3. O motivo aparece em `QMessageBox.information` e nada é alterado (nem `.plot` gravado, nem aba fechada).
4. Os sete arquivos de teste citados em "Situação atual" passam a patchar `qe_studio.ui.rename_controller.ask_rename` (e `.rename_item` em `test_file_grid_menu.py`).
5. Testes novos: rename bloqueado com `SyncCoordinator.running` simulado (pasta pai, filha e raiz bloqueiam; irmã não), com exportação em andamento e com tarefa de
   `DeriveController`; rename libera depois que a tarefa termina.

### R3: Corridas pequenas (B7)
1. **Pull.** Antes de `_start_transfer`, `SyncController` reconfere cada arquivo que a transferência sobrescreveria ou criaria:
   - NEW que passou a existir localmente, ou UPDATE/LOCAL_NEWER aprovado cujo `(mtime, tamanho)` local mudou desde o plano, **saem** da lista de `--files-from`;
   - entram no relatório (`SyncReport.changed_locally: tuple[str, ...]`; "N arquivo(s) mudaram localmente durante a prévia e não foram baixados", em "Detalhes");
   - `PlanItem` guarda `local_size` além de `local_mtime` (também nos NEW, `None` = não existia); a reconferência roda no worker (`run_task`), nunca na GUI.
2. **`flush_now`.** Cada escrita enfileirada leva um número de sequência por arquivo (`itertools.count`); `_write` descarta a que chega depois de uma mais nova já gravada
   (verificação sob um lock). A escrita da GUI thread depois de `DRAIN_MS` usa o mesmo mecanismo, então a antiga, ainda na fila, não a sobrescreve. O retorno de `waitForDone`
   é registrado em `log.warning`.
3. Testes: pull com o arquivo local editado entre `plan_ready` e `confirm` (host-less, `sync_helpers.run_sync(..., before_confirm=…)`) não o sobrescreve e o relatório o lista;
   NEW criado na janela idem; `PlotSettingsStore`: duas escritas do mesmo `.plot` com a segunda adiantada ficam com o conteúdo da segunda.

### R4: Escrita atômica e instância única (S2)
1. `appdirs.atomic_write_text(path, text)`: arquivo temporário **único** na mesma pasta (`tempfile.NamedTemporaryFile(dir=…, prefix=f".{name}.", suffix=".tmp", delete=False)`),
   escreve, `flush`, `os.fsync`, `os.replace`; em qualquer erro remove o temporário e relança. Em POSIX, `fsync` da pasta como melhor esforço. Mesma assinatura (os cinco chamadores não mudam).
2. `tests/test_appdirs.py` (novo): queda simulada no `os.replace` mantém o conteúdo antigo e não deixa `.tmp`; duas escritas concorrentes (threads) do mesmo destino não dividem
   o temporário e o resultado é um dos dois textos inteiros; destino em pasta inexistente levanta `OSError` sem lixo.
3. **Instância única:** `ui/app.py:main` pega um `QLockFile` em `appdirs` (`<dados>/lain.lock`) logo depois de criar a `QApplication`. Se `tryLock()` falha: `QMessageBox.question`
   "O Lain já está aberto com esta configuração. Abrir mesmo assim?"; **Sim** segue sem trava (e loga), **Não** sai com código 0. Travas velhas (processo morto) o próprio
   `QLockFile` remove. Função `acquire_instance_lock(path) -> QLockFile | None` testável sem janela.

### R5: Renomear sem sobrescrever (S3)
1. `file_ops.rename_item` troca `path.rename(target)` por `_rename_noreplace(src, dst)`:
   - Linux: `renameat2(AT_FDCWD, src, AT_FDCWD, dst, RENAME_NOREPLACE)` via `ctypes` (glibc ≥ 2.28); `EEXIST` → o mesmo erro "já existe" de hoje;
   - se `renameat2` não existe ou o sistema de arquivos não suporta (`ENOSYS`, `EINVAL`): arquivos por `os.link` + `os.unlink` (o `link` falha se o destino existe), diretórios por
     verificação + `rename` (janela residual documentada);
   - Windows: `os.rename` (já recusa destino existente).
2. Teste: gancho no ponto entre a verificação e a troca cria o destino; o arquivo criado **não** é sobrescrito e o erro é o de "já existe". Os três testes de `test_file_ops.py` continuam.

## Fora de escopo
- Reabrir o pull inteiro ou mudar o planner; o push já é seguro (`--ignore-existing`).
- Trava por pasta entre duas instâncias, ou *merge* de `folders.json`/`navigation.json`/… entre instâncias (a trava só avisa).
- `known_hosts` pela interface (F14 do `report.md`).
- O corpo de `closeEvent` e as demais extrações de `main_window.py`: spec 27-5.

## Decisões assumidas (confirmar na revisão)
1. A segunda instância pergunta em vez de bloquear (o usuário pode querer duas janelas em projetos diferentes).
2. Sync em andamento bloqueia renomear qualquer pasta **sobreposta**; a raiz do projeto (sync do projeto inteiro) bloqueia todas.
3. Arquivos que mudaram durante a prévia são **pulados** (não é erro): o usuário vê quais e roda o sync de novo.
4. Em B7(b) o descarte por sequência vale por arquivo `.plot`, não globalmente.
5. `RENAME_NOREPLACE` via `ctypes` só em Linux; macOS/Windows seguem o ramo de verificação.

## Notas de implementação
- Novos: `ui/rename_controller.py`, `tests/test_appdirs.py`, `tests/test_rename_blocked.py` (ou dentro de `test_file_grid_menu.py`).
- Alterados: `core/sync/rsync.py`, `core/sync/controller.py`, `core/sync/planner.py` (`local_size`), `core/sync/report.py`, `ui/sync_coordinator.py` (`folder`),
  `ui/plot_export.py` (`running`), `ui/derive_controller.py`, `ui/calc_create_controller.py`, `ui/plot_settings.py`, `core/appdirs.py`, `core/file_ops.py`, `ui/app.py`,
  `ui/main_window.py` (fachada), `tests/ssh_server.py`, `tests/test_sync_ssh.py`, `tests/test_sync_rsync.py`, `tests/sync_helpers.py` e os testes de renomear listados.
- `core/appdirs.py` usa `QLockFile` só em `ui/app.py` (o núcleo de gravação continua Qt-free).
- `CLAUDE.md`: seção de sync (R1.5) e "Context menu (spec 5)" (renomear passa pelo `RenameController`).

## Critérios de aceite e testes
- [ ] Todo argv de ssh/rsync (pull, push, chave, senha) contém `StrictHostKeyChecking=yes`.
- [ ] Com `ssh_config` permissivo (`no`, `accept-new`) e `known_hosts` vazio, pull e push falham sem tentativa de autenticação nem escrita no `known_hosts`.
- [ ] Renomear com sync/push/exportação/derivação/criação sob a pasta é recusado com o motivo; sem elas, funciona como antes.
- [ ] `main_window.rename_path` é uma fachada; `qe_studio.ui.rename_controller.ask_rename` é o alvo dos patches; `main_window.py` perde ≈ 35 linhas.
- [ ] Pull com arquivo editado ou criado entre a prévia e a transferência: não sobrescreve, relatório lista.
- [ ] `PlotSettingsStore`: a escrita velha na fila não sobrescreve a nova.
- [ ] `atomic_write_text`: sem `.tmp` fixo, com `fsync`, queda mantém o conteúdo; segunda instância pergunta; `QLockFile` com trava velha é recuperada.
- [ ] `rename_item` não sobrescreve um destino criado na janela.
- [ ] `ruff`, `pyright`, `test_architecture.py` (incl. `core/` sem `ui`) sem regressão.
