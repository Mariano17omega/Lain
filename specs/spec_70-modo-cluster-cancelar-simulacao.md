# Spec 70: cancelar simulações: `prefix.EXIT` para a que roda (pela pasta), `qdel` para a da fila (pelo popup), sempre conferido e confirmado

| | |
|---|---|
| **Prioridade** | 70: depois da 69, de que usa a base dos comandos que mudam o cluster; a ação mais delicada da rodada (um `qdel` num job em execução deixa o processo rodando sem aparecer na fila) |
| **Status** | Rascunho revisado pelo usuário (25/10/2026): decisões da revisão incorporadas |
| **Depende de** | spec 69 (novos nela: `core/remote/actions.py`: `checked_name`, `checked_dir`, `run_action`, `ActionFailure`; `cluster_jobs.running_in`; `ui/job_actions.py`; `RemoteController.menu_hooks`; `ui/dialogs/cluster_action.py`; o `cd … &&` do servidor dos testes; a guarda que impede os testes de chegar ao cluster, R7), spec 64 e 68 (`fetch_jobs`, `JobsSnapshot`, `JobsPopup` com as barras e a coluna "Núcleos"), spec 65 (`list_remote`, `local_version`, `RemoteBrowser`), spec 11 (`looks_like_input`, `input_lint.lint`) |
| **Usada por** | nenhuma |
| **Esforço** | M/G (R1: P; R2: M; R3: P; R4–R5: M; R6: P) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): uma ação que não se desfaz no cluster, com conferência imediatamente antes de agir, leitura do `prefix` dos inputs do QE e o comportamento do `pw.x` ao achar o `.EXIT` (lido na fonte do QE 7.1) |

## Itens de origem (`Ideias.md`, 25/10/2026, e revisão de 25/10/2026)

> - Para cancelar uma simulação em andamento, crio um arquivo vazio na pasta onde executei o script '.qsub' da simulação ("""touch prefix.EXIT """), com o nome 'prefix.EXIT'. Onde o 'prefix' é o prefix usado nos inputs do quantum espresso.
> - Para cancelar uma simulação que ainda está na fila de espera, uso o comando 'qdel job-ID', sendo o 'job-ID' o numero obtido através do comando 'qstatus' (lista de jobs).
> - O comando 'qdel' não deve ser usado em simulações que estão em andamento, pois isso cria erro no servidor, já que a simulação continua rodando no fundo apesar de sair da lista.
>
> ## Nova funcionalidade: Cancelamento de simulações
>
> Quero que no Ambiente Remoto do Lain, o usuario que possa cancelar as simulações submetidas:
>
> ### Para o caso de uma simulação que está rodando
>
> - O usuario vai até a pasta da simulação que está rodando, na lista de opções do botão de ações do botão direito do mouse, clica em cancelar. O programa verifica se a simulação, daquele script '.sub', está em andamento (usando o qstatus), caso positivo ele cria um arquivo vazio na pasta da simulação com o nome 'prefix.EXIT'. Onde o 'prefix' é o prefix extraido inputs (scf, nscf, bands, etc) dentro da pasta da simulação.
>
> Quando uma simulação é iniciada, é gerado um arquivo "<name_job>.o<job-ID>", onde o 'name_job' é o nome do job definido pelo usuario no cabeçalho do script '.sub':
>
> """
> ###       Grid setup                   ###
> #$ -N "name_job"
> """
>
> O 'job-ID' é o ID do job obtido através do comando 'qstatus'.
>
> Antes de cancelar, verificar se a simulação da pasta onde o script '.qsub' está rodando, isso deve ser feito verificando se o arquivo se o job-ID e o name_job do arquivo "<name_job>.o<job-ID>" é igual ao job-ID e ao name_job obtidos através do comando 'qstatus' (lista de jobs).
>
> ### Para o caso de uma simulação que está na fila de espera
>
> Na spec_64 implementei a exibição de lista de jobs em execução e na fila.
> Quero que coloque uma coluna com botões de cancelamento ao lado de cada job que está na fila de espera (Apenas os jobs da fila de espera, não os que estão em execução), localizadas no painel que abre quando se clica em 'Running: <name>' ou 'No job running' na barra superior.
>
> Para para os jobs que estão na fila de espera, use o comando 'qdel job-ID' para cancelar a simulação. Onde 'job-ID' é o ID do job obtido através do comando 'qstatus' (lista de jobs).
>
> Não deve usar 'prefix.EXIT' para cancelar simulações na fila de espera, pois isso não faz nada, só será cancelado quando o job estiver em execução.
>
> E o comando 'qdel' não deve ser usado para cancelar simulações que estão em andamento, pois isso cria erro no servidor, já que a simulação continua rodando no fundo apesar de sair da lista.
>
> E deve ser feito uma verificação se o job que está na fila de espera não é o mesmo que está em execução. Para isso, verifique se o job-ID e o name_job do arquivo "<name_job>.o<job-ID>" é igual ao job-ID e ao name_job obtidos através do comando 'qstatus' (lista de jobs). Isso seve para caso o usuario repita os name_job.
>
> ### Confimação de cancelamento
>
> Sempre deve abri uma caixa de dialogo perguntando se o usuario quer cancelar a simulação, e mostrando informações sobre a simulação a ser cancelada (nome do job, ID, caminho, etc). E também deve mostrar o metodo usando para cancelar, usando 'qdel' ou 'prefix.EXIT', caso o usuario confirmar o cancelamento, deve ser executado o comando ou criado o arquivo de acordo com o método determinado. A exibição do metodo de cancelamento é apenas para o usuario visualizar se está usando o metodo correto, não é para o usuario escolher o metodo de cancelamento.

Interpretação: o "Ambiente Remoto" é o modo cluster (spec 65); "cancelar" no menu é "Cancelar simulação…", num item de **pasta** (árvore ou
grade) ou num `.qsub` (vale a pasta dele). "Running: <name>" e "No job running" são o indicador da spec 64 em inglês. A verificação de que o
job da fila "não é o mesmo que está em execução" não tem pasta para olhar (um job na fila ainda não tem `<name_job>.o<job-ID>`, e o
`qstatus` não diz a pasta): ela é feita pelo **job-ID**, numa consulta nova do `qstatus` logo antes do `qdel` (o ID tem de estar em "Waiting
jobs", com o mesmo nome e dono, e **não** em "Running jobs"); comparar pelo ID, não pelo nome, é o que protege dos nomes repetidos (decisão 2).
O método nunca é escolhido: sai de onde o usuário clicou (pasta → `.EXIT`; popup → `qdel`) e é conferido antes de agir.

Decisões do usuário na revisão da primeira versão desta spec:

> - Sobre 'Uma regra de segurança do CLAUDE.md muda.' A regra que proibia executar coisas no cluster era apenas para a fase inicial do projeto. Agora, na fase final, vamos implementar algumas funções relacionadas ao cluster.
> - Sobre 'O .EXIT não encerra o job inteiro.' Usar .EXIT  para jobs em execução è uma orientação do admistrador, então mantenha como foi descrito.
> - Sobre 'Ler o prefix exige baixar os inputs.', use uma pasta local temporária conforme você decidiu.
>
> Não quero que nenhum teste seja executado no cluster, mas sim localmente. O Custer é um ambiente de produção/trabalho, nada deve ser executado nele sem permissão do usuario.

Ou seja: o método do `.EXIT` fica como está (orientação do administrador do cluster), os inputs vão para uma pasta local temporária (R1),
todo comando que muda o cluster só roda depois do "Cancelar simulação" do diálogo, e nenhum teste chega ao cluster (a guarda da spec 69 R7).

## Situação atual

- **R1 (o arquivo de parada do QE).** Lido na fonte do QE 7.1 (`Modules/check_stop.f90` no `qe-7.1` do GitHub do QEF): `check_stop_init`
  monta `exit_file = TRIM(prefix)//'.EXIT'` (`'EXIT'` com `prefix` vazio); `check_stop_now` faz `INQUIRE` primeiro do nome puro (a pasta de
  trabalho, que o `#$ -cwd` faz ser a do script) e, se não acha, de `TRIM(tmp_dir)//exit_file`; ao achar, abre e apaga o arquivo
  (`CLOSE(…, STATUS='DELETE')`) e escreve "Program stopped by user request". O `INPUT_PW` dá `prefix` com padrão `'pwscf'` e, em
  `restart_mode`, cita o "exit file" "prefix".EXIT. O script de bandas faz `scf`, depois o `pw.x` de bandas e o `bands.x`
  (`Documentation/Referencia_de_scripts_QSUB/bands.qsub:25-29`; `resources/templates/qsub/bands.qsub.j2`), sem `set -e`: o `.EXIT` para o
  `pw.x` que está rodando e some; o comando seguinte do script começa normalmente.
- **R2 (o `prefix` de uma pasta do cluster).** O modo cluster só tem nome, tamanho e data (`core/remote/listing.py:54`,
  `RemoteEntry`): o conteúdo dos inputs não está no Lain. As peças locais existem: `core/sniff.py:103` (`looks_like_input`, pela cabeça do
  arquivo), `core/qe/input_lint.py:210` (`lint(text) -> InputDoc`, que nunca levanta; `program` e `get(namelist, key)` em `:48-60`),
  `core/qe/input_edit.py:59` (`unquote`), `:66` (`read_input_text`), `core/calc_create/scf_info.py:25` (`DEFAULT_PREFIX = "pwscf"`).
  **Medido** com o rsync 3.5.0 local: `rsync -r --no-h --max-size=1M --exclude='*/' <pasta>/ <destino>/` traz só os arquivos do topo da
  pasta com até 1 MB (um `scf_Al.in` e um `Al.o23650` vieram; um `big.out` de 2 MB e um `sub/inner.in` não). `core/sync/rsync.py:143`
  (`_common`: `--no-h`, `--timeout`, `--protect-args` antes do 3.2.4, `-e ssh …`) e `:263` (`list_command`) são o modelo;
  `core/remote/listing.py:131` (`local_version`) dá a versão. `core/appdirs.py:77` (`cache_dir()`) é a pasta de cache do app.
- **R2 (a pasta do job).** Com `-cwd` e `-j y` (`_base.qsub.j2:11-12`), a saída do escalonador é `<nome>.o<job-ID>` na pasta do script; a
  spec 69 cria `cluster_jobs.running_in(nomes, snapshot, user)`, que liga esses arquivos aos jobs **em execução** do usuário pelo ID e pelo
  nome. Um job na fila ainda não tem o arquivo.
- **R4 (o popup).** `ui/widgets/jobs_popup.py:113-132` (`_table`): quatro colunas (`Nome`, `Dono`, `Envio / início`, `Núcleos`; `CORES = 3`
  em `:35`), `NoSelection` (`:124`); `_section` (`:177-203`) cria as linhas de cada barra; `show_snapshot` (`:150-164`) refaz a tabela
  inteira (também na troca de tema, `:222-224`). É uma janela `Qt.WindowType.Popup` (`:52`) aberta por `JobsController.on_clicked`
  (`ui/jobs_controller.py:234-244`) com o cache da sessão, que pode ter até `jobs_poll_seconds` (300 s) de idade: um job "Na fila" do popup
  pode já ter começado.
- **O `qdel`.** Nenhum código o roda; o `CLAUDE.md` (depois da spec 69) só permite programas do `config.yaml` e argumentos validados.
  **Não verificado:** a saída do `qdel` deste cluster (o SGE costuma dizer "<usuário> has deleted job <id>" ou "… registered the job <id> for
  deletion") e se o `qdel` está no `PATH` de um ssh sem terminal.
- **Não verificado:** se o `qstatus` corta nomes longos de job (a coluna `name` tem 26 caracteres no exemplo da spec 64; os nomes do
  exemplo cabem).
- Tamanhos: `ui/widgets/jobs_popup.py` 244, `ui/jobs_controller.py` 254, `core/sync/rsync.py` 415, `core/config.py` cerca de 486 depois da
  69, `ui/job_actions.py` (novo na 69), `ui/remote_controller.py` cerca de 482 depois da 69.

## Requisitos

### R1: buscar os inputs pequenos de uma pasta do cluster e ler o `prefix`

1. `core/sync/rsync.py`: `small_files_command(config, remote_dir, dest, version) -> list[str]`: `rsync -r --max-size=1M --exclude=*/`
   com `_common` e `user@host:<remote_dir>/` → `<dest>/` (só os arquivos do topo da pasta, até 1 MB; nada de subpastas).
2. Novo `core/remote/inputs.py` (Qt-free, em `QT_FREE`):
   - `pw_prefixes(folder: Path) -> tuple[str, ...]`: dos arquivos de `folder` que `looks_like_input` aceita, os que `lint` lê como
     `program == "pw"`; o `prefix` de cada um (`&CONTROL`, `unquote`), `DEFAULT_PREFIX` (`pwscf`) quando o input não tem; sem repetição, em
     ordem alfabética. `cancel.check()` entre os arquivos. Identificação **pelo conteúdo** (PRD §3), nunca pelo nome.
   - `fetch_prefixes(config, remote_dir, password) -> tuple[str, ...] | ActionFailure`: `tempfile.TemporaryDirectory(dir=cache_dir())`,
     `small_files_command` com `run_command` (`child_env`, `connect_timeout + 30` s), `pw_prefixes` do destino; a pasta temporária sai no
     fim, com sucesso, falha ou cancelamento. Cada `prefix` passa por `checked_name` (spec 69 R1): um `prefix` com caractere de shell é
     `ActionFailure` ("prefix não suportado para o arquivo de parada: {prefix}."). Nenhum input do pw.x: tupla vazia.
3. **Testes** (`tests/test_remote_inputs.py`, novo): `pw_prefixes` de uma cópia de `tests/fixtures/al_pdos_flat` (`copy_fixture`):
   `("al",)` (o `al.projwfc.in` não é pw.x e não conta); um input sem `prefix` dá `pwscf`; dois prefixos diferentes saem os dois, em
   ordem; um `.out` e um `.qsub` não contam; o comando tem `-r`, `--max-size=1M` e `--exclude=*/`; ponta a ponta pelo
   `tests/ssh_server.py` (com chave), uma pasta servida com um input de 1 KB, um arquivo de 2 MB e uma subpasta: só o input chega, e a
   pasta temporária não fica.

### R2: conferir e agir, sem Qt

1. Novo `core/remote/job_cancel.py` (Qt-free, em `QT_FREE`):
   - `StopPlan(remote_dir, jobs: tuple[Job, ...], prefixes: tuple[str, ...], line: str)` e `NotRunning(message)`.
   - `plan_stop(config, remote_dir, password) -> StopPlan | NotRunning | ActionFailure`: lista a pasta **de novo** (`list_remote`),
     consulta a fila **de novo** (`fetch_jobs`, nunca o cache do popup) e faz `running_in(nomes, snapshot, cluster.user)`. Nenhum job:
     `NotRunning("Nenhum job seu em execução nesta pasta: nenhum arquivo <nome>.o<id> corresponde a um job em execução no qstatus. Um job
     na fila se cancela pela fila do cluster, na barra superior.")`. Com jobs: `fetch_prefixes`; nenhum `prefix`:
     `NotRunning("Nenhum input do pw.x (até 1 MB) nesta pasta: sem o prefix, não há como criar o arquivo de parada.")`. Uma falha da
     listagem, da fila ou da busca é `ActionFailure`.
   - `exit_line(config, remote_dir, prefixes) -> str`: `touch` seguido de um caminho citado por prefixo, `<remote_dir>/<prefix>.EXIT`
     (`checked_dir` e `checked_name`), na mesma linha.
   - `stop(config, plan, password) -> Done | Refused | ActionFailure`: consulta a fila **de novo**; se nenhum dos `plan.jobs` continua em
     execução com o mesmo ID, nome e dono, `Refused("O job {job_id} não está mais em execução: nada foi criado.")` (o primeiro do plano);
     senão roda `plan.line` com `run_action` e devolve `Done("Pedido de parada criado: {files}. O pw.x para na próxima verificação.")`.
   - `delete_line(config, job) -> str`: `f"{cluster.delete_command} {job.job_id}"`, com o ID conferido por `^\d+$`.
   - `waiting_check(snapshot, job, user) -> Job | Refused` (pura): o ID está em "Running jobs" →
     `Refused("O job {job_id} começou a rodar: o qdel não é usado em jobs em execução. Cancele pela pasta dele, no modo cluster (Cancelar
     simulação…).")`; o ID não está em "Waiting jobs" → `Refused("O job {job_id} não está mais na fila: nada foi feito.")`; está, mas com
     outro nome ou outro dono → `Refused("O job {job_id} da fila não é mais {name}: nada foi feito.")`; senão o job da fila nova.
   - `delete_waiting(config, job, password) -> Done | Refused | ActionFailure`: consulta a fila **de novo**, `waiting_check`, e só então
     `run_action(delete_line)`; `Done("Job {job_id} ({name}) cancelado com qdel.")`.
   - Um `JobsFailure` da consulta nova é `ActionFailure` com "Não foi possível conferir o estado do job no cluster: {message}. Nada foi
     feito." (sem a fila nova, nenhuma ação roda); o código ≠ 0 do `touch` ou do `qdel` é `classify_failure` (spec 69 R1).
2. **Testes** (`tests/test_job_cancel.py`, novo, com `list_remote`, `fetch_jobs`, `fetch_prefixes` e `run_action` falsos e os textos de
   `tests/jobs_helpers.py`): plano com `Bands-kao-b.o24000` e o job 24000 do usuário em execução; sem o `.o` (ou com o `.o` de um ID
   antigo, ou de outro dono, ou com outro nome) → `NotRunning`; sem input → `NotRunning`; `exit_line` com dois prefixos; `stop` recusa
   quando o job terminou entre o plano e a confirmação e **não** roda o `touch`; `delete_waiting` recusa nos três casos e **não** roda o
   `qdel`; falha da fila nova → nada roda. **Propriedade** (Hypothesis): para qualquer `JobsSnapshot` gerado e qualquer job, `waiting_check`
   só devolve um job quando o ID está na espera, com o mesmo nome e dono, e fora da execução; com IDs repetidos entre as seções, nunca.
3. **Ponta a ponta, local** (`tests/test_job_cancel_ssh.py`, novo): pelo `ssh` real contra o `tests/ssh_server.py` em `127.0.0.1`, com
   `extra_commands={"touch": ["touch"], "qdel": [sys.executable, <script que grava o ID>], "qstatus": [...]}` e uma pasta servida com
   `al.scf.in` (de `tests/fixtures/al_pdos_flat`) e `teste.o7`: `plan_stop` e `stop` criam `al.EXIT` na pasta servida; `delete_waiting` de
   um job na fila falsa entrega o ID ao `qdel` falso; com o job na seção de execução da fila falsa, o `qdel` falso não é chamado.

### R3: configuração

1. `core/config.py:ClusterConfig`: `delete_command: str = "qdel"` (vazio desliga o cancelamento da fila), no validador `_strip_command`.
   O cancelamento pela pasta precisa do `jobs_command` (é ele que diz o que está rodando) e não tem chave própria. Nos dois
   `config.example.yaml`, com o comentário: só roda em job **na fila**, conferido no `qstatus` antes; um job em execução se cancela pelo
   arquivo `<prefix>.EXIT`.
2. **Testes** (`tests/test_config.py`): o padrão; vazio desliga; a chave nos dois exemplos.

### R4: "Cancelar simulação…" no menu do modo cluster

1. `ui/job_actions.py` (spec 69) acrescenta pelo mesmo gancho "Cancelar simulação…" quando há **um** item e ele é uma pasta (árvore ou
   grade) ou um `.qsub` (vale a pasta dele). Desabilitado, com o motivo no tooltip: `jobs_command` vazio ("Cancelar precisa de
   cluster.jobs_command: é o qstatus que diz se a simulação está rodando."); pasta recusada pelo `checked_dir`; uma ação em andamento
   (o motivo da spec 69).
2. O clique: senha como na spec 69 R4.3; `plan_stop` no worker ("Conferindo o job no cluster…"). `NotRunning`: toast `info` com a
   mensagem. `ActionFailure`: toast `error`. `StopPlan`: o diálogo do R6.
3. Confirmado: `stop` no worker ("Criando o arquivo de parada…"); `Done` → toast `info`; `Refused` → toast `warning`; `ActionFailure` → toast
   `error`. Depois de qualquer resposta que conectou: `window.jobs.refresh()` e a pasta listada de novo (ou tirada do cache), como na 69.
4. **Testes** (`tests/test_job_cancel_ui.py`, novo, com `remote_helpers.remote_window`, `menu_spy` e `ask_cancel` trocado em
   `qe_studio.ui.job_actions.ask_cancel`): o item aparece numa pasta e num `.qsub`, não num `.in` nem com dois itens; desabilitado sem
   `jobs_command`; `NotRunning` vira toast e nenhum diálogo abre; o diálogo recebe os jobs, a pasta, os prefixos e a linha; confirmar roda
   `remote_command(config, "touch …")`; recusar não roda nada.

### R5: a coluna de cancelar no popup da fila

1. `ui/widgets/jobs_popup.py`: uma quinta coluna, estreita e sem título. Nas linhas da barra "Na fila" **cujo dono é o usuário**, um
   `QToolButton` plano com o ícone `close` (já vendorizado) e o tooltip "Cancelar o job {job_id} (qdel)"; nas linhas de "Em execução" e nas
   de outros donos, nada. Sinal novo `cancel_requested = pyqtSignal(object)` (o `Job`). `JobsPopup.cancel_reason: Callable[[Job], str] |
   None = None`: chamado ao montar cada linha; um texto não vazio desabilita o botão e vira o tooltip. A tabela continua sem seleção; o botão
   é focável (borda de 1 px de `controls/focus.qss`); o tamanho vem de `scaled`. `WIDTH` passa de 600 para cerca de 630 (medir: o
   cabeçalho e as quatro colunas de hoje não podem encolher).
2. `ui/job_actions.py` liga `window.jobs.popup.cancel_requested` e define `cancel_reason`: `delete_command` vazio ("Cancelamento da fila
   desligado: cluster.delete_command está vazio no config.yaml.") ou uma ação em andamento. O clique **fecha o popup primeiro**
   (`popup.hide()`), depois abre o diálogo do R6 com o job da linha (do cache); confirmado, `delete_waiting` no worker ("Cancelando o job
   na fila…") e as mesmas respostas do R4.3.
3. **Testes** (`tests/test_jobs_ui.py` e `tests/test_job_cancel_ui.py`): com `with_mine(..., waiting=2)` e `QSTATUS_MINE`, os botões
   existem só nas linhas de espera do usuário (nenhum em "Em execução", nenhum nos jobs de `usuario_a`); o clique emite o `Job` certo
   (o ID da linha, não o primeiro com o mesmo nome: duas linhas com o mesmo nome e IDs diferentes); `cancel_reason` desabilita com o
   tooltip; o popup fecha antes do diálogo; confirmar com a fila nova igual roda `qdel 25000`; com o job já em "Running jobs" na fila nova,
   o toast de recusa aparece e **nenhum** `qdel` roda; `tests/test_theme_contrast.py` continua verde (sem token novo).

### R6: o diálogo de confirmação

1. `ui/dialogs/cluster_action.py:ask_cancel(parent, rows, method, note, line) -> bool` (`QDialog` modal com `exec()`; lê a resposta, depois
   `deleteLater()`), título "Cancelar simulação", texto "Cancelar esta simulação?":
   - uma tabela de rótulo e valor, uma linha por item: "Job" (nome), "ID", "Dono", "Início" (em execução) ou "Envio" (na fila) com a data
     inteira do `qstatus` (`Job.date`), "Núcleos", "Pasta" (`usuario@host:/caminho`; na fila: "não informada pelo qstatus"); com vários
     jobs em execução na mesma pasta, um bloco por job;
   - "Método:" e o texto do método, em negrito, **só para ler** (nenhum controle o muda): "arquivo de parada do pw.x ({files})" ou
     "qdel {job_id} (o job sai da fila antes de começar)";
   - a nota do método: no `.EXIT`, "O pw.x procura esse arquivo na pasta durante a execução, para de forma limpa (\"Program stopped by user
     request\") e o apaga. Os comandos seguintes do script (outro pw.x, bands.x, projwfc.x…) ainda rodam."; no `qdel`, "Antes do qdel o
     Lain consulta a fila de novo: se o job já começou, nada é feito.";
   - "Comando que vai rodar no cluster:" e a linha exata, em fonte monoespaçada;
   - botões "Cancelar simulação" e "Voltar"; o padrão é "Voltar" (Enter não cancela nada por engano).
2. `ui/job_actions.py` monta `rows`, `method`, `note` e `line` a partir do `StopPlan` (R4) ou do `Job` e de `delete_line` (R5).
3. **Testes** (`tests/test_job_cancel_ui.py`, com `test_atoms_dialog.py:drive_modal`): o diálogo real mostra o nome, o ID, a pasta e o
   método de cada caso; "Voltar" é o padrão; "Voltar" devolve `False` e "Cancelar simulação" `True`.

### R7: regras e documentação

1. `CLAUDE.md`, "Sync safety" (sobre a redação da spec 69): os programas incluem `cluster.delete_command` e o `touch` fixo; uma linha nova:
   "Cancelling a job (spec 70) never guesses: a fresh `qstatus` right before acting decides. A running job is stopped only by creating
   `<prefix>.EXIT` in its folder (matched by its `<name>.o<id>`); `qdel` runs only on a job still waiting, by its ID, never on one that is
   running."
2. PRD §5.1: a linha do modo cluster ganha "and cancels a job (spec 70): `<prefix>.EXIT` when it runs, `qdel` while it waits".
3. `README.md`, "Cluster mode" e "Cluster jobs": "Cancelar simulação…", o botão da fila, a chave `delete_command`, o que o `.EXIT` faz e
   não faz (os comandos seguintes do script ainda rodam).

## Fora de escopo

- Parar o script inteiro (os passos depois do `pw.x` que recebe o `.EXIT`): o método é o do usuário e só para o `pw.x` da vez; outra spec,
  se for preciso (por exemplo, um `.EXIT` para cada passo ou um `qdel` depois do fim do `pw.x`).
- Cancelar job de outro usuário, ou job em execução pelo `qdel`: proibido pelo pedido.
- Mostrar a pasta de um job da fila (`qstat -j <id>` diria o `cwd`; o formato deste cluster não foi visto): o diálogo diz "não informada
  pelo qstatus".
- Apagar um `<prefix>.EXIT` que sobrou (por exemplo, o job terminou antes de ler): o Lain nunca apaga nada no cluster; a spec 69 avisa ao
  submeter.
- Cancelar pelo modo local ou pela barra superior um job em execução: o pedido é pela pasta, no modo cluster.
- Qualquer passo de aceite no cluster real: ele é ambiente de produção (decisão do usuário); a implementação se prova só localmente.
- Um `.EXIT` em `outdir` (`tmp_dir`): o `pw.x` olha a pasta de trabalho primeiro, que é onde o usuário cria o arquivo.

## Decisões assumidas (confirmar na revisão)

Decididas pelo usuário na revisão (25/10/2026):

- **O `.EXIT` para o job em execução fica como descrito:** é a orientação do administrador do cluster. A nota do diálogo (os comandos
  seguintes do script ainda rodam) só informa; o método não muda.
- **Os inputs vão para uma pasta local temporária** (R1), apagada no fim.
- **A regra do `CLAUDE.md` muda** (spec 69, decisão 1) e **nenhum teste chega ao cluster** (spec 69 R7); nenhuma spec tem passo de aceite
  nele.

Assumidas nesta versão:

1. **Onde aparece "Cancelar simulação…":** num item de pasta (árvore ou grade) e num `.qsub` (vale a pasta dele), com um item só.
2. **A verificação do job da fila é pelo ID, numa fila nova**, logo antes do `qdel`: o ID precisa estar em "Waiting jobs", com o mesmo nome e
   dono, e fora de "Running jobs". Um job da fila não tem `<name_job>.o<job-ID>` nem pasta no `qstatus`, então a comparação com o arquivo
   que o pedido descreve vale para o job em execução (R2), e o ID cobre os nomes repetidos. Entre a fila nova e o `qdel` sobra a janela de
   um login (cerca de um segundo), que o escalonador não deixa fechar (um "qdel só se estiver esperando" não existe no SGE, não verificado).
3. **Todo cancelamento confere de novo antes de agir**, também o da pasta (o job pode ter terminado entre o diálogo e o clique): nada roda
   sem a fila nova.
4. **Só os jobs do usuário têm o botão** na fila (o `qdel` de um job alheio falharia, e o pedido é cancelar as "simulações submetidas" pelo
   usuário).
5. **Vários prefixos na pasta:** um `.EXIT` por `prefix` dos inputs do pw.x, criados juntos. Um `.EXIT` de um `prefix` que não está rodando
   para o próximo `pw.x` desse `prefix` no mesmo job (o que se quer de um cancelamento) e, se sobrar, a spec 69 avisa na próxima submissão.
6. **Só inputs do pw.x contam** para o `prefix` (é o `pw.x` que procura o arquivo); `bands.x`, `projwfc.x` e `pp.x` não. Inputs maiores que
   1 MB não são buscados.
7. **Nome igual exatamente** entre o `<name_job>.o<id>` e o `qstatus`, como pedido. Se o `qstatus` cortar nomes longos (não verificado), um
   job com nome longo não seria reconhecido: aceitar o nome do `qstatus` como começo do nome do arquivo é a alternativa de uma linha.
8. **A nota sobre os comandos seguintes do script** entra no diálogo, só como informação (o método é o do administrador): o usuário vê que
   o `.EXIT` para o `pw.x` da vez e que o script segue quando tem mais de um passo. Tirar a nota é uma linha, se ela atrapalhar.

## Notas de implementação

- Novos: `core/remote/inputs.py`, `core/remote/job_cancel.py` (novos, Qt-free, em `QT_FREE`); `tests/test_remote_inputs.py`,
  `tests/test_job_cancel.py`, `tests/test_job_cancel_ui.py`, `tests/test_job_cancel_ssh.py` (novos).
- Alterados: `core/sync/rsync.py` (`small_files_command`, cerca de 430/500), `core/config.py` (`delete_command`, cerca de 488/500) e os dois
  `config.example.yaml`, `ui/job_actions.py` (o item do menu, o popup, as respostas: cerca de 320 linhas; acima de 400, o cancelamento vai
  para um `ui/job_cancel.py` novo), `ui/dialogs/cluster_action.py` (`ask_cancel`), `ui/widgets/jobs_popup.py` (coluna, sinal, `cancel_reason`, cerca
  de 275), `tests/jobs_helpers.py` (fila com dois jobs de mesmo nome), `tests/test_jobs_ui.py`, `tests/test_config.py`,
  `tests/test_architecture.py` (`QT_FREE`), catálogo `lain.po`/`.mo`.
- Ordem: R1 → R2 (sem Qt) → R3 → R6 (diálogo) → R4 → R5 → R7.
- A guarda da spec 69 R7 já está na suíte: todos os testes desta spec rodam localmente (fakes e `tests/ssh_server.py`). Durante a
  implementação, nada roda contra o cluster do usuário: nem `uv run lain` com o `config.yaml` da raiz, nem `ssh` para o host dele.
- Limites: nenhum arquivo passa de 500; `ui/remote_controller.py` e `ui/main_window.py` não mudam (o gancho e a linha são da 69).
- Nenhum `ui/` toca o disco: a pasta temporária dos inputs é criada e apagada no worker (`core/remote/inputs.py`).
- Documentação ao implementar: `CLAUDE.md` (R7.1), PRD §5.1 (R7.2), `README.md` (R7.3), `specs/README.md`.
- i18n: textos novos em `_()`, `scripts/i18n.py update`, tradução ("Cancelar simulação…" → "Cancel simulation…", "Voltar" → "Back"),
  `compile` e `check`.

## Critérios de aceite e testes

- [ ] Sem clicar em cancelar nada muda: o popup sem jobs do usuário na fila fica igual (sem botão), e a suíte existente passa sem mudar
      expectativas (`tests/test_jobs_ui.py`, `tests/test_remote_ui.py`).
- [ ] O `prefix` sai do conteúdo dos inputs do pw.x da pasta do cluster, buscados até 1 MB, sem deixar arquivo temporário
      (`tests/test_remote_inputs.py`).
- [ ] O cancelamento pela pasta só cria `<prefix>.EXIT` quando um `<nome>.o<id>` da pasta é um job do usuário em execução no `qstatus`, com
      ID e nome iguais, conferido de novo antes do `touch` (`tests/test_job_cancel.py`).
- [ ] O `qdel` nunca roda num job em execução nem num job que saiu da fila; a propriedade de `waiting_check` vale para qualquer fila
      (`tests/test_job_cancel.py`, Hypothesis).
- [ ] O popup tem o botão só nos jobs do usuário na fila; o clique fecha o popup e abre a confirmação com o ID da linha
      (`tests/test_jobs_ui.py`, `tests/test_job_cancel_ui.py`).
- [ ] O diálogo mostra nome, ID, pasta, método e o comando exato, com "Voltar" como padrão (`tests/test_job_cancel_ui.py`, `drive_modal`).
- [ ] Pelo `ssh` real contra o servidor local (`127.0.0.1`): o `touch` cria o `<prefix>.EXIT` na pasta servida, o `qdel` falso recebe o ID
      de um job na fila e não é chamado para um job em execução (`tests/test_job_cancel_ssh.py`).
- [ ] Nenhum teste desta spec fala com outro host nem lê o `config.yaml` real: a guarda da spec 69 R7 passa com eles. Não há passo de
      aceite no cluster (ambiente de produção, decisão do usuário).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes, tudo localmente.
