# Spec 71: correções de "Submeter…" e "Cancelar simulação…": cópias parciais, o `prefix` do SCF e do relax, o registro dos jobs submetidos e o mesmo nome

| | |
|---|---|
| **Prioridade** | 71: corrige o que a revisão das specs 69–70 achou, antes de qualquer outra ação nova no cluster |
| **Status** | Implementada (26/10/2026). Desvios: `fetch_prefixes` virou `fetch_stop_sources` e `pw_prefixes` virou `stop_sources` (devolvem `StopSource(prefix, inputs)`), e a cópia ficou num ajudante único, `copy_small_files`, usado também por `fetch_job_name`; as pastas temporárias das duas leituras têm o mesmo prefixo (`inputs-`), que os testes conferem que somem; `folder_check` devolve `FolderState(exit_files, snapshot)`; `SubmitPlan.job_name` e `same_name` têm padrão (`""`, `()`), e o diálogo só mostra "Job:" com nome; `Submitted.log_error`; o bloqueio pelo registro tem duas mensagens (na fila, em execução) em vez de uma com o estado no meio; a submissão que acha um job novo de mesmo nome depois da pergunta diz "apareceu no cluster" (pode estar rodando); `submit_log.record` recusa um campo vazio ou com tabulação/quebra de linha (`ValueError`, o job continua submetido); `job_name` fica em `core/qsub_lint.py`, que já lia as diretivas `#$`; `ui/job_actions.py` 270, `ui/job_cancel.py` 240, `core/remote/submit.py` 210, `core/remote/inputs.py` 169, `core/remote/submit_log.py` 100, `ui/dialogs/cluster_action.py` 188, `core/sync/rsync.py` 440 |
| **Depende de** | spec 69 (submeter, `core/remote/actions.py`, a guarda dos testes), spec 70 (cancelar, `core/remote/inputs.py`, o popup da fila), spec 64 (`fetch_jobs`, `JobsSnapshot`), spec 38 (`core/qsub_lint.py`), spec 61 (`data_dir()`, `paths.data`), spec 27-3 (`atomic_write_text`, instância única) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: P; R2: P; R3: M; R4–R7: P) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): ações que mudam o cluster, com a regra do administrador para o `.EXIT` |

## Itens de origem

`Documentation/Relatorios/report-25-10-26-specs-69-70.md` (revisão das specs 69 e 70, 25/10/2026), achados C1–C7, com os ajustes
do usuário (26/10/2026):

> - Regarding the issue "C4": The cluster administrator's guideline is to use `prefix.EXIT` to cancel simulations. The `prefix.EXIT`
>   file used must always correspond to the `prefix` defined in the SCF or relaxation (relax/vc-relax) input file. In cases where
>   multiple SCF input files with different prefixes exist in the same folder, a corresponding `prefix.EXIT` file must be created for
>   each SCF input. The same applies to relaxation and vc-relax input files.
> - Regarding the issue "C2": I like the suggestion to use `<local_root>/.lain/` to track jobs submitted via Lain, but […] instead
>   of using `<local_root>/.lain/` for this purpose, a separate log file should be created to record simulations submitted through
>   Lain. Furthermore, to prevent other instances of duplicate submissions, the system must check whether the job name (`name_job`)
>   matches any job currently in the queue or already running. If a match is found, a dialog box should appear to inform the user
>   that a job with the same name is already queued or running, and ask whether they wish to proceed with submitting another job
>   under the same name.
> - Please exclude the issue "C8 · Five SSH logins per action" from this set of fixes; I will address it separately later.

Respostas do usuário: o registro fica em `data_dir()/submitted_jobs.log` (segue `paths.data`); só os jobs **do próprio usuário** contam
para o nome igual; o registro é uma tabela de texto separada por tabulações, com cabeçalho.

## Situação atual (antes desta spec)

- `core/remote/inputs.py:69`: qualquer código do rsync diferente de 0 abortava a leitura dos inputs, inclusive 24 ("file has
  vanished") e 23, normais numa pasta com o pw.x rodando (C1, reproduzido no relatório).
- `pw_prefixes` lia o `prefix` de **todo** input do pw.x (nscf e bands inclusive); a nota do diálogo dizia que os comandos seguintes
  "ainda rodam", o que não vale para um pw.x com outro `prefix` da lista (C4).
- `folder_check` só via jobs em execução (pelo `<nome>.o<id>`): um job na fila não bloqueava uma nova submissão (C2; fora de escopo
  na spec 69).
- A falha do `qstatus` na conferência virava `SubmitBlocked` e perdia `connection`/`auth`/`local` (C3); `cluster_jobs.classify` lia
  qualquer "Permission denied" como login recusado, sem exigir o código 255 do ssh.
- Uma confirmação aceita depois do `cancel()` do fechamento ainda rodava o comando (`TaskGroup.submit` aceita tarefa depois de
  `shutdown`) (C5).
- O botão de cancelar do popup guardava o estado "Aguarde…" do momento do desenho, e um clique bloqueado sumia sem aviso (C6).
- `submit_line` só era usada pelos testes, cópia de `SubmitPlan.line` (C7).

## Requisitos

### R1: cópias parciais do rsync (C1)
1. `core/remote/listing.py`: `VANISHED = 24` ao lado de `PARTIAL = 23`.
2. `core/remote/inputs.py`: `copy_small_files(config, remote_dir, scratch, password, only=None)` copia (ou devolve `ActionFailure`
   local); quem chama lê a pasta temporária primeiro e decide: código 0 vale; 23 ou 24 valem quando chegou o que se precisava (uma
   fonte do `.EXIT`, o script); o resto passa por `listing.classify` como antes (pasta inexistente → `NOT_FOUND`, sem leitura →
   `NO_ACCESS`). O código aceito vai ao log como aviso.

### R2: o `prefix` vem só dos inputs de SCF, relax e vc-relax (C4)
1. `stop_sources(folder) -> tuple[StopSource, ...]`: só inputs do pw.x (pelo conteúdo) cujo `calculation` (sem aspas, minúsculo,
   `scf` quando ausente, como no pw.x) está em `STOP_CALCULATIONS = ("scf", "relax", "vc-relax")`; um `StopSource(prefix, inputs)`
   por `prefix`, em ordem alfabética, com os inputs que o definem.
2. `StopPlan.sources`, com `prefixes` e `files` como propriedades; sem fonte, `NotRunning("Nenhum input de scf, relax ou vc-relax do
   pw.x (até 1 MB) nesta pasta: o arquivo de parada usa o prefix de um deles.")`.
3. O diálogo mostra cada arquivo com seus inputs ("arquivo de parada do pw.x: al.EXIT (al.scf.in), si.EXIT (relax.in)"); `NOTE_EXIT`
   diz: um arquivo por `prefix` desses inputs; o pw.x para na próxima verificação e o apaga; um pw.x seguinte com o mesmo `prefix`
   (nscf, bands) ainda roda, a partir do cálculo interrompido; com outro `prefix` da lista, para logo na primeira verificação; sem
   pw.x rodando, o arquivo fica e a próxima submissão avisa.

### R3: registro dos jobs submetidos, bloqueio pelo ID e o mesmo nome (C2)
1. `core/qsub_lint.py:job_name(text, script)`: o valor do último `-N` das linhas `#$`, sem aspas; sem `-N`, o nome do arquivo (o
   padrão do SGE). `core/remote/inputs.py:fetch_job_name` copia só o script (`small_files_command(only=…)`: `--include=<script>`,
   `--exclude=*`).
2. Novo `core/remote/submit_log.py` (sem Qt): `data_dir()/submitted_jobs.log`, cabeçalho `# date_utc\taccount\tjob_id\tname\t
   remote_dir\tscript` e uma linha por job; `record` lê, acrescenta e grava inteiro (`atomic_write_text`); `read_log` pula linhas
   ilegíveis e trata um arquivo ilegível como vazio; `logged_here(entries, account, remote_dir)` dá os `(job-ID, nome)`.
3. `folder_check`, depois do bloqueio pelo `.o`: um job do usuário (em execução ou na fila) cujo `(ID, nome)` está no registro desta
   conta e pasta bloqueia (`SubmitBlocked`, uma mensagem para a fila e outra para a execução). ID **e** nome: o SGE reaproveita IDs.
4. `plan_submit` lê o nome do job; `SubmitPlan.job_name` e `same_name` (os jobs do usuário com esse nome, em execução e na fila).
   `submit` confere de novo: um job de mesmo nome que não estava no plano bloqueia ("…apareceu no cluster depois da confirmação…").
5. Depois de um `Submitted` reconhecido, `submit` grava o registro no worker; uma falha (`OSError`, `ValueError`) não desfaz a
   submissão: vai em `Submitted.log_error` e o toast vira aviso ("O registro de jobs submetidos não pôde ser gravado (…).").
6. `ui/dialogs/cluster_action.py:SameNameDialog`/`ask_same_name`: "Já existe um job seu chamado {name} no cluster", uma linha por
   job ("em execução desde …", "na fila desde …"), "Submeter outro job com o mesmo nome?", "Voltar" (padrão, Enter) e "Submeter mesmo
   assim". `_on_planned` pergunta antes do diálogo de submissão; "Voltar" não roda nada. O diálogo de submissão mostra "Job: {nome}".

### R4: a falha do `qstatus` mantém os indicadores (C3)
1. `core/remote/actions.py:failure_of_jobs(jobs, message)`, usado por `job_cancel._queue` e por `folder_check`, que passa a devolver
   `ActionFailure` (o mesmo texto): toast de erro, LED e `forget_password`.
2. `cluster_jobs.classify`: login recusado só com o código 255 do ssh, como `classify_failure` desde a spec 70.

### R5: nada chega ao cluster depois do fechamento (C5)
`JobActionsController.cancel()` marca `_closed`; `run()` volta sem fazer nada depois disso. Cobre submeter, parar e `qdel` (todos
usam o mesmo `run`).

### R6: o popup decide no clique (C6)
`waiting_blocked` só devolve `NO_DELETE` (botão desabilitado); `cancel_waiting` confere a ação em andamento no clique e mostra o motivo
num toast de aviso.

### R7: `submit_line` removida (C7)
Os testes conferem `SubmitPlan(...).line` montado com `submit_steps`.

## Fora de escopo

- C8 (cinco logins ssh por ação): o usuário trata depois.
- Um job da fila que o Lain **não** submeteu (de um terminal) continua sem bloquear pela pasta: só o diálogo do mesmo nome o pega.
- Criar só o `.EXIT` do `prefix` que roda agora: o `qstatus` não diz qual input está rodando.

## Decisões

- **Do usuário:** a regra do administrador para o `prefix` (SCF, relax, vc-relax; um arquivo por input de cada); um registro próprio, fora
  de `.lain/`, em `data_dir()`, como tabela de texto; o nome igual pergunta (não bloqueia) e só conta os jobs do usuário; C8 fica fora.
- **Assumidas:** um job do registro desta pasta ainda no cluster **bloqueia** (o ID é certo); `md`/`vc-md` não nomeiam o `.EXIT` (a
  regra cita só SCF e relax); uma pasta só com nscf/bands não ganha `.EXIT` (`NotRunning`); o registro guarda todos os jobs, sem
  podar.

## Critérios de aceite e testes

Todos só com falsos e `tests/ssh_server.py` (nada chega ao cluster):
- `tests/test_remote_inputs.py`: 23/24 com input lido dão a fonte; 24 sem input e outros códigos falham; pasta inexistente com 23
  continua `NOT_FOUND`; nscf, bands e bands.x não contam; relax (`si_relax`) e vc-relax (`kao_vc_relax`) contam; `calculation`
  ausente conta como scf; um `prefix` por vários inputs; o comando de um arquivo só; o script lido pelo servidor local.
- `tests/test_qsub_lint.py`: `job_name` (aspas, o último `-N`, comentário, sem valor, padrão) e o script de referência.
- `tests/test_submit_log.py`: ida e volta, cabeçalho, linhas ruins, arquivo ilegível, campos recusados, `logged_here`.
- `tests/test_remote_submit.py`: bloqueio pelo registro (fila e execução), registro de outra pasta/nome/conta não bloqueia,
  `same_name` só do usuário, nome novo depois da pergunta bloqueia, registro gravado e `log_error`, falha da fila com indicadores.
- `tests/test_job_submit.py`: a pergunta do nome antes da submissão, LED offline com a fila sem resposta, aviso do registro, nada roda
  depois do `cancel()`, os dois diálogos reais (`drive_modal`).
- `tests/test_job_cancel.py` e `tests/test_job_cancel_ui.py`: o novo `NotRunning`, um `.EXIT` por fonte, o método com os inputs, o
  toast do clique durante uma ação, nada roda depois do `cancel()`.
- `tests/test_cluster_jobs.py`: "Permission denied" com código ≠ 255 não é login recusado. `tests/test_job_submit_ssh.py`: nome do job
  e registro pelo servidor local.
