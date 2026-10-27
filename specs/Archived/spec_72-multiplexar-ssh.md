# Spec 72: uma conexão ssh para várias ações: `ControlMaster` no modo cluster

| | |
|---|---|
| **Prioridade** | 72: depois das correções da 71; não bloqueia nada, mas corta a espera de toda ação no cluster (submeter, cancelar, fila, listagem, sync) |
| **Status** | Implementada (27/10/2026). Desvios: o encerramento usa `ssh -O stop` em vez de `-O exit` (decisão do usuário na implementação: o mestre apaga o socket antes de responder e sai quando não resta sessão, e a transferência de outra janela do Lain termina; as do próprio Lain já morreram nos passos "cancelar" e "sync"); `control_dir()` confere com um `isdir` se a pasta ainda existe e a refaz (verificado contra o servidor de teste: sem a pasta, o ssh faz o login e sai com 255, `unix_listener: cannot bind`, sem rodar o comando; todo ssh falharia depois de um limpador do `/tmp`); `mux.sockets(folder)` lista os sockets para o `close_all` e os testes; o `close_all` sem um ssh que rode (`OSError`) registra e devolve `True`; os mestres dos testes fecham em `LocalSSHServer.close()` (cobre todos os servidores, não só os dois fixtures), com `ssh -F /dev/null`; o servidor ganhou `open_connections()`; R4.4 e R4.5 passaram sem mudar o Lain: o ssh troca o socket morto e, na sessão recusada ("Session open refused by peer"), entra por uma conexão própria e roda o comando uma vez; `core/config.py` 490, `core/sync/rsync.py` 442, `ui/shutdown.py` 143, `core/sync/mux.py` 146 |
| **Depende de** | spec 27-3 (`ssh_command`, `StrictHostKeyChecking=yes` forçado), spec 69 (`remote_command`, `run_command`, a guarda `tests/cluster_guard.py`), spec 64 (`fetch_jobs`), spec 65 (`list_remote`), spec 70 (`fetch_stop_sources`, `copy_small_files`), spec 71 (as ações que conferem duas vezes), spec 27-5 (`ui/shutdown.py`), spec 7 (`tests/ssh_server.py`) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1–R3: P cada; R4: M, pelos testes) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda `ssh_command`, o contrato de todo ssh e rsync do Lain, e a regra de segurança do `StrictHostKeyChecking` |

## Itens de origem (achado C8 do relatório de 25/10/2026 e pedido de 26/10/2026)

`Documentation/Relatorios/report-25-10-26-specs-69-70.md`, achado C8, opção (b), que o usuário tirou da spec 71 ("I will address it
separately later") e agora pediu:

> - **(b)** multiplexar o ssh (`ControlMaster=auto`, `ControlPersist` curto, `ControlPath` no diretório de runtime) durante a sequência
>   da ação, reduzindo tudo a um único aperto de mão. A (b) mexe no ssh de todo o Lain (askpass, `StrictHostKeyChecking=yes`) e pede
>   uma spec própria.

> escreva a spec da (b) com o spec-sdd

Medida do usuário no cluster dele (`Documentation/resultado_multiplexacao_ssh_20261026_231840.txt`, ssh local OpenSSH 10.0p2): o mestre
abre e o `-O check` o encontra; **0,25 s** por comando pelo mestre contra **1,65 s** sem; 3 sessões simultâneas sem falha; com 12, duas
mensagens `Session open refused by peer` (o `MaxSessions` do servidor está perto de 10) e, mesmo assim, **0 comandos falharam**. O
usuário não respondeu às duas perguntas de escopo (vale para o rsync também? quanto tempo o mestre fica?): as respostas assumidas estão
em "Decisões assumidas".

## Situação atual

- **R1 (um ponto só para as opções do ssh).** `core/sync/rsync.py:75-98`, `ssh_command(cluster, ssh_binary)`, monta todas as opções
  (`-p`, `StrictHostKeyChecking=yes` em `:83-84`, `ConnectTimeout`, `ServerAliveInterval=15`, `ServerAliveCountMax=3`, `BatchMode=yes`
  ou `NumberOfPasswordPrompts=1`). Só dois lugares o chamam em `src/`: `rsync.py:148` (`-e`, o ssh do rsync: pull, push, listagem,
  dry run, `QProcess` de `core/sync/_process.py:260-300`) e `core/sync/command.py:39-46` (`remote_command`: `qstatus`, `qsub`, `touch`,
  `qdel`, a cópia dos inputs). `remote_command` passa por `run_command` (`command.py:49-77`) em `core/remote/listing.py:151-157`,
  `core/cluster_jobs.py:170-171`, `core/remote/actions.py:116-117` e `core/remote/inputs.py:87-93`. `grep -rn "ControlMaster\|ControlPath\|ControlPersist" src`
  não acha nada: cada chamada é um login completo. As ações de submeter e cancelar fazem 5 (submeter: listagem + `qstatus`, depois
  listagem + `qstatus` + `qsub`; cancelar pela pasta: listagem + `qstatus` + cópia dos inputs, depois `qstatus` + `touch`).
- **R2 (nada fecha um mestre).** `ui/shutdown.py:85-119` (`steps_for`): o passo "cancelar" (`:89-99`) mata os ssh em curso
  (`run_command` os mata, `command.py:80-92`), e o passo "sync" (`:109`) espera o rsync. Nenhum passo conhece um ssh que fica vivo depois
  do comando. Um mestre com `ControlPersist` sobreviveria ao app até o tempo acabar.
- **R3 (comportamento a provar, medido no servidor de teste, sem o cluster).** Num script descartável (scratchpad, fora do repositório)
  contra `tests/ssh_server.py` em `127.0.0.1`: três `subprocess.Popen(ssh … -o ControlMaster=auto -o ControlPath=… -o ControlPersist=20 … true)`
  com `stdout`/`stderr` em pipe e `start_new_session=True`, como `run_command`, voltaram em **0,05–0,06 s** cada (`communicate()` não
  espera o `ControlPersist`: o mestre troca os descritores por `/dev/null` ao se desligar) e o servidor viu **1 login e 3 execuções**.
  **Não verificado:** o que acontece com o `QProcess` do rsync (mesma ideia, mas não foi medido); uma conexão recusada por
  `MaxSessions` (o resultado do usuário, 0 falhas com 2 recusas, sugere que o próprio ssh refaz o comando por uma conexão nova; **inferido,
  não lido no código do ssh**); um socket morto deixado por um mestre morto à força; o sufixo temporário que o ssh acrescenta ao
  `ControlPath` ao criar o socket (a conta do tamanho abaixo usa uma folga).
- **R4 (testes).** `tests/ssh_server.py:146-149` (`check_channel_request`) aceita qualquer número de sessões; `:207-233`
  (`ssh_binary`) escreve o `ssh_config` temporário; `tests/conftest.py:66-71` (`_isolated_user_dirs`) redireciona `XDG_DATA_HOME`,
  `XDG_CONFIG_HOME` e `XDG_CACHE_HOME`, **não** `XDG_RUNTIME_DIR`; o `ssh_server` (`:273-292`) só fecha o servidor no fim, sem saber de
  nenhum processo ssh. Testes existentes contam logins: `tests/test_cluster_jobs_ssh.py:88` espera exatamente `[False]` em
  `server.attempts`. `tests/test_sync_rsync.py:42-66` confere o argv de `ssh_command`. `core/config.py` tem 488 de 500 linhas;
  `core/sync/rsync.py`, 440; `ui/shutdown.py`, 136; `core/sync/command.py`, 92; `core/appdirs.py`, 149.

## Requisitos

### R1: `core/sync/mux.py` (novo), a multiplexação num módulo Qt-free

1. Módulo novo `src/qe_studio/core/sync/mux.py` (entra em `QT_FREE`, `tests/test_architecture.py:67`). Constantes: `PERSIST_SECONDS = 120`
   (o que o usuário testou) e `MAX_DIR_CHARS = 42` (o `ControlPath` é `<pasta>/%C`; `%C` expande para 40 caracteres, o ssh acrescenta um
   sufixo temporário de cerca de 17, e o caminho de um socket Unix aceita 104 no BSD/macOS: `42 + 1 + 40 + 17 = 100`).
2. `control_dir() -> Path | None`: a pasta dos sockets. `$XDG_RUNTIME_DIR/qe-studio-mux` quando a variável existe e é absoluta; senão
   `<tempfile.gettempdir()>/qe-studio-mux-<uid>`. Cria com modo `0o700`, e **só devolve** uma pasta que seja diretório real (não
   link), do próprio usuário (`st_uid == os.getuid()`) e sem permissão para grupo e outros (se for do usuário e tiver permissão a mais,
   `chmod 0o700`). Devolve `None` quando algo disso falha, quando o caminho passa de `MAX_DIR_CHARS`, e em `sys.platform == "win32"`
   (o OpenSSH do Windows não multiplexa: **não verificado**, a opção fica desligada ali). `functools.lru_cache` pela base: só a primeira
   chamada toca o disco (como `askpass_program`, que a `child_env` já chama antes de cada ssh); uma chamada na thread da GUI paga isso uma vez.
3. `options(cluster: ClusterConfig) -> list[str]`: `[]` se `cluster.multiplex` for falso ou `control_dir()` for `None`; senão
   `["-o", "ControlMaster=auto", "-o", f"ControlPath={dir}/%C", "-o", "ControlPersist=120"]`. Uma lista, sempre os mesmos tokens, para o
   teste conferir por igualdade.
4. `close_all(ssh_binary: str, timeout_s: float) -> bool`: para cada socket (`stat.S_ISSOCK`) em `control_dir()`, roda
   `ssh -O stop -S <socket> localhost` (o rascunho dizia `-O exit`; o `-S` leva direto ao socket; o destino só preenche o argumento), com `ssh_binary`,
   `stdin=DEVNULL`, tempo limite repartido entre eles; ignora falha de socket já morto. Devolve se terminou no tempo. Sem `control_dir()`
   ou sem sockets: `True` sem rodar nada. Nunca levanta.
5. Log (nível `debug`, em inglês) do que `options` decidiu uma vez por processo; **nenhum texto novo para o usuário**: sem `_()`, sem
   `.po`.
6. **Testes** (`tests/test_ssh_mux.py`, novo, sem rede): `options` com tudo ligado dá os seis tokens; `[]` com `multiplex=False`, com
   `sys.platform` trocado por `win32`, com `XDG_RUNTIME_DIR` apontando para uma pasta de caminho longo (43 caracteres), e quando a pasta
   `qe-studio-mux` existe como link ou de outro dono (o dono se simula trocando `os.getuid`); a pasta é criada com `0o700`; uma já
   existente com `0o755` do próprio usuário é corrigida; `close_all` sem pasta nem sockets devolve `True` sem `Popen`.

### R2: `ssh_command` usa a multiplexação, com um interruptor

1. `core/config.py:ClusterConfig` ganha `multiplex: bool = True`, com um comentário de uma linha ("one ssh connection shared by the
   actions on the cluster (spec 72); false: every ssh logs in by itself"), e entra nas **duas** cópias de `config.example.yaml` (raiz e
   `src/qe_studio/resources/`, idênticas: `tests/test_config.py`), documentado como os outros campos de `cluster`.
2. `ssh_command` (`rsync.py:75-98`) acrescenta `mux.options(cluster)` **antes** de devolver, depois das opções de hoje. Todas as
   opções de hoje ficam (`StrictHostKeyChecking=yes` no argv vence o `~/.ssh/config`; o mestre nasce com ele). Os `-o` do Lain
   vencem também um `ControlMaster`/`ControlPath` do `~/.ssh/config` do usuário; quem não quer isso põe `multiplex: false`.
3. Nada muda em quem chama `ssh_command`: `rsync -e` e `remote_command` herdam as opções. A senha (`auth: password`) continua só no
   `SSH_ASKPASS` do ambiente do filho; com o mestre, o askpass roda **uma vez** (no ssh que cria o mestre).
4. `rsync.py` não passa de 450 linhas (acrescenta uma importação e uma linha); `config.py` não passa de 495 (o campo e o comentário).
   Se passar, o campo vai para onde o `test_architecture.py` mandar, sem `SIZE_EXCEPTIONS`.
5. **Testes** (`tests/test_sync_rsync.py`, `tests/test_config.py`): `ClusterConfig().multiplex is True`; `ssh_command` com a
   multiplexação ligada contém os seis tokens depois de `StrictHostKeyChecking=yes`, e com `multiplex: false` o argv é **idêntico ao de
   hoje** (a comparação com a lista de antes, escrita no teste); as duas cópias do `config.example.yaml` seguem idênticas; os testes de
   `test_sync_rsync.py:42-66` mantêm o que provam (chave/senha/`StrictHostKeyChecking`) e passam a fixar `multiplex=False` quando
   comparam o argv inteiro.

### R3: fechar os mestres no encerramento

1. `ui/shutdown.py:steps_for` ganha o passo `Step("ssh", close_ssh, cap_ms=1000)` **logo depois** do "sync" (o rsync em curso já
   acabou ou foi morto) e antes das exportações; `close_ssh(ms)` chama `mux.close_all(config.sync.ssh_binary, ms / 1000)` e devolve o
   resultado (`False`: não acabou no tempo, e o encerramento só registra, como nos outros passos). A janela já está escondida
   (`run_shutdown`); o comando fala só com um socket local, e o tempo é o do passo.
2. Quem fecha a conexão do cluster não precisa de senha nem de rede. Sem `ssh_binary` válido (`OSError`), o passo registra e segue.
3. Um mestre que sobrar (o app morreu à força) acaba sozinho em `PERSIST_SECONDS` sem cliente; o socket morto que ficar é refeito pelo
   próximo ssh (R4.4).
4. **Testes** (`tests/test_shutdown.py`): os passos de `steps_for` incluem "ssh" imediatamente depois de "sync"; com `mux.close_all`
   trocado por um falso que registra a chamada, o fechamento da janela o chama uma vez com o `ssh_binary` da configuração; se o falso
   devolve `False`, o relatório tem "ssh" em `late` e os passos seguintes ainda rodam.

### R4: comportamento contra o servidor de teste

Todos em `tests/test_ssh_mux.py` (novo), com o `ssh_server` e o ssh real; **nenhum chega ao cluster** (a guarda de `tests/cluster_guard.py`
continua valendo, e o destino do `close_all` é `localhost`).

1. **Um login para várias ações.** Com `multiplex=True`: três `run_command(remote_command(...))` seguidos, mais um `list_remote` e um
   `fetch_jobs`, deixam `len(server.attempts) == 1` e uma execução no `server.commands()` por chamada.
2. **O `run_command` não espera o mestre.** O mesmo trio volta em menos de 5 s no total (o `ControlPersist` do teste é de 120 s): se o
   mestre segurasse os pipes, o `communicate()` demoraria. O pull e o push do `test_sync_ssh.py` (pelo `QProcess`) acabam sem esperar
   o `ControlPersist` e deixam o mesmo único login.
3. **Senha uma vez.** Com `auth: password` (askpass real do servidor de teste), três comandos deixam uma única tentativa de senha
   aceita em `server.attempts`, e a senha nunca aparece num argv nem no log (como em `test_cluster_jobs_ssh.py`).
4. **Socket morto.** Depois do primeiro comando, mata-se o mestre com `SIGKILL` (o pid vem do `ssh -O check`); o comando seguinte
   **ainda funciona** (um segundo login). Se isso falhar com o ssh de hoje, a spec vira: apagar o socket morto antes de tentar.
5. **Sessão recusada.** O servidor ganha `max_sessions: int | None = None` (`tests/ssh_server.py`, `check_channel_request` devolve
   `OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED` a partir da N-ésima sessão aberta de uma conexão). Com `max_sessions=1` e um comando
   `sleep` do servidor segurando a sessão, um segundo comando **termina com código 0 e roda uma única vez** (o ssh refaz por uma
   conexão nova: `len(server.attempts) == 2`). É o que se lê no resultado do usuário (inferido). **Se o teste falhar** (código 255 ou o
   comando rodar duas vezes), `run_command` repete **uma vez** sem multiplexação, só quando o `stderr` traz `Session open refused by
   peer`, e só para um comando que a recusa garante que não começou; a spec do teste continua a mesma.
6. **A chave do servidor continua obrigatória.** Com `known_hosts="other"` (chave trocada) e `multiplex=True`, o comando falha como
   hoje (a mensagem de chave mudada) e **nenhum socket** fica em `control_dir()`; com `known_hosts="empty"`, idem.
7. **Fechar.** `mux.close_all` depois de um comando: o `ssh -O check` para o mesmo socket falha, a pasta não tem mais sockets, e o
   comando seguinte faz um segundo login. O `close_all` com um socket morto na pasta não levanta e devolve `True`.
8. **Caminho no limite.** Com `XDG_RUNTIME_DIR` apontando para uma pasta de exatamente `MAX_DIR_CHARS` caracteres no `/tmp`, o mestre
   abre (prova a conta do tamanho); com um a mais, `options` dá `[]` e o comando funciona sem mestre.
9. **Limpeza.** O fixture `ssh_server` (e o de `test_cluster_jobs_ssh.py`) chama `mux.close_all` no fim, antes de `server.close()`:
   nenhum `ssh` mestre sobrevive a um teste; `tests/conftest.py:_isolated_user_dirs` passa a incluir `XDG_RUNTIME_DIR`, apontado para
   uma pasta **curta** (`tempfile.mkdtemp(prefix="lm")` em `/tmp`, apagada no fim; o `tmp_path_factory` dá caminhos longos demais) para
   que o teste nunca toque o `/run/user` real e os sockets caibam no limite.
10. **O padrão dos testes de hoje.** `LocalSSHServer.config_data` ganha o parâmetro `multiplex: bool = False`: as dezenas de testes
    que contam logins ou execuções continuam provando o caminho sem mestre; só `test_ssh_mux.py` liga `multiplex=True`. Um teste fixa
    que o **padrão de produção** (`parse_config` sem a chave) é `True`.

## Fora de escopo

- **Listagem e `qstatus` em paralelo** (a opção (a) do C8): outra spec, se a espera ainda incomodar depois desta; as duas se somam (as
  duas threads usam o mesmo mestre).
- **`jobs_poll_seconds` (300 s) mais longo que o `ControlPersist`**: a consulta periódica da fila abre um mestre novo a cada vez (1 login,
  como hoje) e ele fica 120 s; só as ações em sequência (as que o usuário dispara) aproveitam. Estender o `ControlPersist` para cobrir a consulta
  deixaria uma sessão autenticada ociosa por muito mais tempo: decisão do usuário.
- **`ControlPersist` configurável**, `ProxyJump`/`ProxyCommand` e hosts atrás de um nó de entrada: o `%C` já separa um destino de outro;
  qualquer ajuste fino é adiado até alguém precisar.
- **Windows**: a multiplexação fica desligada (R1.2); suporte, se existir, é outra spec.
- **A sonda TCP de `core/sync/monitor.py`** não usa ssh (só `connect`): não muda.
- **Fechar a janela entre a última conferência e o comando** (a corrida da spec 69/70): continua de um login; o mestre a encurta em
  tempo, não em lógica, e as regras do `CLAUDE.md` seguem proibindo decidir no cluster num comando só.

## Decisões assumidas (confirmar na revisão)

1. **Vale para tudo que passa por `ssh_command`, o rsync inclusive** (o usuário não respondeu). É o caminho que tem um ponto só; a
   alternativa mais leve é um parâmetro `multiplex=False` em `rsync.py:148` e deixar o sync como está. Escolhi o amplo porque uma
   listagem/dry run seguidos de uma ação (cancelar, plotar) se beneficiam do mesmo mestre.
2. **`ControlPersist` de 120 s, constante.** É o que o usuário mediu; cobre ler o diálogo de confirmação (que fica entre a conferência e o
   comando) sem manter uma sessão autenticada ociosa por muito tempo. Se o usuário ficar mais que isso no diálogo, a conferência seguinte
   abre um mestre novo: correto, só mais lento.
3. **Interruptor `cluster.multiplex` (padrão ligado).** Para um cluster ou política que proíba, e para depurar. Não há janela de
   ajustes (PRD §6): é um campo do `config.yaml`.
4. **O Lain vence o `~/.ssh/config`** (como já faz com `StrictHostKeyChecking`): as opções vão no argv.
5. **Um mestre por destino** (`%C` = máquina local, host, porta e usuário), não por chave ou modo de autenticação. O `config.yaml` só
   é lido na partida (não há janela de ajustes), então uma mudança de chave reinicia o app, que fecha os mestres.
   **Corrigido na implementação:** existe "Recarregar config.yaml". Depois dele, um mestre do mesmo host, porta e usuário segue
   servindo até 120 s com o login antigo (uma nova `key_path` ou `auth` vale depois disso; outro host, usuário ou porta abre um
   mestre novo na hora). Inofensivo: nada foi feito para isso.
6. **Sem repetição na sessão recusada**, a menos que o teste R4.5 mostre que o ssh não refaz sozinho (inferido do resultado do usuário).
7. **Windows desligado.** Conservador: não consegui verificar o suporte do OpenSSH do Windows. **Nota da implementação:** no macOS
   sem `XDG_RUNTIME_DIR`, o `gettempdir()` (`/var/folders/…/T`) passa de `MAX_DIR_CHARS`, e a multiplexação também fica desligada.
8. **O padrão dos testes é sem mestre** (R4.10): preserva a leitura dos testes existentes; os novos ligam a opção.

## Notas de implementação

- Novos: `src/qe_studio/core/sync/mux.py`, `tests/test_ssh_mux.py`.
- Alterados: `core/sync/rsync.py` (`ssh_command` chama `mux.options`), `core/config.py` (`ClusterConfig.multiplex`), as duas cópias de
  `config.example.yaml`, `ui/shutdown.py` (o passo "ssh"), `tests/ssh_server.py` (`max_sessions`; `config_data(multiplex=False)`),
  `tests/conftest.py` (`XDG_RUNTIME_DIR` curto; limpeza no `ssh_server`), `tests/test_cluster_jobs_ssh.py` (limpeza no fixture),
  `tests/test_sync_rsync.py`, `tests/test_config.py`, `tests/test_shutdown.py`, `tests/test_architecture.py` (`QT_FREE`).
- Limites: `core/config.py` 488 de 500 (o campo cabe em 3 linhas); `core/sync/rsync.py` 440 (+2); `ui/shutdown.py` 136; nenhum arquivo
  perto do limite fora o `config.py`.
- Ordem: R1, R2, R3, depois R4 (R4.9 e R4.10 antes dos outros testes, para a suíte inteira continuar verde a cada passo).
- Documentação ao implementar: `README.md` (a seção do ssh: o mestre, o `multiplex`, o `ControlPersist` de 120 s, a pasta dos sockets e a
  nota de que o `MaxSessions` do cluster limita as sessões simultâneas), `config.example.yaml` (R2.1), e **uma linha** na seção "Sync
  safety" do `CLAUDE.md` (as opções do ssh só nascem em `ssh_command`; o mestre usa `ControlPath` curto em `control_dir()` e fecha no
  encerramento). Nenhum texto novo para o usuário: o catálogo `.po` não muda.
- Sem passo de aceite no cluster: o cluster é produção e o usuário já mediu o que importava.

## Critérios de aceite e testes

- [x] `multiplex: false` dá um argv de ssh idêntico ao de hoje, e toda a suíte atual passa sem mudança de lógica
  (`test_sync_rsync.py`, `test_sync_ssh.py`, `test_cluster_jobs_ssh.py`, `test_job_submit_ssh.py`, `test_job_cancel_ssh.py`, `test_config.py`).
- [x] Cinco chamadas de ssh seguidas deixam um login no servidor de teste (R4.1), e voltam sem esperar o `ControlPersist` (R4.2).
- [x] Com `auth: password`, o askpass roda uma vez e a senha não vai a argv nem a log (R4.3).
- [x] Um socket morto e uma sessão recusada não fazem nenhum comando falhar nem rodar duas vezes (R4.4, R4.5).
- [x] Uma chave de servidor trocada ou desconhecida continua recusando o comando, sem deixar socket (R4.6).
- [x] `mux.close_all` e o passo "ssh" do encerramento fecham os mestres; nenhum `ssh` mestre sobrevive a um teste (R3, R4.7, R4.9).
- [x] O limite do caminho do socket está provado nos dois lados (R4.8), a pasta é `0700` do próprio usuário (R1.6).
- [x] O padrão de produção é ligado (R4.10), as duas cópias do `config.example.yaml` seguem idênticas.
- [x] Nenhum teste toca o cluster real nem o `/run/user` real (a guarda e o `XDG_RUNTIME_DIR` dos testes).
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes;
  `scripts/i18n.py check` sem mudança (nenhum texto novo).
