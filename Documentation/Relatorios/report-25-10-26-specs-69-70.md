# Relatório de revisão: specs 69 e 70 (submeter e cancelar no modo cluster)

Data: 2026-10-25 · Base: `main` @ aa377ec · Escopo: os dois últimos commits, `fc52023` (spec 69, "Submeter…" num
`.qsub`) e `aa377ec` (spec 70, "Cancelar simulação…" numa pasta e o `qdel` do popup da fila).

**Método.** Uma revisão automática (`/code-review medium`) levantou 10 achados. Cada um foi conferido no código, e
quatro foram reproduzidos com um script descartável. O script usa os falsos de `tests/` (`FakeListing`, `snapshot`) e
troca `list_remote`, `fetch_jobs` e `run_command` por funções locais: **nenhuma rede, nenhum acesso ao cluster**. A
suíte (pytest, ruff, pyright) não foi executada. Nada foi alterado no repositório além deste arquivo. Cada achado
diz como foi obtido:

- **Confirmado**: reproduzido pelo script.
- **Leitura**: lido no código, não reproduzido.

Escala: prioridade **Alto / Médio / Baixo**; esforço **P** = horas, **M** ≈ 1 dia, **G** = mais de 1 dia.

A conferência mudou a severidade de alguns achados e corrigiu afirmações da revisão automática (§4). Achados
repetidos foram juntados: são 8 IDs para os 10 achados.

---

## 0. Resumo

| ID | Sev. | Área | Achado | Como | Esf. |
|---|---|---|---|---|---|
| C1 | **Médio** | Cancelar (pasta) | Os códigos 24 e 23 do rsync, ao copiar os inputs, abortam o cancelamento, justamente numa pasta com o pw.x rodando | Confirmado | P |
| C2 | **Médio** | Submeter | Um job do usuário ainda na fila não bloqueia uma nova submissão na mesma pasta | Confirmado | P/M |
| C3 | Baixo | Submeter | Uma falha do `qstatus` na conferência da pasta perde `connection`/`auth`/`local`: o toast sai como aviso, não erro, e o LED fica verde | Confirmado | P |
| C4 | Baixo | Cancelar (pasta) | A nota do diálogo diz que os comandos seguintes "ainda rodam", mas um pw.x seguinte com outro `prefix` da pasta para logo no início | Confirmado + Leitura | P |
| C5 | Baixo | Fechamento | Uma confirmação aceita depois do `cancel()` do fechamento ainda roda o comando | Leitura | P |
| C6 | Baixo | Popup da fila | O estado do botão de cancelar fica velho enquanto o popup está aberto, e um clique bloqueado some sem aviso | Leitura | P |
| C7 | Baixo | Limpeza | `submit_line` duplica `SubmitPlan.line`, e só os testes a usam | Leitura | P |
| C8 | Baixo | Desempenho | Submeter e cancelar pela pasta abrem 5 logins ssh cada | Leitura | M |

Ordem sugerida: **C1 → C2 → C3 → C4 → C5 → C6 → C7**; C8 só se a demora incomodar (§5).

**O que está sólido.** As três ações conferem a pasta e a fila duas vezes: antes do diálogo e logo antes do comando.
Os nomes vindos do cluster passam por `checked_name` e `shlex.quote`. O `qdel` roda só pelo ID e só com o job ainda em
espera (`waiting_check`). A guarda `tests/cluster_guard.py` já pegou dois vazamentos reais. **Nenhum achado permite um
comando no cluster sem confirmação, nem um `qdel` num job em execução.**

---

## 1. Cancelar uma simulação (spec 70)

### C1 · Os códigos 24 e 23 do rsync abortam o cancelamento — **Médio** · Confirmado

**Onde.** `src/qe_studio/core/remote/inputs.py:67-71`

```python
result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
failure = classify(result, []) if result.timed_out or result.code != 0 else None
if isinstance(failure, RemoteFailure):
    return failure_of(failure)
prefixes = pw_prefixes(Path(scratch))
```

**O que acontece.** Para criar `<prefix>.EXIT`, `plan_stop` copia os arquivos do topo da pasta (até 1 MB, sem
subpastas: `small_files_command`) para uma pasta temporária e lê o `prefix` dos inputs do pw.x. Qualquer código
diferente de 0 vira falha, inclusive os dois que o rsync usa para cópias **parciais**:

- **24** ("file has vanished"): um arquivo listado sumiu antes de ser copiado. Numa pasta com o pw.x rodando, isso é
  normal. O pw.x apaga o próprio `.EXIT` e, com `outdir='./'`, os arquivos de mistura. O script também move ou apaga
  arquivos entre as etapas (o `pdos.qsub` faz `mv *wfc* orbitals/`).
- **23** quando um único arquivo é ilegível (de outro usuário do grupo, por exemplo). Pior: `listing.classify` lê
  "Permission denied" com o código 23 como `NO_ACCESS`, a mensagem de uma *pasta* sem acesso, o que engana o usuário.

**Reprodução.** Com um `run_command` falso que grava um `scf.in` (`prefix='al'`) na pasta temporária:

```
rsync 0,  scf.in copiado → ('al',)
rsync 24, scf.in copiado → ActionFailure('rsync terminou com código 24: file has vanished: ".../al.mix1"')
```

O input chegou inteiro nos dois casos: só o código de saída muda o resultado.

**Por que importa.** É o caminho para parar um job em execução. Ele falha justamente quando a pasta está mais ativa, e
a mensagem não diz que basta tentar de novo.

**Sugestão.** Ler o que chegou antes de decidir, e aceitar 23 e 24 quando algum input do pw.x foi lido:

```python
VANISHED = 24  # rsync: some files vanished while they were copied

result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
prefixes = () if result.timed_out else pw_prefixes(Path(scratch))
if result.code in (PARTIAL, VANISHED) and prefixes:
    log.warning("inputs: rsync ended with code %s, reading what arrived", result.code)
elif result.timed_out or result.code != 0:
    failure = classify(result, [])
    if isinstance(failure, RemoteFailure):
        return failure_of(failure)
```

Uma pasta inexistente ou sem leitura continua falhando como hoje: nada chega, `prefixes` fica vazio e `classify` dá
`NOT_FOUND` ou `NO_ACCESS`. Um input ilegível pode faltar na lista, mas o do job em execução é do próprio usuário,
então o risco é pequeno.

**Testes** (`tests/test_remote_inputs.py`):

- código 24 com um `scf.in` copiado dá `("al",)`;
- código 23 sem nada copiado continua `ActionFailure`;
- código 24 sem nenhum input do pw.x continua falha, porque não há o que ler.

### C4 · A nota do diálogo não bate com os vários `prefix` — **Baixo** · Confirmado (linha) + Leitura

**Onde.** `src/qe_studio/core/remote/job_cancel.py:90-95` (`exit_line`) e `src/qe_studio/ui/job_cancel.py:49-53`
(`NOTE_EXIT`).

**O que acontece.** `exit_line` cria um `.EXIT` para o `prefix` de **cada** input do pw.x da pasta. Com dois
`prefix`:

```
touch /home/u/runs/ilita/Bands/al.EXIT /home/u/runs/ilita/Bands/al_conv.EXIT
```

É o que a spec 70 decidiu (decisão 5: "Um `.EXIT` de um `prefix` que não está rodando para o próximo `pw.x` desse
`prefix` no mesmo job (o que se quer de um cancelamento) e, se sobrar, a spec 69 avisa na próxima submissão"), e o aviso
existe (`SubmitDialog`: "A pasta tem {name}: o pw.x vai parar na primeira verificação…"). O problema é o texto que o
usuário lê antes de confirmar:

> O pw.x procura esse arquivo na pasta durante a execução, para de forma limpa ("Program stopped by user request") e o
> apaga. Os comandos seguintes do script (outro pw.x, bands.x, projwfc.x…) ainda rodam.

Isso vale para os programas que não são pw.x e para um pw.x com o **mesmo** `prefix`, porque o arquivo já foi apagado.
Não vale para um pw.x com **outro** `prefix` da lista: ele acha o seu `.EXIT` e para na primeira verificação. O caso
típico é um script de convergência que roda `ecut_30.in`, `ecut_40.in`… com um `prefix` cada.

No fluxo mais comum (scf → bandas, com o mesmo `prefix`, que é o que deixa as bandas lerem o `.save` do scf), o texto
está certo, mas não avisa o que interessa: cancelar durante o scf deixa o pw.x de bandas começar sobre um cálculo
interrompido.

**Sugestão.** Reescrever `NOTE_EXIT` para cobrir os dois casos, por exemplo:

> O pw.x procura esse arquivo na pasta durante a execução, para de forma limpa ("Program stopped by user request") e o
> apaga. Um pw.x seguinte do script com o mesmo prefix ainda roda, a partir do cálculo interrompido; com outro prefix
> desta lista, ele para logo na primeira verificação. Os demais programas (bands.x, projwfc.x…) ainda rodam.

Texto novo: `scripts/i18n.py update`, traduzir e `compile`.

Mudar o comportamento (criar só o `.EXIT` do `prefix` que roda agora) não é sugerido: o `qstatus` não diz qual input
está rodando, e adivinhar contraria a regra da spec 70 ("nunca adivinha").

---

## 2. Submeter (spec 69)

### C2 · Um job do usuário na fila não bloqueia a submissão — **Médio** · Confirmado

**Onde.** `src/qe_studio/core/remote/submit.py:91-97` (`folder_check`) e `src/qe_studio/core/cluster_jobs.py:61-63`
(`mine`, que só devolve os jobs em execução).

**O que acontece.** O único vínculo entre um job e uma pasta é o `<nome>.o<id>`, que o escalonador cria quando o job
**começa**. Um job na fila não deixa nada na pasta, então `folder_check` não o vê.

**Reprodução.** Fila com o job 25000 `Bands-kao-b` do usuário em espera, pasta com `bands.qsub`: `folder_check`
devolve `()` (nada bloqueia) e o diálogo de submissão abre.

**Cenário.** O usuário submete e vê "Job 25000 (Bands-kao-b) submetido.". A fila demora a começar o job, ele acha que
não foi e submete o mesmo `.qsub` de novo. Os dois jobs rodam na mesma pasta e escrevem nos mesmos arquivos, que é
exatamente o que a spec 69 quer evitar.

**Contexto.** A spec 69 deixou isso fora de escopo de propósito ("Fora de escopo": o `qstatus` não diz a pasta de um
job na fila; o `qstat -j <id>` diria o `cwd`, mas o formato deste cluster não foi visto). Não é um desvio da spec: é
uma lacuna que ela mesma registrou, e o caso mais provável tem uma solução barata.

**Sugestão (sem adivinhar).** O Lain sabe exatamente o que ele mesmo submeteu: o `Submitted(job_id, name)` chega junto
com a pasta do plano.

1. `JobActionsController` guarda `job_id → remote_dir` de cada `Submitted` da sessão (ou em `<local_root>/.lain/`, via
   `core/project_data.py`, para valer entre sessões).
2. `plan_submit` e `submit` recebem os IDs submetidos daquela pasta, e `folder_check` bloqueia quando algum deles está
   em `snapshot.waiting`, comparando pelo ID, como o `waiting_check` da spec 70. Mensagem, por exemplo: "O job
   {job_id} que o Lain submeteu desta pasta ainda está na fila. Espere ele começar ou cancele-o pela fila antes de
   submeter outro script."
3. Opcional, para jobs que o Lain não registrou: um **aviso** no diálogo, não um bloqueio, quando um job do usuário na
   fila tem o nome do `#$ -N` do script. Isso exige ler o `.qsub`, um arquivo pequeno (a cópia de
   `small_files_command` já existe).

Itens 1–2: P. Item 3: M. **Decisão do usuário:** um job na fila deve bloquear, como o em execução, ou só avisar? A
sugestão acima bloqueia só quando o ID é certo.

**Testes** (`tests/test_remote_submit.py`): um ID registrado para a pasta e em espera na fila dá `SubmitBlocked`; o
mesmo ID já em execução continua bloqueado pela regra de hoje; um ID de outra pasta não bloqueia.

### C3 · A falha do `qstatus` perde os indicadores da falha — **Baixo** · Confirmado

**Onde.** `src/qe_studio/core/remote/submit.py:86-90` e `src/qe_studio/ui/job_actions.py:243`.

```python
jobs = fetch_jobs(config, password)
if isinstance(jobs, JobsFailure):
    message = _(
        "Não foi possível conferir se já roda um job nesta pasta: {message}. Nada foi submetido."
    )
    return SubmitBlocked(message.format(message=jobs.message.rstrip(".")))
```

`SubmitBlocked` só leva a mensagem. Em `_tell`, todo resultado que não é `ActionFailure` passa por `self.report(None)`
("o cluster respondeu"), e um `SubmitBlocked` vira toast de **aviso**.

**Reprodução.** Com a listagem OK e `fetch_jobs` dando `JobsFailure(connection=True)`, `folder_check` devolve
`SubmitBlocked('Não foi possível conferir… O cluster não respondeu. Nada foi submetido.')`, sem nenhum indicador.

**Alcance real (menor do que a revisão automática disse).** `folder_check` lista a pasta antes de consultar a fila,
com a mesma senha e o mesmo ssh. Uma senha errada ou um ssh que não roda falham já na listagem, que mantém os
indicadores (`failure_of`). Sobra um caso: o `qstatus` estoura o tempo, ou a conexão cai, depois de a listagem
responder. Um qmaster do SGE ocupado faz isso. Nesse caso o LED fica verde e o toast é de aviso, não de erro. Nada é
submetido em nenhum caso: a segurança não é afetada.

**Inconsistência.** O cancelamento faz a mesma conversão à mão, mas mantém os indicadores
(`core/remote/job_cancel.py:72-86`, `_queue`). São duas versões da mesma regra.

**Sugestão.**

1. Criar `failure_of_jobs(jobs: JobsFailure, message: str) -> ActionFailure` em `core/remote/actions.py`, ao lado de
   `failure_of`, e usá-la em `_queue` e em `folder_check`. `folder_check` passa a devolver `ActionFailure` (o tipo já
   está na assinatura), com a mensagem de hoje.
2. Ao mesmo tempo, alinhar `core/cluster_jobs.py:147`. Ali, `classify` lê qualquer "Permission denied" como login
   recusado, sem exigir o código 255 do ssh. É o falso positivo que a spec 70 corrigiu em `classify_failure`: um
   "Permission denied" do próprio comando faria o Lain esquecer a senha certa. Com os indicadores passando adiante,
   esse falso positivo passaria a alcançar também a submissão.

**Testes.** Em `tests/test_remote_submit.py`: `fetch_jobs` com `JobsFailure(connection=True)` dá `ActionFailure` com
`connection=True` e a mensagem "Nada foi submetido.". Em `tests/test_job_submit.py`: o LED vai para "inacessível".

### C7 · `submit_line` duplica `SubmitPlan.line` — **Baixo** · Leitura

**Onde.** `src/qe_studio/core/remote/submit.py:70-71`.

Nenhum código de `src/` chama `submit_line`; só `tests/test_remote_submit.py:48` e `tests/test_remote_actions.py:71`.
A linha que vai de fato para o ssh é `SubmitPlan.line` (`" && ".join(self.steps)`), outra cópia da mesma junção. Hoje
as duas dão o mesmo texto, mas os testes conferem uma função que a produção não usa: uma mudança em `SubmitPlan.line`
continuaria passando nos testes de `submit_line`.

**Sugestão.** Remover `submit_line` e fazer os dois testes conferirem o `plan.line` de um `SubmitPlan` montado com
`submit_steps`, ou então fazer `SubmitPlan.line` chamar uma função única.

---

## 3. O que vale para as duas ações

### C5 · Uma confirmação aceita depois do fechamento ainda roda o comando — **Baixo** · Leitura

**Onde.**

- `src/qe_studio/ui/job_actions.py:210-223` (`_on_planned`), `:106-112` (`cancel`) e `:125-131` (`run`);
- `src/qe_studio/ui/job_cancel.py:162-166` e `:202-206`;
- `src/qe_studio/core/tasks.py:255-269` (`TaskGroup.submit`).

**O que acontece.** O diálogo de confirmação (`ask_submit` ou `ask_cancel`) é um `exec()` modal aberto de dentro do
retorno da tarefa de conferência. Suponha que o passo "cancelar" do fechamento (`job_actions.cancel()`) rode enquanto
o diálogo está aberto. `_pending` e `_plan` são limpos e o pool é desligado, mas `_on_planned` já tem `config` e
`password` em variáveis locais. Se o diálogo voltar como aceito, `self.run(SUBMITTING, submit, …)` roda mesmo assim,
porque `TaskGroup.submit` não tem estado "fechado" e aceita uma tarefa nova depois de `shutdown`. O mesmo vale para
"Criando o arquivo de parada…" e para o `qdel`.

**Alcance real.** Pequeno. Os diálogos são `setModal(True)` (modais para a aplicação). Enquanto um deles está aberto,
o Qt ignora o pedido de fechar a janela vindo do gerenciador de janelas. No fim da sessão, o Qt fecha primeiro o
diálogo modal, que volta como *rejeitado*, e só depois a janela. O caminho que sobra é um `window.close()`
programático com o diálogo aberto (um teste, ou um futuro fechamento por sinal). Ainda assim, o comando é dos que mudam
o cluster, e a correção é curta.

**Sugestão.**

```python
def cancel(self) -> None:
    self._closed = True
    self._tasks.shutdown(0)
    ...

def run(self, label: str, fn: Callable, *args: Any, on_done: Callable[[Any], None]) -> None:
    if self._closed:  # the window is closing: nothing new reaches the cluster
        return
    ...
```

Como `JobCancelController` usa o mesmo `run`, a guarda cobre as três ações.

**Teste.** Um `ask_submit` falso que chama `window.job_actions.cancel()` e devolve `True`: nenhum `run_action` é
chamado. O mesmo com `ask_cancel` em `qe_studio.ui.job_cancel`.

### C6 · Botões de cancelar do popup — **Baixo** · Leitura

**Onde.** `src/qe_studio/ui/widgets/jobs_popup.py:239-256` (`_cancel_button`) e
`src/qe_studio/ui/job_cancel.py:175-179` (`cancel_waiting`).

**O que acontece.** O estado do botão (habilitado, ou desabilitado com "Aguarde…") é calculado por `cancel_reason`
quando a listagem é desenhada. O popup redesenha ao ser aberto (`ui/jobs_controller.py:234-244`, `on_clicked` →
`_fill_popup`) e quando chega uma consulta nova com ele aberto. Nada o redesenha quando uma ação no cluster começa ou
termina.

- Se o popup for aberto durante uma conferência, os botões aparecem desabilitados com "Aguarde: uma ação no cluster
  está em andamento.". A ação termina em segundos, mas os botões continuam assim até o popup ser fechado e aberto de
  novo, ou até chegar a próxima consulta.
- `cancel_waiting` esconde o popup e, se `waiting_blocked` não for vazio, volta sem dizer nada. Com o botão desenhado
  no estado certo, isso quase não acontece (uma ação só começa com um clique fora do popup, que o fecha). Se acontecer,
  o clique some sem resposta.

**Sugestão.** Decidir no clique, não no desenho. O botão fica habilitado sempre que `cluster.delete_command` existe,
e `cancel_waiting` mostra o motivo num toast quando há uma ação em andamento:

```python
reason = self.waiting_blocked(job)
if reason:
    self.toast.show_message(reason, "warning")
    return
```

Isso resolve o estado velho e o clique silencioso de uma vez.

**Teste** (`tests/test_job_cancel_ui.py`): com uma ação segurada (`FakeFetch.hold()`), clicar no botão mostra o toast
e não abre o diálogo.

### C8 · Cinco logins ssh por ação — **Baixo** · Leitura

**Onde.** `src/qe_studio/core/remote/submit.py` (`plan_submit`, `submit`) e `src/qe_studio/core/remote/job_cancel.py`
(`plan_stop`, `stop`, `delete_waiting`).

| Ação | Antes do diálogo | Depois da confirmação | Total |
|---|---|---|---|
| Submeter | listagem + `qstatus` | listagem + `qstatus` + `qsub` | 5 |
| Cancelar (pasta) | listagem + `qstatus` + cópia dos inputs | `qstatus` + `touch` | 5 |
| Cancelar (fila) | nenhum | `qstatus` + `qdel` | 2 |

Cada um é um ssh completo, sem multiplexação (não há `ControlMaster` em `src/`), com até `connect_timeout + 30` s. Com
`auth: password` ou um cluster lento, cada clique leva vários segundos.

A janela entre a última conferência e o comando é de um login (o do próprio `qsub` ou `touch`), e ter menos logins
antes não a diminui. Fechá-la de verdade exigiria decidir no cluster, num comando só, que as regras de `CLAUDE.md`
(Sync safety) não permitem.

**Sugestão.** Só se a demora incomodar:

- **(a)** rodar a listagem e o `qstatus` em paralelo dentro da tarefa, o que corta a espera de um login em cada
  conferência. É preciso conferir o cancelamento cooperativo (`core/cancel.py`) nas duas threads.
- **(b)** multiplexar o ssh (`ControlMaster=auto`, `ControlPersist` curto, `ControlPath` no diretório de runtime)
  durante a sequência da ação, reduzindo tudo a um único aperto de mão. A (b) mexe no ssh de todo o Lain (askpass,
  `StrictHostKeyChecking=yes`) e pede uma spec própria.

---

## 4. Correções à revisão automática

| Revisão automática | Depois da conferência |
|---|---|
| A falha do `qstatus` perde os indicadores e uma senha errada nunca é esquecida (era o 1º achado) | A senha errada falha antes, na listagem, que mantém os indicadores. Sobram o LED e o nível do toast: **Baixo** (C3) |
| `exit_line`, com o exemplo `al` (scf) + `al_bands` (bandas) | Um pw.x de bandas com outro `prefix` não leria o `.save` do scf. O caso real é uma série de inputs com um `prefix` cada. O comportamento segue a decisão 5 da spec 70; o defeito é o texto do diálogo (C4) |
| Um job na fila não bloqueia a submissão | Confirmado, mas a spec 69 deixou isso fora de escopo de propósito; a sugestão bloqueia só pelo ID certo (C2) |
| Botões desabilitados por até 300 s (`jobs_poll_seconds`) | O popup redesenha a cada abertura: o estado velho dura só enquanto ele fica aberto (C6) |
| `submit_line` não é usada nem nos testes | Dois testes a usam; o problema é testarem uma cópia que a produção não usa (C7) |
| Fechar a janela durante o diálogo roda o `qsub` | Possível no código, mas o Qt bloqueia o fechamento da janela enquanto há um modal aberto (C5, **Baixo**) |
| Os cinco logins alargam a janela de corrida | A janela é de um login em qualquer caso; o custo é de tempo (C8) |

---

## 5. Ordem sugerida

1. **C1** (P): é o caminho para parar um job em execução. A correção fica em `inputs.py`, com três testes.
2. **C2**, itens 1–2 (P): bloqueio, pelo ID, dos jobs submetidos pelo Lain. Antes, decidir se um job na fila bloqueia
   ou só avisa.
3. **C3** (P): `failure_of_jobs`, mais o código 255 em `cluster_jobs.classify`.
4. **C4** (P): o texto do diálogo e o catálogo de traduções.
5. **C5** e **C6** (P cada): a guarda `_closed` e a decisão no clique.
6. **C7** (P): limpeza.
7. **C8** (M): só se a demora incomodar; a opção (b) precisa de uma spec própria.

C1–C7 cabem numa spec curta de correções (`spec-sdd`). Toda verificação deve rodar só contra `tests/ssh_server.py` ou
falsos, nunca contra o cluster.

---

## Anexo: o script de reprodução

Script descartável, fora do repositório, rodado com `uv run python`, com `XDG_*` em uma pasta temporária e
`QE_STUDIO_NO_CHECKOUT_CONFIG=1`. Ele montou um `AppConfig` com `parse_config` (host `hpc.example`) e trocou as
funções de rede por falsos:

| Achado | O que foi trocado | Resultado |
|---|---|---|
| C1 | `inputs.run_command` grava um `scf.in` e devolve o código 24, depois 0; `inputs.local_version` fixo | `ActionFailure(… código 24 …)` contra `('al',)` |
| C2 | `submit.list_remote = FakeListing(...)`; `submit.fetch_jobs` devolve uma fila com o job 25000 do usuário em espera | `folder_check` → `()` |
| C3 | `submit.fetch_jobs` devolve `JobsFailure(connection=True)` | `SubmitBlocked(...)`, sem indicadores |
| C4 | nenhum (`exit_line` é pura) | `touch …/al.EXIT …/al_conv.EXIT` |
