# Spec 64: jobs do cluster na barra superior ("Executando: <nome>") e a fila inteira num clique

| | |
|---|---|
| **Prioridade** | 64: funcionalidade nova, média, independente das specs 61–63; abre a folga em `ui/main_window.py` (R0) e o executor de comandos remotos (R1) que a spec 65 usa |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 33 R3 (o LED sozinho na barra superior, `usuario@host` no tooltip), spec 17 e 27-3 (`ssh_command`, `child_env`, senha da sessão, `StrictHostKeyChecking=yes`), spec 27-5 (passos do fechamento), spec 7 R7 (servidor SSH local dos testes) |
| **Usada por** | spec 65 (R0: folga em `main_window.py`; R1: `core/sync/command.py`, novo) |
| **Esforço** | M/G (R0: P; R1–R3: P; R4–R6: M) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): abre um caminho novo (um comando remoto que não é o rsync, com senha, falhas de conexão e cancelamento), mexe no servidor SSH dos testes e em `ui/main_window.py` (449/450) |

## Itens de origem (`Ideias.md`, 25/10/2026)

Nos exemplos, os logins de outros usuários do cluster foram trocados por `usuario_a` e `usuario_b`, e o do usuário e o nome da máquina
por `usuario@cluster` (dados pessoais, como na spec 27-9); o resto é literal.

> No terminal, uso o comando 'qstatus -a' para visualizar todos os jobs que estão sendo executados e a fila de jobs, e 'qstatus' para visualizar apenas os jobs do meus usuario, os que estão na espera e estão sendo executados. Por exemplo:
>
> ```text
> usuario@cluster:~$ qstatus -a
> Running jobs:
>  job-ID  # name                      owner      start time          running in
> ------------------------------------------------------------------------------
>   23538 32 Nd2Fe14B-4f-129           usuario_a  10/15/2026 17:53:02 physica.q
>   23591 32 hBN+Sm-1                  usuario_b  10/20/2026 11:29:17 physica.q
>   23592 32 hBN+Eu-1                  usuario_b  10/22/2026 08:34:47 physica.q
>
> Waiting jobs:
>  job-ID  # name                      owner      submit time
> -------------------------------------------------------------------
>   23542 32 Sm3NbO8-HP-130            usuario_a  10/15/2026 18:05:21
>   23543 32 BNNT90-S-375              usuario_a  10/15/2026 18:07:00
> ```
>
> ```text
> usuario@cluster:~$ qstatus
> Waiting jobs for user: usuario
>  job-ID  # name                      submit time
> --------------------------------------------------------
>   23644 32 Bands-kao-b               10/22/2026 23:39:04
>   23645 32 PDS-B                     10/22/2026 23:43:43
>   23646 32 Bands-kao-001-p           10/22/2026 23:46:20
> ```
>
> - Na barra superior, tem um ponto que ficar verde ou vermelho para indicar a conexão com cluster. O ponto que indicar a conexão com cluster, ficar verde se estiver conectado, e vermelho se não estiver.
> - Quero que do lado esquerdo desse botão apareça o 'name' do job, do meu usuario, que está sendo executado, com um formato 'Running: <name>', ou 'No job running' (Se o usuario não estiver rodando nenhum job). Se Tiver mais de um job rodando, o conteudo de Running fica variando entre os jobs que estão sendo executados, de 5 em 5 segundos (Podendo ser configurado em 'config.yaml'), por exemplo.
> - E quando clicar em cima de 'Running: <name>' ou 'No job running' abre uma lista suspensa com todos os jobs do cluster (qstatus -a), com um formato parecido com o do comando 'qstatus -a', onde vai mostrar o 'name', 'owner', 'submit time' e 'running in'. Como o conteudo da lista precisa ser consultada no cluster sempre, matenha o conteudo tela salva temporariamente durante cada sessão, atualizando a cada 5 min (Podendo ser configurado em 'config.yaml').

Interpretação: o primeiro item descreve o LED de hoje e pede que ele fique verde quando há conexão e vermelho quando não há; "do lado
esquerdo desse botão" é à esquerda do LED. 'Running: <name>' e 'No job running' são os textos que o usuário vê na interface em inglês
(`ui.language: en`); a fonte em português é "Executando: {name}" e "Nenhum job em execução" (o `.po` dá exatamente o texto pedido). "Lista
suspensa" é um painel que abre embaixo do texto. "Salva temporariamente durante cada sessão" é em memória, nunca em disco.

## Situação atual

- **LED.** `ui/widgets/bars.py:216` cria o `StatusLed`; `:226` o põe entre o botão "Plotar SCF" e o separador dos botões de painel
  (`:229`). Cores por estado em `LED_TOKENS` (`:28`): `online` verde (`success`), `offline` vermelho (`error`), `syncing` amarelo,
  `unknown`/`disabled` cinza. O estado vem de `core/sync/monitor.py`: uma conexão TCP na porta do SSH (sem login) a cada
  `cluster.status_poll_seconds` (300 s, `core/config.py:119`) enquanto a janela está ativa (`:129`), e `report(reachable)` (`:110`)
  com o resultado de um sync de verdade. Ou seja, já fica verde com o cluster acessível e vermelho sem ele; nada hoje faz login para
  conferir.
- **Nada consulta jobs.** Não há `qstatus`, `qstat` nem fila de jobs no código (`grep -ri qstat src/` vazio). O `report.md` adiou o
  "Monitor de jobs" (F11, "scheduler decidido: SGE", `specs/README.md`). O formato acima é o do `qstatus` deste cluster (um script do
  cluster, não verificado: provavelmente um invólucro do `qstat` do SGE); não há exemplo da saída **com** um job do usuário em execução.
- **Executar um comando no cluster.** Só o rsync roda no cluster hoje, por `QProcess` (`core/sync/_process.py`). As peças que um
  comando novo reaproveita: `ssh_command` (`core/sync/rsync.py:74`: `StrictHostKeyChecking=yes`, `ConnectTimeout`, `BatchMode` com
  chave), `child_env` (`:115`: `LC_ALL=C.UTF-8`, `TZ=UTC`, senha só por `SSH_ASKPASS`) e as falhas (`FAILURE_HINTS` `:324`,
  `is_auth_failure` `:359`, `is_connection_failure` `:366`, `explain_failure` `:375`, que falam de rsync: "rsync não está instalado no
  cluster.", "rsync terminou com código…"). A senha digitada vale para a sessão em `SyncCoordinator._session_password`
  (`ui/sync_coordinator.py:76`, pedida em `_ask_password` `:250`, esquecida após falha de autenticação `:311`).
- **Servidor SSH dos testes.** `tests/ssh_server.py:35` só permite `true` e `echo` além do `rsync --server` (`:327`); qualquer outro
  comando volta com 127 e não roda.
- **`ui/main_window.py` tem 449/450 linhas.** O rodapé do caminho mora nele: `_relative` (`:280`), `_on_file_selected` (`:296`),
  `_on_selection_changed` (`:300`), as ligações (`:223-224`) e a linha do rodapé em `on_folder_selected` (`:294`), cerca de 20 linhas que
  só formatam o texto do rodapé. Testes que guardam esse texto: `tests/test_multi_selection.py:52-60`, `tests/test_main_window.py:109`,
  `tests/test_file_grid_menu.py:92`.
- Tamanhos: `ui/widgets/bars.py` 373, `core/sync/rsync.py` 383, `core/config.py` 430, `ui/shutdown.py` 133,
  `tests/ssh_server.py` 403.

## Requisitos

### R0: folga em `ui/main_window.py`

1. Novo `ui/footer_path.py:FooterPath.for_window(window)`: liga `explorer.folder_selected`, `files.file_selected` e
   `files.selection_changed` e escreve o rodapé do caminho (`status.set_path`) exatamente como hoje (caminho relativo à raiz, "." na raiz,
   "{n} itens selecionados" com mais de um item).
2. Saem de `main_window.py` `_relative`, `_on_file_selected`, `_on_selection_changed`, as duas ligações e a linha do rodapé de
   `on_folder_selected`; entra `self.footer = FooterPath.for_window(self)`. Resultado esperado: cerca de 430/450.
3. **Testes:** os três arquivos acima passam sem mudança.

### R1: um comando no cluster, cancelável

1. Novo `core/sync/command.py` (Qt-free, em `QT_FREE` de `tests/test_architecture.py`): `run_command(argv, env, timeout_s) ->
   CommandResult(code: int | None, stdout: str, stderr: str, timed_out: bool)`. `subprocess.Popen` com `stdin=DEVNULL`; espera em passos
   de 0,2 s chamando `cancel.check()`; ao cancelar ou estourar o tempo mata o processo (`kill`, `wait`) e, no cancelamento, propaga
   `Cancelled`. Saída lida como UTF-8 com `surrogateescape`.
2. `remote_command(config, command: str) -> list[str]`: `[*ssh_command(cluster, sync.ssh_binary), f"{user}@{host}", command]`. O texto
   do comando vem só do `config.yaml`; nada lido do cluster entra num comando.
3. **Testes** (`tests/test_sync_command.py`, novo): saída e código de um `python -c` local; tempo esgotado mata o filho (`timed_out`);
   cancelar uma tarefa de `run_task` que roda `sleep 30` termina em menos de 1 s e não deixa processo vivo.

### R2: ler a saída do `qstatus`

1. Novo `core/cluster_jobs.py` (Qt-free, em `QT_FREE`): `Job(job_id: str, slots: int, name: str, owner: str | None, date: str,
   queue: str | None, running: bool)` e `JobsSnapshot(running: tuple[Job, ...], waiting: tuple[Job, ...], fetched_at: float)`, com
   `mine(user) -> tuple[Job, ...]` (os em execução cujo `owner == user`).
2. `parse_qstatus(text) -> JobsSnapshot`: seções pelos títulos "Running jobs:" e "Waiting jobs:" (também "Waiting jobs for user: <u>" e
   o equivalente de execução, do `qstatus` sem `-a`, onde o dono é `<u>`: formato não verificado, sem exemplo); linhas de cabeçalho (`job-ID…`) e de traços ignoradas. Cada
   linha de job é dividida por espaços a partir das **duas pontas**: `job-ID` e `#` no começo; no fim, `fila`, `hora`, `data` e `dono` na
   execução, `hora`, `data` e `dono` na espera (sem `dono` quando o título diz o usuário); o que sobra no meio é o `name` (um nome com
   espaços continua inteiro). Data e hora ficam como texto (`"10/15/2026 17:53:02"`), no fuso do cluster.
3. Saída vazia ou só com títulos: sem jobs. Saída com texto que não forma nenhuma linha de job nem título conhecido: `ValueError`
   ("Saída de {command} não reconhecida.").
4. `fetch_jobs(config, password) -> JobsSnapshot | JobsFailure`: roda `remote_command(config, cluster.jobs_command)` com `child_env` e
   tempo de `cluster.connect_timeout + 30` s. `JobsFailure(message, connection: bool, auth: bool, missing: bool)`: autenticação recusada
   (`is_auth_failure`), sem conexão (`is_connection_failure`), comando inexistente (código 127 ou "command not found": "O comando {command}
   não foi encontrado no cluster (cluster.jobs_command)."), outro código ("{command} terminou com código {code}: <última linha do
   stderr>"). As mensagens de conexão e autenticação reaproveitam as de `FAILURE_HINTS`.
5. **Testes** (`tests/test_cluster_jobs.py`, novo, com os dois exemplos acima como constantes): três em execução e dois na fila com dono,
   nome, data e fila; a variante do usuário dá o dono do título; nome com espaço; seção vazia; texto estranho → `ValueError`; `mine`
   filtra pelo dono; as quatro falhas classificadas a partir de `stderr` e código.

### R3: configuração

1. `core/config.py:ClusterConfig` ganha `jobs_command: str = "qstatus -a"` (vazio desliga tudo desta spec), `jobs_poll_seconds: int =
   Field(default=300, ge=30)` e `jobs_rotate_seconds: int = Field(default=5, ge=1, le=3600)`. Nos dois `config.example.yaml`, em
   `cluster:`, com comentários: o comando roda no cluster pelo ssh, com o login do `config.yaml`; um `qstatus` fora do `PATH` de um ssh
   sem terminal precisa do caminho completo.
2. **Testes** (`tests/test_config.py`): padrões e limites; as chaves nos dois exemplos.

### R4: "Executando: <nome>" à esquerda do LED

1. Novo `ui/widgets/jobs_indicator.py:JobsIndicator` (um botão plano com texto, sem ícone, elidido à direita com largura máxima
   `scaled(240)`, fonte da escala). `TopBar` ganha `add_before_led(widget)` e a barra fica: caminho, "Plotar SCF", **indicador**, LED,
   separador, botões de painel.
2. Textos (português em `_()`; o `.po` dá o inglês pedido):
   - "Consultando jobs…" até a primeira resposta;
   - "Executando: {name}" com um job do usuário em execução; com dois ou mais, o nome troca a cada `jobs_rotate_seconds`, na ordem do
     `qstatus`;
   - "Nenhum job em execução" sem nenhum;
   - "Jobs indisponíveis" depois de uma falha (o tooltip diz a causa);
   - "Jobs: informe a senha" com `auth: password` sem senha conhecida (nem `password_env` nem digitada na sessão); o clique pede a senha
     com o mesmo diálogo do sync.
3. Tooltip com resposta: "Seus jobs: {running} em execução, {waiting} na fila · atualizado às {time}. Clique para ver a fila do cluster."
4. Escondido quando o cluster não está configurado (`sync_enabled` falso) ou `jobs_command` está vazio.
5. **Testes** (`tests/test_jobs_ui.py`, novo, com um `fetch` falso injetado e o relógio da rotação acionado à mão): os cinco textos;
   rotação entre dois jobs; um job de outro dono não aparece; escondido sem cluster; a ordem dos widgets da barra.

### R5: a fila inteira num clique

1. Novo `ui/widgets/jobs_popup.py:JobsPopup` (`QFrame` com `Qt.WindowType.Popup`, aberto com `show()` logo abaixo do indicador; não é um
   `QMenu`). Conteúdo: título "Fila do cluster", "Atualizado às {time}" e o botão "Atualizar"; uma tabela com as seções "Em execução
   ({n})" e "Na fila ({n})" e as colunas "Nome", "Dono", "Envio / início" e "Fila" (na execução a data é a de início, a única que o
   `qstatus -a` dá; na espera, a de envio, e "Fila" vazia). Os jobs do usuário em negrito com a cor `accent_text`. O `job-ID` e o `#`
   ficam no tooltip da linha.
2. Sem jobs no cluster: "Nenhum job no cluster.". Antes da primeira resposta: o indicador de progresso (`CircularProgress`) e
   "Consultando o cluster…". Falha: a mensagem e "Tentar de novo".
3. **Cache da sessão:** a última `JobsSnapshot` fica em memória no controlador; abrir o painel mostra o cache na hora. "Atualizar" (e
   "Tentar de novo") consulta já; abrir com o cache mais velho que `jobs_poll_seconds` consulta em segundo plano, mostrando o cache.
   Nada vai para disco nem para o `QSettings`.
4. **Testes** (`tests/test_jobs_ui.py`): o painel mostra as duas seções com o exemplo; o cache aparece sem nova consulta; "Atualizar"
   consulta; colunas e destaque dos jobs do usuário; fechar com Esc.

### R6: quando consultar, o LED e o fechamento

1. Novo `ui/jobs_controller.py:JobsController.for_window(window)` (construído logo depois do `SyncCoordinator`): consulta ao abrir a
   janela e a cada `jobs_poll_seconds` **enquanto a janela está ativa** (como `ConnectionMonitor._on_app_state`); ao voltar a ficar
   ativa, consulta se a última tem mais que o intervalo. Uma consulta por vez (`TaskGroup` com uma chave; uma nova substitui a pendente).
2. LED (o primeiro item do pedido): uma consulta que conectou (qualquer código menos falha de conexão) chama
   `window.sync.monitor.report(True)`; falha de conexão chama `report(False)`. Falha de autenticação não muda o LED (o cluster respondeu).
3. Falha de autenticação ou comando inexistente **param** as consultas automáticas até "Atualizar", "Tentar de novo" ou "Recarregar
   config.yaml" (repetir login recusado pode bloquear o IP no cluster, como diz `monitor.py`); a senha da sessão é esquecida, como no sync.
   `SyncCoordinator` ganha os públicos `session_password(ask: bool) -> str | None` e `forget_password()` no lugar do privado
   `_ask_password`.
4. "Recarregar config.yaml": `_apply_loaded` chama `self.jobs.set_config(self.config)` (uma linha): cache e timers recomeçam.
5. Fechamento: o passo "cancelar" de `ui/shutdown.py:steps_for` chama `window.jobs.cancel()` (para os timers e cancela a consulta, cujo
   `ssh` morre pelo R1).
6. **Testes** (`tests/test_jobs_ui.py`): janela inativa não consulta; ativa de novo depois do intervalo consulta; falha de conexão deixa
   o LED `offline`, sucesso `online`; autenticação recusada para o timer e um "Atualizar" volta a consultar; recarregar o config zera o
   cache; fechar a janela com uma consulta pendurada (`fetch` que bloqueia até cancelado) termina dentro do orçamento do fechamento.

### R7: o comando no servidor SSH dos testes

1. `tests/ssh_server.py`: `LocalSSHServer(..., commands: dict[str, list[str]] | None = None)`. Um `argv[0]` que está em `commands` roda
   `commands[argv[0]] + argv[1:]` na pasta servida e é registrado como permitido; o resto da lista de permissões não muda. O cabeçalho do
   arquivo documenta.
2. **Teste de ponta a ponta** (`tests/test_cluster_jobs_ssh.py`, novo): um `qstatus` falso (`[sys.executable, <script>]` que imprime o
   exemplo) pelo `ssh` real, com chave e com senha (`SSH_ASKPASS`); a senha não aparece em `argv` nem no log (como
   `tests/test_sync_ssh.py:71`).

## Fora de escopo

- Ações sobre jobs (cancelar com `qdel`, enviar com `qsub`): só leitura.
- Notificação quando um job termina, histórico, gráfico de uso: outra spec.
- Outros escalonadores (Slurm `squeue`, PBS `qstat`): o comando é configurável, mas o parser só lê o formato deste `qstatus`.
- Converter as datas para o fuso local: ficam como o cluster as escreve.

## Decisões assumidas (confirmar na revisão)

1. **Um comando só (`qstatus -a`).** "Meus jobs em execução" são os do `qstatus -a` com `owner` igual a `cluster.user`: uma consulta
   alimenta o indicador e a lista. O exemplo do `qstatus` sem `-a` não mostra a seção de execução do usuário, e a coluna `owner` pode
   cortar logins longos (não verificado; o do usuário cabe).
2. **"submit time" da lista:** na execução o `qstatus -a` só dá o início; a coluna se chama "Envio / início".
3. **Textos fonte em português**, com o inglês pedido no catálogo ("Running: {name}", "No job running").
4. **Consulta só com a janela ativa**, como o monitor do LED; ao voltar, atualiza se passou do intervalo.
5. **O LED continua com os mesmos estados**; a consulta dos jobs é uma prova de conexão a mais (login de verdade), alimentando o
   `report` que o sync já usa.
6. **Auth por senha sem senha conhecida não pergunta sozinho:** só quando o usuário clica no indicador (um diálogo surgindo a cada 5 min
   seria pior).
7. O R0 entra aqui porque é a primeira spec da rodada que precisa de linha em `main_window.py`; a spec 65 conta com ele.

## Notas de implementação

- Novos: `ui/footer_path.py` (novo), `core/sync/command.py` (novo), `core/cluster_jobs.py` (novo), `ui/jobs_controller.py` (novo),
  `ui/widgets/jobs_indicator.py` (novo), `ui/widgets/jobs_popup.py` (novo), QSS do indicador e do painel em
  `ui/resources/styles/<domínio>/` (novo; cores só de tokens existentes), `tests/test_sync_command.py`, `tests/test_cluster_jobs.py`,
  `tests/test_jobs_ui.py`, `tests/test_cluster_jobs_ssh.py` (novos).
- Alterados: `ui/main_window.py` (R0; `self.jobs`; uma linha em `_apply_loaded`), `ui/widgets/bars.py` (`add_before_led`),
  `ui/sync_coordinator.py` (senha pública), `ui/shutdown.py` (cancelar), `core/config.py` e os dois `config.example.yaml`,
  `tests/ssh_server.py`, `tests/test_architecture.py` (`QT_FREE`), catálogo `lain.po`/`.mo`.
- Ordem: R0 primeiro (sozinho, a suíte verde), depois R1–R3 (sem Qt), R4–R6, R7.
- Limites: `ui/main_window.py` 449 → cerca de 432/450 depois do R0 e das duas linhas desta spec.
- Documentação ao implementar: `README.md` (seção nova "Jobs do cluster": o comando, o indicador, as chaves e o aviso do `PATH`);
  `specs/README.md` (F11 do `report.md` deixa de ser "adiado": esta spec cobre a leitura); `CLAUDE.md`, "Sync safety": "um comando
  remoto além do rsync só vem do `config.yaml` (`cluster.jobs_command`) e roda com as mesmas opções do ssh".
- i18n: textos novos em `_()`, depois `scripts/i18n.py update`, tradução ("Running: {name}", "No job running", …) e `compile`.

## Critérios de aceite e testes

- [ ] O rodapé do caminho continua igual (`test_multi_selection.py`, `test_main_window.py:109`, `test_file_grid_menu.py:92`) e
      `main_window.py` fica abaixo de 450 (`test_architecture.py`).
- [ ] O parser lê os dois exemplos e recusa texto estranho (`tests/test_cluster_jobs.py`).
- [ ] O comando remoto é cancelável e respeita o tempo (`tests/test_sync_command.py`).
- [ ] "Executando: <nome>" troca a cada `jobs_rotate_seconds`; "Nenhum job em execução"; "Jobs indisponíveis"; escondido sem cluster
      (`tests/test_jobs_ui.py`).
- [ ] O clique abre a fila com as quatro colunas, do cache, e "Atualizar" consulta (`tests/test_jobs_ui.py`).
- [ ] O LED segue a consulta; login recusado para as consultas; fechar não espera a consulta (`tests/test_jobs_ui.py`).
- [ ] Pelo `ssh` real, com chave e senha, sem a senha em `argv` ou no log (`tests/test_cluster_jobs_ssh.py`).
- [ ] Passo manual de aceite: no cluster real, `jobs_command: qstatus -a` mostra o job do usuário; se o `qstatus` não estiver no `PATH`
      do ssh sem terminal, o indicador diz "Jobs indisponíveis" com a mensagem do comando inexistente.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
