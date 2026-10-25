# Spec 69: modo cluster: "Submeter…" no `.qsub` roda `chmod a+x` e `qsub` na pasta, com confirmação e bloqueada se a pasta já tem um job rodando

| | |
|---|---|
| **Prioridade** | 69: a primeira da rodada; abre a base que a spec 70 usa (um comando que **muda** algo no cluster, nomes vindos do cluster validados, o gancho no menu remoto, o servidor SSH dos testes com `cd … &&` e a guarda que impede os testes de chegar ao cluster) |
| **Status** | Implementada (25/10/2026). Desvios: `SubmitPlan` guarda `steps` (as três partes) e `line` é propriedade (o diálogo mostra uma por linha sem recortar um `remote_root` citado que tenha ` && `); `checked_dir` devolve a palavra de shell já citada; a guarda (`tests/cluster_guard.py`) confere `run_command` trocando o `subprocess` de `core/sync/command.py` por um proxy (todo chamador passa por ele, mesmo os que importam `run_command` por nome ou depois da fixture), registra a violação, levanta `ClusterGuardError` (uma `AssertionError`: num worker vira `on_error`) e falha o teste no teardown; a sonda proibida devolve `False` sem conectar; os dois `config.example.yaml` versionados (com `cluster.example.org`) são aceitos por `find_config`; a guarda pegou dois vazamentos reais: `test_language.test_startup_language_order` lia o `config.yaml` da raiz (cwd do repositório) e os testes de `test_first_run.py` deixavam a sonda do LED conectar em `cluster.example.org` (vindo do modelo do config): o primeiro roda numa pasta vazia, os outros têm a sonda falsa; uma falha do plano também alimenta o LED e esquece a senha recusada, como a do `qsub`, com o toast "A submissão falhou: …"; `ssh_server._allowed` e `_split_and` (o servidor tem 452 linhas) e duas recusas novas em `tests/test_ssh_server.py`; `cluster_guard` em `known-local-folder` do ruff; o README registra que o bloqueio depende do nome do job no `qstatus` igual ao `-N` do script; `remote_controller.py` 487/500, `main_window.py` 446/450, `config.py` 486/500 |
| **Depende de** | spec 65 (modo cluster: `RemoteController.show_menu`, `RemoteBrowser`, `list_remote`), spec 64 (`core/sync/command.py`: `remote_command`, `run_command`; `fetch_jobs`; `JobsController.refresh`; `SyncCoordinator.session_password`/`forget_password`), spec 27-3 (`StrictHostKeyChecking=yes`, senha só por `SSH_ASKPASS`), spec 7 R7 e 64 R7 (servidor SSH local dos testes, `extra_commands`) |
| **Usada por** | spec 70 (`core/remote/actions.py` e `ui/job_actions.py`, novos nesta spec; `cluster_jobs.running_in`, o gancho `menu_hooks`, o `cd … &&` do servidor dos testes, a guarda dos testes) |
| **Esforço** | M (R1–R3: P; R4: M; R5–R7: P) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): reescreve uma regra de segurança do `CLAUDE.md` (hoje nada lido do cluster entra num comando), monta comandos de shell remotos com nomes que vêm do cluster, põe uma guarda em toda a suíte de testes e mexe em `ui/remote_controller.py` (477/500) e `ui/main_window.py` (444/450) |

## Itens de origem (`Ideias.md`, 25/10/2026, e revisão de 25/10/2026)

> - Para executar uma simulação no cluster, após enviar o script com os inputs, Eu executo no custer, no diretório onde o script foi enviado, os comandos 'chmod a+x script.qsub' e depois 'qsub script.qsub'. Quando a simulação é submetida com sucesso, o terminal retorna """Your job <job-ID> ("<name_job>") has been submitted"""
>
> ## Nova funcionalidade: Execução de simulações
>
> Quero que no Ambiente Remoto do Lain, o usuario que possa executar as simulações.
>
> O usuario vai até a pasta da simulação que deseja executar (a pasta deve conter um script '.sub'), na lista de opções do botão de ações do botão direito do mouse quando clicar no '.sub' com o botão direito, deve aparecer 'submeter'(ou outro nome que achar melhor). Esse botão vai iniciar a simulação com 'chmod a+x script.qsub' e 'qsub script.qsub'.
>
> Quando o usuario submeter uma simulação, deve aparece uma caixa de dialogo para o usuario confirmando a submissão. Se a submição for bem sucedida, deve aparecer uma notificação para o usuario.

Decisões do usuário na revisão da primeira versão desta spec:

> - Sobre 'Uma regra de segurança do CLAUDE.md muda.' A regra que proibia executar coisas no cluster era apenas para a fase inicial do projeto. Agora, na fase final, vamos implementar algumas funções relacionadas ao cluster.
> - O '.sub' do pedido foi um erro de digitação, o correto é '.qsub'
> - Sobre 'ao submeter, dois avisos que não bloqueiam: um *.EXIT esquecido na pasta e um job seu já rodando nela.' Quero que se já tiver um script em execução dentro da pasta, o usuario não pode executar outro script, para não ter conflitos.
>
> Não quero que nenhum teste seja executado no cluster, mas sim localmente. O Custer é um ambiente de produção/trabalho, nada deve ser executado nele sem permissão do usuario.

Interpretação: o "Ambiente Remoto" é o modo cluster da spec 65 (botão "Cluster" da barra lateral) e o script é o `.qsub`. A "caixa de diálogo
confirmando a submissão" vem **antes** (pergunta), e a "notificação" depois, quando o `qsub` responde que submeteu. O nome do botão é
"Submeter…". "Já tiver um script em execução dentro da pasta" é um job do usuário em "Running jobs" do `qstatus` cujo `<nome>.o<job-ID>` está
na pasta (a única ligação entre um job e uma pasta que o cluster dá). "Nada deve ser executado nele sem permissão" vale para o Lain (todo
comando que muda o cluster só roda depois do clique de confirmação; as consultas de leitura são as de hoje, specs 64 e 65) e para o
desenvolvimento: nenhum teste nem verificação da implementação chega ao cluster (R7).

## Situação atual

- **Nada submete jobs.** `grep -rn "qsub " src/qe_studio --include=*.py` só acha o `.qsub` como tipo de arquivo (`core/file_kinds.py:25`,
  `SCRIPT_SUFFIXES = {".qsub"}`), o `core/qsub_lint.py` e os templates do "Criar cálculo". A spec 64 deixou "enviar com `qsub`" fora de
  escopo ("só leitura").
- **O único comando remoto além do rsync** é o `cluster.jobs_command` (`core/config.py:137`, `"qstatus -a"`), montado por
  `core/sync/command.py:38-45` (`remote_command(config, command)`: `ssh` com as opções de `ssh_command`, `user@host` e o texto) e rodado
  por `run_command` (`:48-76`: sem stdin, sessão própria, cancelável, tempo-limite). O `CLAUDE.md` ("Sync safety", linhas 134-137) diz:
  "A remote command other than rsync comes only from `config.yaml` (`cluster.jobs_command`) … nothing read from the cluster goes into a
  command" e "The cluster mode only lists … and downloads". Um "Submeter" precisa pôr no comando a pasta e o nome do script, que vêm da
  listagem do cluster: as duas regras mudam (R6.1; decisão do usuário: a regra era da fase inicial).
- **O menu do modo cluster.** `ui/remote_controller.py:400-422` (`show_menu`) monta "Baixar", "Plotar" (só pastas) e "Copiar caminho" num
  `QMenu`; `items` são `RemotePath(path, is_dir)` (`ui/widgets/remote_model.py:28`), vindos da árvore (`remote_panels.py:133-137`, sempre
  pasta) ou da grade (`:308-319`, a seleção). Não há gancho para outro módulo acrescentar itens; o arquivo tem **477/500** linhas.
- **O que o `qsub` usa da pasta.** O cabeçalho que o "Criar cálculo" grava (`resources/templates/qsub/_base.qsub.j2:8-12`) e os scripts de
  referência do usuário (`Documentation/Referencia_de_scripts_QSUB/bands.qsub:9-13`) têm `#$ -N "<nome>"`, `#$ -pe physica <NP>`,
  `#$ -cwd` e `#$ -j y`: o job roda na pasta de onde o `qsub` foi chamado (por isso o `cd`), e a saída do escalonador vai para
  `<nome>.o<job-ID>` nessa pasta (o que `core/file_kinds.py:29`, `JOB_STDOUT`, já reconhece), criada quando o job **começa**. Um job ainda
  na fila não deixa nada na pasta, e o `qstatus` não diz a pasta de um job.
- **Saber se já roda algo na pasta.** `core/cluster_jobs.py:59-65` dá `mine(user)` (em execução) e `queued(user)`; nada liga um job a uma
  pasta. Os vestígios na pasta são o `<nome>.o<job-ID>` e, se um cancelamento anterior não foi consumido, um `<prefix>.EXIT` (spec 70), que
  **para o próximo pw.x logo na primeira verificação**: o `pw.x` 7.1 procura `TRIM(prefix)//'.EXIT'` primeiro na pasta de trabalho e depois
  em `tmp_dir`, e o apaga ao achar (`Modules/check_stop.f90`, `check_stop_now`, lido no `qe-7.1` do GitHub do QEF).
- **Avisar o usuário.** `ui/widgets/toast.py:166` (`Toast.show_message(text, level, details)`), usado pelo `RemoteController`
  (`window.toast`); a confirmação modal segue `ui/dialogs/overwrite.py:69-78` (`exec`, lê, depois `deleteLater`).
- **Servidor SSH dos testes.** `tests/ssh_server.py:329-359` (`_serve_exec`): `shlex.split` do comando; o único composto aceito é
  `mkdir -p <dir> && rsync --server …` (`:335-337`); `extra_commands` mapeia `argv[0]` (`:338-339`); `_run` (`:368`) roda sempre em
  `cwd=self.root` (`:372`). Um `cd <dir> && chmod … && qsub …` hoje volta com 127.
- **Os testes e o cluster real (R7).** Há um `config.yaml` com o cluster do usuário na raiz do repositório (git-ignorado), e a suíte roda com
  essa pasta como `cwd`. `tests/conftest.py:19` só desliga o passo do checkout (`QE_STUDIO_NO_CHECKOUT_CONFIG`); um `QE_STUDIO_CONFIG` do
  ambiente do desenvolvedor não é removido, e `find_config` olha `./config.yaml` (`core/config.py:343`). O `window_factory`
  (`conftest.py:144-206`) cria a janela com `LoadedConfig(config, None)`: um `reload_config()` nela faria `load_config(None)` e leria o
  `config.yaml` real. Hoje isso é evitado teste a teste (`tests/test_main_window.py:80-86` troca `load_config`; `test_first_run.py:25-27`
  muda o `cwd` e apaga a variável; o `window_factory` troca `fetch_jobs`, `conftest.py:159-167`), sem uma guarda geral. As saídas para a rede
  são três: `run_command` (`core/sync/command.py:48`), `RsyncRun._launch` (`core/sync/_process.py:252`, `process.start` em `:300`) e
  `monitor.probe` (`core/sync/monitor.py:35`, conexão TCP). Hosts que os testes usam hoje (`grep` em `tests/*.py`): `hpc.example`, `hpc`,
  `127.0.0.1`, `10.0.0.1`, `cluster.test`, `h`; não verificado se algum teste lança um processo ou uma sonda com `hpc`, `h` ou `10.0.0.1`
  (que podem existir numa rede real).
- **Não verificado:** se o `qsub` (e o ambiente do SGE) está no `PATH` de um `ssh` sem terminal no cluster do usuário; o `qstatus` está
  (a spec 64 funciona), mas é um script do cluster. A forma da resposta de um job-array (`Your job-array …`) não foi vista.
- Tamanhos: `ui/remote_controller.py` 477, `ui/main_window.py` 444/450, `core/config.py` 484, `core/cluster_jobs.py` 163,
  `core/sync/command.py` 91, `ui/shutdown.py` 135, `tests/ssh_server.py` 403.

## Requisitos

### R1: comandos que mudam o cluster, com nomes do cluster validados

1. Novo `core/remote/actions.py` (Qt-free, em `QT_FREE` de `tests/test_architecture.py`):
   - `SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._+-]*$")` e `checked_name(name) -> str`: devolve `name` ou levanta `ValueError`
     ("Nome não suportado para um comando no cluster: {name} (use letras, números, '.', '_', '+' e '-')."). Vale para todo valor que veio
     do cluster e entra num comando (nome de arquivo, de pasta abaixo de `paths.remote_root`; na spec 70, `prefix` e job-ID).
   - `checked_dir(config, remote_dir) -> str`: `remote_dir` está em `paths.remote_root` ou abaixo dele (senão `ValueError`), e cada
     componente **abaixo** de `remote_root` passa por `checked_name`; `remote_root` vem do `config.yaml` e não é validado, só citado.
   - Todo valor entra no texto do comando por `shlex.quote`, mesmo depois de validado.
   - `ActionFailure(message, connection=False, auth=False, missing=False, local=False)` e
     `classify_failure(result, command, setting) -> ActionFailure` para um `CommandResult` que não deu certo, pelas mesmas regras de
     `core/cluster_jobs.py:127-147` (tempo esgotado → `connection`; `is_auth_failure` → `auth`; 127 ou "command not found" → `missing`,
     "O comando {command} não foi encontrado no cluster ({setting})."; `is_connection_failure` → `connection`; senão "{command} terminou
     com código {code}: <última linha do stderr>"). `setting` é a chave do `config.yaml` (`cluster.submit_command`). O `classify` dos jobs
     não muda (as mensagens de hoje ficam como estão).
   - `run_action(config, command, password) -> CommandResult | ActionFailure`: `remote_command` + `child_env` + `run_command` com
     `connect_timeout + 30` s; `OSError` → `ActionFailure(local=True)`.
2. O texto dos programas (`qsub`, na spec 70 `qdel`) vem do `config.yaml`; `cd`, `chmod a+x` e (spec 70) `touch` são fixos. Nenhum texto
   lido do cluster vira programa ou opção: só argumento, validado e citado.
3. **Testes** (`tests/test_remote_actions.py`, novo, sem rede): `checked_name` aceita `scf.qsub`, `1_Bands_Al`, `hBN+Sm-1`,
   `vc-relax.qsub` e recusa `-x.qsub`, `.oculto`, `a b.qsub`, `a;b`, `$(id)`, `` a`b ``, `a'b`, `a\nb` e o vazio; `checked_dir` recusa
   `remote_root/../x`, um caminho fora de `remote_root` e um componente inseguro, e cita um `remote_root` com espaço
   (`'/home/u/my runs'/ilita`); **propriedade** (Hypothesis): para todo nome que passa em `checked_name`, `shlex.split` da linha de
   submissão (R2.1) dá exatamente os tokens `["cd", <pasta>, "&&", "chmod", "a+x", <nome>, "&&", "qsub", <nome>]`; as falhas classificadas
   a partir de `stderr` e código.

### R2: submeter, nunca sobre um job em execução na mesma pasta

1. `core/remote/submit.py` (novo, Qt-free, em `QT_FREE`):
   - `submit_line(config, remote_dir, script) -> str`:
     `f"cd {quote(dir)} && chmod a+x {quote(script)} && {cluster.submit_command} {quote(script)}"`, com `checked_dir` e `checked_name`.
   - `Submitted(job_id: str, name: str)` e `parse_submitted(stdout) -> Submitted | None`: a linha
     `Your job <job-ID> ("<name_job>") has been submitted` (`^Your job (\d+) \("(.*)"\) has been submitted`), em qualquer linha do stdout.
   - `SubmitBlocked(message)` e `folder_check(config, remote_dir, password) -> tuple[str, ...] | SubmitBlocked | ActionFailure`: lista a
     pasta **de novo** (`list_remote`, nunca o cache) e consulta a fila **de novo** (`fetch_jobs`). Devolve os arquivos da pasta chamados
     `EXIT` ou terminados em `.EXIT` (para o aviso do R4.4), ou:
     - `SubmitBlocked` quando `cluster_jobs.running_in(nomes, snapshot, cluster.user)` (R2.2) não é vazio: "Já há um job seu em execução
       nesta pasta: {name} (job {job_id}). Espere ele terminar ou cancele-o antes de submeter outro script." (o primeiro);
     - `SubmitBlocked` quando a fila não pôde ser lida (`JobsFailure`): "Não foi possível conferir se já roda um job nesta pasta:
       {message}. Nada foi submetido." Sem a fila conferida, não se submete;
     - `ActionFailure` quando a listagem falha.
   - `SubmitPlan(remote_dir, script, line, exit_files: tuple[str, ...])` e `plan_submit(config, remote_dir, script, password) -> SubmitPlan |
     SubmitBlocked | ActionFailure`: `folder_check` e `submit_line`.
   - `submit(config, plan, password) -> Submitted | str | SubmitBlocked | ActionFailure`: `folder_check` **de novo**, logo antes de agir
     (um job pode ter começado na pasta enquanto o diálogo estava aberto); bloqueado → `SubmitBlocked` e nada roda. Senão roda `plan.line`
     com `run_action`: código 0 com a linha reconhecida → `Submitted`; código 0 sem ela → a primeira linha não vazia do stdout (`str`);
     código ≠ 0 → `classify_failure(result, cluster.submit_command, "cluster.submit_command")`.
2. `core/cluster_jobs.py`: `running_in(file_names, snapshot, user) -> tuple[Job, ...]`: os jobs **em execução** de `user` para os quais a
   pasta tem `<name>.o<job_id>` (`^(?P<name>.+)\.o(?P<id>\d+)$`; `job.name == name` e `job.job_id == id`, as duas iguais). Um `.o` de uma
   execução antiga (ID fora da fila), um `.e<id>`, um job de outro dono ou um nome diferente com o mesmo ID não contam.
3. `core/config.py:ClusterConfig`: `submit_command: str = "qsub"` (vazio desliga o "Submeter"), no mesmo validador `_strip_command` do
   `jobs_command`. O "Submeter" também precisa do `jobs_command` (é a fila que diz se já roda um job na pasta). Nos dois
   `config.example.yaml`, em `cluster:`, com o comentário: roda na pasta do script, pelo ssh, depois de `chmod a+x`, só depois da
   confirmação e só se nenhum job do usuário roda nessa pasta (conferido no `jobs_command`); um `qsub` fora do `PATH` de um ssh sem
   terminal precisa do caminho completo (como o `jobs_command`).
4. **Testes** (`tests/test_remote_submit.py`, novo, com `list_remote`, `fetch_jobs` e `run_action` falsos): a linha exata para
   `"/home/u/runs/ilita/Bands"` e `"bands.qsub"`; `parse_submitted` da resposta do pedido, de uma resposta com uma linha antes, e `None`
   para `Your job-array 1.1-10:1 ("x") has been submitted`; o plano com `pwscf.EXIT` na pasta dá `exit_files`; com `Bands-kao-b.o24000` e o
   job 24000 do usuário em execução, `plan_submit` dá `SubmitBlocked` e nenhum comando é montado; com a fila em `JobsFailure`,
   `SubmitBlocked`; **o job começa entre o plano e a confirmação** (a segunda consulta já o tem em execução): `submit` dá `SubmitBlocked` e
   `run_action` **não** é chamado; falha da listagem → `ActionFailure`; `submit` nos três casos de resposta. `tests/test_cluster_jobs.py`:
   os casos de `running_in` do R2.2, com `jobs_helpers.with_mine`.

### R3: o gancho do menu remoto

1. `ui/remote_controller.py`: `self.menu_hooks: list[Callable[[QMenu, list[RemotePath]], None]] = []`; `show_menu` chama cada gancho
   depois de "Plotar" e antes de "Copiar caminho", com um separador antes do primeiro item que um gancho acrescentar e outro antes de
   "Copiar caminho" (o menu sem ganchos fica como hoje). Esperado: cerca de 482/500 linhas.
2. **Testes** (`tests/test_remote_ui.py`): sem gancho, os itens do menu são os de hoje (`remote_helpers.menu_spy`); um gancho de teste
   recebe os itens e o seu item aparece entre "Plotar" e "Copiar caminho".

### R4: "Submeter…" no menu e o diálogo de confirmação

1. Novo `ui/job_actions.py:JobActionsController.for_window(window)` (uma linha em `MainWindow`, depois de `self.remote`, cerca de 445/450): registra
   o gancho em `window.remote.menu_hooks`; lê a configuração por `window.config` no momento de agir (sem linha nova em `_apply_loaded`). Um
   pool próprio de 1 thread (sem pai Qt) e um `TaskGroup` com a chave `"action"`: uma ação de cada vez.
2. O gancho acrescenta "Submeter…" **só** quando há um item, ele é um arquivo e o nome termina em `.qsub`. Desabilitado, com o motivo no
   tooltip:
   - `submit_command` vazio: "Submissão desligada: cluster.submit_command está vazio no config.yaml.";
   - `jobs_command` vazio: "Submeter precisa de cluster.jobs_command: é o qstatus que diz se já roda um job nesta pasta.";
   - nome ou pasta recusados pelo R1: a mensagem do `ValueError`;
   - uma ação em andamento: "Aguarde: uma ação no cluster está em andamento.".
3. O clique: com `auth: password` e sem senha conhecida, `window.sync.session_password(ask=True)` (cancelar não faz nada); depois
   `plan_submit` no worker, com `BusyTracker` "Conferindo a pasta no cluster…". `SubmitBlocked`: toast `warning` com a mensagem, e **nenhum
   diálogo abre**. `ActionFailure`: toast `error`.
4. Novo `ui/dialogs/cluster_action.py:ask_submit(parent, plan, account) -> bool` (`QDialog` modal com `exec()`; lê a resposta, depois
   `deleteLater()`), título "Submeter no cluster":
   - "Submeter {script}?" e "Pasta: {account}:{remote_dir}";
   - "Comandos que vão rodar no cluster:" e, em fonte monoespaçada, as três partes de `plan.line` uma por linha (`cd …`, `chmod a+x …`,
     `qsub …`), o texto exato que vai para o ssh;
   - um aviso em `warning` por arquivo de `exit_files`: "A pasta tem {name}: o pw.x vai parar na primeira verificação. Apague o arquivo no
     cluster antes de submeter.";
   - botões "Submeter" e "Cancelar"; o padrão é "Cancelar" quando há aviso, "Submeter" quando não há.
5. Confirmado: `submit` no worker ("Submetendo no cluster…"). Respostas:
   - `Submitted`: toast `info` "Job {job_id} ({name}) submetido." e a mesma frase no rodapé;
   - `str` (código 0, resposta não reconhecida): toast `warning` "O qsub terminou sem erro, mas a resposta não foi reconhecida: {line}";
   - `SubmitBlocked` (um job começou na pasta depois do diálogo): toast `warning` com a mensagem; nada foi submetido;
   - `ActionFailure`: toast `error` "A submissão falhou: {message}"; `auth` esquece a senha (`forget_password`); `connection` chama
     `window.sync.monitor.report(False)`, as outras respostas `report(True)` (como os jobs e as listagens).
   - Em todos os casos em que o `qsub` rodou com código 0: `window.jobs.refresh()` (o job novo aparece na fila) e a pasta é listada de
     novo se o modo cluster a mostra (`window.remote.refresh()`), senão sai do cache (`window.remote.browser.invalidate(remote_dir)`).
6. Fechamento: o passo "cancelar" de `ui/shutdown.py:steps_for` chama `window.job_actions.cancel()` (o `ssh` morre pelo `run_command`). Um
   `qsub` que já chegou ao cluster pode ter submetido: a fila da próxima sessão mostra.
7. **Testes** (`tests/test_job_submit.py`, novo, com `remote_helpers.remote_window`, `menu_spy`, `jobs_helpers.FakeFetch` e
   `ask_submit` trocado em `qe_studio.ui.job_actions.ask_submit`): "Submeter…" aparece num `.qsub` e não num `.in`, numa pasta nem com
   dois itens; os quatro motivos de desabilitado; uma pasta com job do usuário em execução dá o toast de bloqueio e o diálogo **não** é
   chamado; o plano chega ao diálogo com o aviso de `*.EXIT`; recusar não roda nada; confirmar roda `remote_command(config, plan.line)` e
   mostra o toast com o job; o job que começa entre o diálogo e a confirmação dá o toast de bloqueio e nenhum `qsub`; a fila é consultada de
   novo; falha de login esquece a senha; com `auth: password` sem senha, o diálogo de senha é pedido uma vez.

### R5: o servidor SSH dos testes aceita `cd <pasta> && …`

1. `tests/ssh_server.py:_serve_exec`: um comando `cd <pasta> && A && B …` (tokens `&&` do `shlex.split`) roda cada parte em sequência na
   `<pasta>` (que precisa estar dentro da pasta servida, como o `mkdir -p` de hoje), parando na primeira com código ≠ 0; cada parte precisa
   ser permitida (`extra_commands` ou `PROBE_COMMANDS`), senão o comando inteiro volta com 127 e nada roda. `_run` ganha `cwd`. O
   cabeçalho do arquivo documenta a forma.
2. **Teste de ponta a ponta, local** (`tests/test_job_submit_ssh.py`, novo): `extra_commands={"chmod": ["chmod"], "qsub": [sys.executable,
   <script>]}`, em que o `qsub` falso grava o `cwd` e o nome recebido e imprime `Your job 1 ("teste") has been submitted`; pelo `ssh` real,
   contra o `tests/ssh_server.py` em `127.0.0.1`, com chave e com senha: `submit` devolve `Submitted("1", "teste")`, o `cwd` gravado é a
   pasta do script, o script ficou executável, a senha não aparece em `argv` nem no log (como `tests/test_cluster_jobs_ssh.py:79-80`).

### R6: regras e documentação

1. `CLAUDE.md`, "Sync safety": a linha do comando remoto passa a "A remote command other than rsync is built only from programs named in
   `config.yaml` (`cluster.jobs_command`, `cluster.submit_command`) plus the fixed `cd` and `chmod a+x`, in `core/remote/actions.py` and
   `core/sync/command.py`; a value read from the cluster (a file or folder name) enters only as an argument, after `checked_name` and
   `shlex.quote`. A command that changes the cluster runs only after the user confirms it." e a do modo cluster a "The cluster mode lists,
   downloads through the usual pull (or into `tmp_remote/` to plot) and submits a `.qsub` after a confirmation (`chmod a+x`, then `qsub`,
   in its folder), never while a job of the user runs in that folder."
2. `CLAUDE.md`, "Testing", uma linha nova: "The cluster is production: no test or verification ever reaches it. Tests talk only to
   `tests/ssh_server.py` (`127.0.0.1`) or fakes; the autouse guard in `tests/conftest.py` fails a test that reads the real `config.yaml` or
   contacts any other host (spec 69 R7)."
3. PRD §5.1 (`specs/Archived/spec_0-PRD.md:89-90`): a linha do modo cluster ganha "and submits a `.qsub` (spec 69) after a confirmation,
   never while a job of the user runs in that folder".
4. `README.md`, "Cluster mode": o item "Submeter…" (o que roda, o bloqueio, o aviso do `.EXIT`, a chave `submit_command` e o `PATH`).

### R7: nenhum teste chega ao cluster

1. `tests/conftest.py`, uma fixture `autouse` (a guarda):
   - remove `QE_STUDIO_CONFIG` do ambiente de cada teste;
   - envolve `qe_studio.core.config.find_config`: um resultado que não está dentro de uma pasta temporária do pytest nem de `tests/` (o
     `config.yaml` da raiz do repositório, o `~/.config/qe-studio/config.yaml` de verdade) falha o teste com "Um teste leu o config.yaml
     real ({path}): o cluster é ambiente de produção (spec 69 R7).";
   - envolve as três saídas para a rede, onde são importadas: `run_command` (`core/sync/command.py`), `RsyncRun._launch`
     (`core/sync/_process.py`) e `monitor.probe` (`core/sync/monitor.py`). O host contatado (o `user@host` do `argv`, o `Endpoint.host`, o
     `host` da sonda) precisa ser de teste: `127.0.0.1`, `localhost`, `ssh_server.HOST_ALIAS`, ou um nome sob os domínios reservados
     `.invalid`, `.example` ou `.test` (RFC 2606/6761, nunca resolvem); um `Endpoint` sem host (pasta local) passa. Qualquer outro falha o
     teste **antes** de o processo ou a conexão começar, com "Um teste tentou falar com {host}: os testes nunca chegam ao cluster (spec 69
     R7)."
2. A suíte inteira roda com a guarda. Um teste que hoje lança um processo ou uma sonda com outro host (`hpc`, `h`, `10.0.0.1`: medir) passa a
   usar um nome `.invalid`; um teste que lê o `config.yaml` real passa a usar um em `tmp_path`. A guarda nunca é afrouxada para um teste
   passar.
3. **Testes** (`tests/test_test_guard.py`, novo): dentro de um teste, `run_command` com `usuario@cluster.real.org` falha pela guarda e
   nenhum processo nasce (um `Popen` espião não é chamado); `monitor.probe("cluster.real.org", 22)` falha; `RsyncRun` com um `Endpoint` de
   host real falha antes do `QProcess.start`; `find_config(None, {}, cwd=<raiz do repositório>)` com um `config.yaml` lá falha (um
   `config.yaml` falso numa cópia temporária da estrutura, sem depender do arquivo do usuário); `127.0.0.1`, `HOST_ALIAS`, `hpc.example` e
   `x.invalid` passam.

## Fora de escopo

- Cancelar jobs (o `prefix.EXIT` e o `qdel`): spec 70.
- Bloquear a submissão quando um job da mesma pasta ainda está **na fila**: ele não deixa nada na pasta e o `qstatus` não diz a pasta dele
  (o `qstat -j <id>` diria o `cwd`; o formato deste cluster não foi visto). O bloqueio cobre o job em execução, como pedido; o job da fila
  aparece no popup da barra superior.
- Submeter pelo modo local (um `.qsub` da pasta local, que primeiro precisaria ser enviado): o pedido é no "Ambiente Remoto". O caminho de
  hoje continua "Enviar ao cluster" e depois "Submeter…" no modo cluster.
- Submeter vários scripts de uma vez, job-arrays (`-t`), opções extras do `qsub` (`-hold_jid`…) e editar o script antes: um script, como
  está no cluster.
- Ler o `#$ -N` do script para mostrar o nome antes de submeter: o nome chega na resposta do `qsub`.
- Apagar o `<prefix>.EXIT` esquecido: o Lain nunca apaga nada no cluster; o diálogo avisa.
- Notificação do sistema (D-Bus): o aviso é o toast do Lain.
- Outros escalonadores (Slurm `sbatch`): o programa é configurável, mas a resposta lida é a do SGE.
- Qualquer passo de aceite no cluster real: ele é ambiente de produção (decisão do usuário); a implementação se prova só localmente, e o
  primeiro uso de verdade é do usuário, quando ele quiser.

## Decisões assumidas (confirmar na revisão)

Decididas pelo usuário na revisão (25/10/2026):

1. **A regra do `CLAUDE.md` muda:** a proibição de executar coisas no cluster era da fase inicial; programas do `config.yaml`, argumentos do
   cluster validados e citados, e só depois da confirmação.
2. **Só `.qsub`:** o '.sub' do pedido foi erro de digitação.
3. **Um job do usuário em execução na pasta bloqueia a submissão** (sem diálogo, só o toast), conferido no plano e de novo logo antes do
   `qsub`.
4. **Nenhum teste chega ao cluster** (R7), e nenhuma spec tem passo de aceite nele.

Assumidas nesta versão:

5. **Sem a fila conferida, não se submete** (falha do `qstatus` ou `jobs_command` vazio): é a consequência do bloqueio da decisão 3; sem a
   consulta, o Lain não sabe se há conflito.
6. **O `*.EXIT` esquecido na pasta só avisa** (não bloqueia): a revisão só pediu o bloqueio do job em execução.
7. **"Submeter…" só num `.qsub` do modo cluster**, com um item selecionado; não aparece em pastas.
8. **A notificação é um toast** (com a mesma frase no rodapé), não uma janela.
9. **Nomes com espaço ou caracteres de shell são recusados** (pastas abaixo de `remote_root` e o script), mesmo citados: o login do cluster
   pode não ser `bash`. O `remote_root` do `config.yaml` só é citado.
10. **`submit_command` configurável** (padrão `qsub`), como o `jobs_command`, porque o `PATH` de um ssh sem terminal pode não ter o SGE (não
    verificado). `cd` e `chmod a+x` são fixos.
11. **Uma ação no cluster de cada vez**, num pool próprio; um segundo clique espera (item desabilitado com o motivo).

## Notas de implementação

- Novos: `core/remote/actions.py`, `core/remote/submit.py` (novos, Qt-free, em `QT_FREE`); `ui/job_actions.py`,
  `ui/dialogs/cluster_action.py` (novos); `tests/test_remote_actions.py`, `tests/test_remote_submit.py`, `tests/test_job_submit.py`,
  `tests/test_job_submit_ssh.py`, `tests/test_test_guard.py` (novos).
- Alterados: `core/cluster_jobs.py` (`running_in`), `core/config.py` (`submit_command`, cerca de 486/500) e os dois `config.example.yaml`,
  `ui/remote_controller.py` (`menu_hooks`), `ui/main_window.py` (`self.job_actions`), `ui/shutdown.py`, `tests/conftest.py` (a guarda),
  `tests/ssh_server.py` (`cd … &&`, `_run(cwd)`), `tests/test_cluster_jobs.py`, `tests/test_remote_ui.py`, `tests/test_config.py`,
  `tests/test_architecture.py` (`QT_FREE`), os testes que a guarda pegar (R7.2), catálogo `lain.po`/`.mo`.
- Ordem: **R7 primeiro** (a guarda, com a suíte verde, antes de existir qualquer comando que mude o cluster) → R1 e R2 (sem Qt) → R5
  (servidor) → R3 → R4 → R6.
- Durante a implementação, nada roda contra o cluster do usuário: nem `uv run lain` com o `config.yaml` da raiz, nem `ssh` para o host dele.
  Para ver a janela, use `scripts/screenshot.py` ou um `config.yaml` temporário sem cluster.
- Limites: `ui/remote_controller.py` 477 → cerca de 482/500 (só o gancho; a lógica fica em `ui/job_actions.py`); `ui/main_window.py` 444 →
  445/450; `core/config.py` 484 → cerca de 486/500.
- Nenhum `ui/` novo toca o disco; tudo o que fala com o cluster roda no worker.
- Documentação ao implementar: `CLAUDE.md` (R6.1 e R6.2), PRD §5.1 (R6.3), `README.md` (R6.4), `specs/README.md` (a spec vai para `Archived/`).
- i18n: textos novos em `_()`, `scripts/i18n.py update`, tradução ("Submeter…" → "Submit…", "Submeter no cluster" → "Submit to the
  cluster"), `compile` e `check`.

## Critérios de aceite e testes

- [ ] A guarda vale para a suíte inteira: um teste que lê o `config.yaml` real ou fala com um host que não é de teste falha antes de
      contatar a rede (`tests/test_test_guard.py`), e a suíte passa com ela.
- [ ] Com o modo cluster desligado, ou sem gancho, nada muda: o menu remoto tem os itens de hoje e a suíte existente passa sem mudar
      expectativas (`tests/test_remote_ui.py`, `tests/test_cluster_jobs.py`).
- [ ] Nomes vindos do cluster só entram validados e citados; a linha de submissão não se deixa quebrar (`tests/test_remote_actions.py`,
      propriedade com Hypothesis).
- [ ] "Submeter…" aparece só num `.qsub` do modo cluster, desabilitado com o motivo quando não pode (`tests/test_job_submit.py`).
- [ ] Com um job do usuário em execução na pasta (ou sem a fila conferida), nada é submetido nem no plano nem logo antes do `qsub`
      (`tests/test_remote_submit.py`, `tests/test_job_submit.py`).
- [ ] O diálogo mostra a pasta, os comandos exatos e o aviso de `*.EXIT` (`tests/test_job_submit.py`).
- [ ] Confirmar roda `cd … && chmod a+x … && qsub …` na pasta; a resposta vira o toast "Job {id} ({nome}) submetido." e a fila é
      consultada de novo (`tests/test_job_submit.py`).
- [ ] Pelo `ssh` real contra o servidor local (`127.0.0.1`), com chave e senha, o `qsub` falso roda na pasta do script, que fica
      executável, sem a senha em `argv` ou no log (`tests/test_job_submit_ssh.py`).
- [ ] Fechar a janela com uma submissão pendurada termina dentro do orçamento (`tests/test_shutdown.py`, novo caso).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes, tudo localmente.
