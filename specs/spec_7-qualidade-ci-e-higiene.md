# Spec 7: Qualidade, CI e higiene do projeto

| | |
|---|---|
| **Prioridade** | 7 (base mínima: protege todas as specs seguintes) |
| **Status** | Rascunho para revisão |
| **Depende de** | nenhuma |
| **Usada por** | spec 8 (pyright no CI), spec 14 (job de desempenho), spec 17 (testes de sync), todas as demais (CI) |
| **Esforço** | G (o servidor SSH de teste é a maior parte) |

## Itens de origem (`report.md`)

> **A6. Sem CI**: não há `.github/`. → workflow com `uv sync`, `ruff check/format`, `pytest` (offscreen, rsync instalado), `-m perf` opcional.
>
> **A7. Higiene/empacotamento**: sem `setWindowIcon`/`desktopFileName` (ícone genérico na barra de tarefas); sem `.desktop`; README l.4 aponta `Documentation/PRD.md`, que não existe (é `specs/spec_0-PRD.md`); WIP não commitado.
>
> **2.3 Robustez e testes**: fixtures cobrem QE 7.1 e 7.3.1: adicionar saídas 6.x / 7.2 / 7.4 · testes de propriedade (Hypothesis) para `parse_relax` e `read_gnu` · `TextViewer.reload` sem uso: remover ou passar a usar · remover `plot.export.theme`.

Decisões do usuário (30/09/2026): o foco é o **QE 7.1 ou mais novo**. Nada de fixtures nem de suporte
específico para versões mais antigas. O F10 (acompanhamento ao vivo) foi adiado, então o
`TextViewer.reload` sem uso é removido.

Decisão de arquitetura do usuário, registrada no `CLAUDE.md` (30/09/2026):
> Para os testes de sincronização com cluster, crie um servidor ssh local, com paramiko apontando para uma pasta com arquivos de testes.

## Situação atual

- **Sem CI.** Não há `.github/`, `.gitlab-ci.yml`, Makefile, tox, nox nem pre-commit. Os testes rodam só
  na máquina do desenvolvedor.
- `pyproject.toml`:
  - `[dependency-groups].dev`: `pytest>=8`, `pytest-qt>=4.4`, `pytest-timeout>=2.3`, `ruff>=0.6`;
  - pytest com `addopts = "-m 'not realdata'"`, então os testes `perf` rodam por padrão.
- **Ícone.** `ui/app.py:66-68` define só o nome da aplicação, a organização e a versão. Não há
  `setWindowIcon` nem `setDesktopFileName`, então a barra de tarefas mostra um ícone genérico. Não existe
  ícone do app no repositório (`ui/resources/icons/` só tem glifos Material Symbols), nem arquivo
  `.desktop` (o `core/desktop_apps.py` só **lê** os `.desktop` do sistema).
- **README.** `README.md:4` aponta para `Documentation/PRD.md`, removido no commit `ceccffe`. O PRD agora é
  `specs/spec_0-PRD.md`.
- **Fixtures** (`tests/fixtures/README.md`): QE 7.3.1 (`al_*`, `si_*`), QE 7.1 (`kao_*`) e uma QE 6.0
  (`ni_pdos_spin`, exemplo oficial). Não há saídas do 7.2 nem do 7.4.
- **Parsers sem testes de propriedade.** `bands_x.read_gnu` (`core/qe/bands_x.py:32`) e
  `qe/relax.parse_relax` são testados só com fixtures e alguns textos sintéticos.
- **Código morto:**
  - `TextViewer.reload()` (`ui/widgets/workspace.py:107-108`) não é chamado em lugar nenhum. Se fosse,
    leria até 4 MB no thread da GUI;
  - `plot.export.theme` (`core/config.py:120-122`) não tem efeito. Só gera o aviso de descontinuado
    (`config.py:274-277`, testado em `tests/test_config.py:142-150`). Já saiu do `config.example.yaml`,
    mas o `config.yaml` local do usuário ainda tem `theme: current`, então o aviso aparece a cada
    início.
- As seções do config usam `extra="forbid"` (`config.py:65`), e uma chave desconhecida vira erro
  "chave desconhecida" (`config.py:236-237`). Por isso, apagar o campo do modelo quebraria configs antigos.
- **Testes de sync sem ssh de verdade.** `tests/fake_ssh.py` é um falso `ssh`:
  - os testes põem `sync.ssh_binary = "python tests/fake_ssh.py"` (`tests/test_sync_integration.py:22-34`,
    `tests/test_sync_ui.py:20,46`);
  - quando o rsync chama `<ssh> [opções] host rsync --server …`, o script descarta as opções e o host e
    roda o comando na própria máquina com `sh -c`. Com `FAKE_SSH_LOG`, anota o host e o comando;
  - o rsync real, os excludes, os nomes com acento, as datas e os conflitos são exercitados, mas **nada
    do ssh**: as opções montadas por `ssh_command` (`core/sync/rsync.py:59-76`: `-p`, `ConnectTimeout`,
    `BatchMode`, `-i`/`IdentitiesOnly`, `NumberOfPasswordPrompts`) nunca chegam a um ssh real;
  - também ficam sem teste a autenticação por senha via `SSH_ASKPASS` (`core/sync/askpass.py`), a recusa
    de chave de host desconhecida (o askpass responde "no" a perguntas `yes/no`), a conexão recusada e a
    queda no meio da transferência.

## Requisitos

### R1: Integração contínua (GitHub Actions)
1. Novo `.github/workflows/ci.yml`, disparado em `push` e `pull_request`:
   - `ubuntu-latest`, Python 3.11 e 3.12 (matriz), uv via `astral-sh/setup-uv` com cache;
   - pacotes do sistema: `rsync` e `openssh-client` (R7), mais as bibliotecas que o Qt offscreen exige
     (`libegl1`, `libxkbcommon0`, `libfontconfig1`, `libdbus-1-3` e o que faltar ao rodar);
   - passos: `uv sync`, `uv run ruff check .`, `uv run ruff format --check .` e
     `uv run pytest -m "not realdata and not perf"`.
2. Job separado `perf` (`uv run pytest -m perf`), com `continue-on-error: true`. Em runners compartilhados
   o tempo varia, então ele informa sem bloquear o merge.
3. Os testes de sync rodam com o `rsync` e o `ssh` reais (pulam sozinhos se faltar algum). No CI os dois
   estão instalados, então não pulam.
4. O `README.md` ganha a seção "Desenvolvimento" com o badge do CI e os mesmos comandos do `CLAUDE.md`.

### R2: Ícone e integração com o desktop
1. Ícone próprio do Lain em `src/qe_studio/ui/resources/app/lain.svg`, mais PNGs 16, 32, 48, 64, 128
   e 256 px gerados a partir dele (o script `scripts/fetch_assets.py` ou um novo
   `scripts/build_icons.py` gera os PNGs; os arquivos gerados são versionados).
2. `ui/app.py`: `app.setWindowIcon(QIcon(...))` com todos os tamanhos e
   `QGuiApplication.setDesktopFileName("lain")`, para que o compositor (Wayland/X11) associe a janela ao
   `.desktop`.
3. `packaging/lain.desktop` (`Type=Application`, `Name=Lain`, `GenericName=QE Studio`,
   `Exec=lain %F`, `Icon=lain`, `Categories=Science;Physics;Education;`, `StartupWMClass=lain`).
4. `scripts/install_desktop.py` copia o `.desktop` para `$XDG_DATA_HOME/applications` e os PNGs para
   `$XDG_DATA_HOME/icons/hicolor/<N>x<N>/apps/lain.png`. Nada é instalado sem o usuário rodar o
   script, e o README explica o passo.

### R3: README
1. Corrigir o link da linha 4 para `specs/spec_0-PRD.md`.
2. Citar `specs/README.md` como índice das specs.

### R4: Fixtures do QE 7.1 em diante
1. Política, registrada em `tests/fixtures/README.md`: o Lain dá suporte ao QE ≥ 7.1. Fixtures novas
   são sempre de 7.1 ou mais novo. A `ni_pdos_spin` (6.0) fica, porque é a única PDOS com spin, até a
   fixture com spin da spec 13 substituí-la.
2. Novas fixtures reais e reduzidas, uma pasta por versão: `qe72_al/` e `qe74_al/` (ou outro sistema
   pequeno), cada uma com `scf.out`, a saída do bands.x com `.gnu` e uma PDOS curta. São reduzidas como
   as demais e documentadas no README das fixtures (ver "Pendência").
3. Testes parametrizados por versão para `sniff`, `parse_pw_output`, `read_gnu`, `parse_bandsx_output` e
   `load_pdos`, verificando: o formato da linha de Fermi, o separador de blocos do `.gnu` (linha vazia no
   7.3, espaço no 7.1) e o cabeçalho das colunas da PDOS.
4. Nenhum código novo para tratar formatos anteriores ao 7.1.

### R5: Testes de propriedade (Hypothesis)
1. `hypothesis` no grupo dev.
2. `tests/test_properties.py`:
   - `read_gnu`: para matrizes aleatórias (nbnd × nks), o texto gerado com cada separador (linha vazia,
     linha com espaço) é lido de volta igual (com `allclose`). Um texto truncado no meio de uma linha ou
     com bandas de tamanhos diferentes gera `BandsFormatError` e nunca outra exceção;
   - `parse_relax`: para sequências aleatórias de passos completos e um corte aleatório do texto, o
     parser nunca levanta exceção, os passos devolvidos são um prefixo dos passos gerados e
     `truncated_steps` ≤ 1.
3. Perfil `ci` com `max_examples` menor e `deadline=None` (o tempo do runner varia), selecionado por
   `HYPOTHESIS_PROFILE`.
4. As specs que criam parsers novos (9, 11 e 12) acrescentam os seus casos neste arquivo.

### R6: Remoção de código morto
1. Remover `TextViewer.reload()` (`workspace.py:107-108`).
2. Remover o campo `plot.export.theme` do modelo. Para não quebrar configs antigos:
   - antes da validação, `parse_config` retira `plot.export.theme` dos dados brutos e registra o aviso
     "plot.export.theme foi removido e é ignorado: apague a linha do config.yaml.";
   - qualquer outra chave desconhecida continua sendo erro.
3. Ajustar `tests/test_config.py:142-150` para o novo aviso.

### R7: Servidor SSH local (paramiko) para os testes de sync
1. `paramiko` no grupo dev. Novo módulo de teste `tests/ssh_server.py` com a classe `LocalSSHServer` e o
   fixture `ssh_server` em `conftest.py`.
2. O servidor:
   - escuta em `127.0.0.1`, numa porta livre (bind na porta 0), num thread daemon, um thread por
     conexão;
   - tem chave de host RSA gerada por sessão de testes (`paramiko.RSAKey.generate(2048)`), salva num
     diretório temporário;
   - serve uma **pasta temporária de arquivos de teste** como o "cluster". O fixture devolve
     `(server, remote_root)`, e o teste cria os arquivos remotos ali;
   - autentica por **chave pública** (par de chaves do cliente gerado no diretório temporário, `0600`) e
     por **senha** (valor fixo do teste). Usuário fixo `lain-test`;
   - atende `exec` (`check_channel_exec_request`): roda o comando recebido como subprocesso **local**
     (`shlex.split`, sem shell), com `cwd = remote_root`, e liga stdin/stdout/stderr ao canal nos dois
     sentidos. No fim, envia o código de saída (`send_exit_status`) e fecha o canal;
   - **lista de comandos permitidos**: só `rsync --server …` e `true`/`echo` (sondas). Qualquer outro
     comando é recusado com código 127 e registrado, para o teste não executar comandos arbitrários;
   - guarda um log de conexões (usuário, método de autenticação, comando), que os testes consultam no
     lugar do `FAKE_SSH_LOG`;
   - tem modos de falha controlados pelo teste:
     - `reject_auth` (toda autenticação falha);
     - `drop_after_bytes=N` (fecha o canal depois de N bytes de stdout, para simular queda);
     - `stall_banner` (aceita o TCP e não manda o banner, para o `ConnectTimeout`).
3. Isolamento do cliente: o `ssh` real **nunca** lê `~/.ssh`. O OpenSSH usa o home do `passwd`, não
   `$HOME`, então redirecionar `XDG_*` não basta. O fixture escreve um `ssh_config` temporário com:
   ```
   Host lain-test-host
     HostName 127.0.0.1
     Port <porta>
     UserKnownHostsFile <tmp>/known_hosts
     GlobalKnownHostsFile /dev/null
     StrictHostKeyChecking yes
     UpdateHostKeys no
   ```
   O `known_hosts` temporário recebe `[127.0.0.1]:<porta> ssh-rsa <chave do servidor>`. A config do Lain
   nos testes usa `sync.ssh_binary = "ssh -F <tmp>/ssh_config"` (o `ssh_binary` já passa por
   `shlex.split`), `cluster.host = "lain-test-host"`, `cluster.port = <porta>`,
   `cluster.user = "lain-test"` e `paths.remote_root = remote_root`.
4. Migração:
   - `test_sync_integration.py` e `test_sync_ui.py` passam a usar o `ssh_server` no lugar do
     `fake_ssh.py`. Os testes com "remoto" como caminho local (sem ssh) continuam como estão;
   - `tests/fake_ssh.py` é **removido**, junto com o `FAKE_SSH_LOG`;
   - `test_sync_monitor.py` ganha um caso que sonda a porta do `ssh_server` (estado "online") e uma
     porta fechada ("offline").
5. Testes novos que o servidor permite:
   - pull completo com **autenticação por chave** (`BatchMode=yes`, `-i <chave>`, `IdentitiesOnly`);
   - pull com **senha via `SSH_ASKPASS`**: o `qe-studio-askpass` recebe o prompt e a senha chega só pelo
     ambiente do filho (o log do servidor mostra o método `password`; a senha não aparece em argv nem
     nos logs do Lain);
   - senha errada → sync FAILED com mensagem de autenticação, sem arquivos locais criados;
   - **chave de host desconhecida** (known_hosts vazio) → recusada, nos dois modos de autenticação
     (`BatchMode` e o "no" do askpass), com status FAILED;
   - chave de host **trocada** (known_hosts com outra chave) → recusada;
   - porta fechada → "Conexão recusada pelo cluster" (mensagem de `rsync.py:250`);
   - `stall_banner` → falha dentro de `cluster.connect_timeout` (configurado em 2 s no teste);
   - `drop_after_bytes` → FAILED, e nenhum arquivo parcial fica com o nome final (o rsync usa temporário).
6. Requisitos dos testes: pulam se faltar `rsync` ou `ssh` (`shutil.which`). O servidor é encerrado no
   teardown do fixture (fecha o socket e espera os threads com timeout), dentro dos 60 s do
   `pytest-timeout`.
7. O `CLAUDE.md` (seção "Testing notes") passa a descrever o `ssh_server`, e sai a menção ao
   `fake_ssh.py`.

## Fora de escopo
- Fixtures ou correções para QE 6.x ou 7.0.
- Pacote PyPI, Flatpak, AppImage ou instalador para Windows.
- Publicação automática (release) pelo CI.

## Decisões assumidas (confirmar na revisão)
1. CI no **GitHub Actions** (o relatório cita `.github/`). Se o repositório estiver em outro serviço,
   o R1 é traduzido para ele.
2. O job `perf` não bloqueia o merge (R1.2).
3. O ícone é desenhado do zero, no estilo do design system (`Documentation/design system (UX)/`).
   Não há marca prévia.
4. Instalar o `.desktop` é um passo manual (R2.4), e não um efeito de `uv sync`.
5. `plot.export.theme` vira aviso e é ignorado (R6.2), em vez de erro.
6. O servidor de teste executa os comandos como subprocessos locais com lista de permitidos (R7.2), e não
   implementa SFTP nem shell interativo (o Lain usa só `exec`).
7. A chave de host do servidor é RSA (`paramiko.RSAKey.generate`), que funciona em qualquer versão do
   paramiko. Ed25519 fica de fora porque o paramiko não gera chaves desse tipo.
8. O `ssh_config` temporário (R7.3) é passado via `sync.ssh_binary`. O código de produção
   (`ssh_command`) não muda por causa dos testes.

## Pendência
- **Fixtures QE 7.2 e 7.4:** o usuário precisa fornecer saídas reais (scf + bands.x + projwfc de um
  sistema pequeno) dessas versões. Sem elas, o R4.2 e o R4.3 ficam só com 7.1 e 7.3.1.
- **WIP não commitado** (remoção do `Documentation/Relax-Viewer-/`, docstrings, `extend-exclude`): deve
  ser commitado pelo usuário antes de começar a implementação, para o primeiro CI rodar sobre uma base
  limpa.

## Notas de implementação
- Novos: `.github/workflows/ci.yml`, `packaging/lain.desktop`, `scripts/install_desktop.py`,
  `src/qe_studio/ui/resources/app/`, `tests/test_properties.py`, `tests/ssh_server.py`,
  `tests/test_ssh_server.py` (testes do próprio servidor: autenticação, lista de permitidos, encerramento).
- Alterados:
  - `pyproject.toml` (dev: `hypothesis`, `paramiko`), `ui/app.py`, `README.md`, `core/config.py`;
  - `ui/widgets/workspace.py`, `tests/conftest.py` (fixture `ssh_server`);
  - `tests/test_sync_integration.py`, `tests/test_sync_ui.py`, `tests/test_sync_monitor.py`;
  - `tests/test_config.py`, `tests/fixtures/README.md`;
  - `CLAUDE.md` (comando do CI, política de versões, `ssh_server`).
- Removido: `tests/fake_ssh.py`.
- Ordem sugerida: R7 cedo, porque troca a base dos testes de sync que as specs 15 e 17 alteram.
- O `conftest.py` já força `QT_QPA_PLATFORM=offscreen`, então o CI não precisa de Xvfb.

## Critérios de aceite e testes
- [ ] Um push abre o workflow, e lint, formatação e testes passam em 3.11 e 3.12.
- [ ] O job `perf` roda e o seu resultado aparece, sem bloquear.
- [ ] `QApplication.windowIcon()` não é nulo e `desktopFileName()` é `"lain"`, verificado em teste.
- [ ] `scripts/install_desktop.py --prefix <tmp>` instala o `.desktop` e os ícones nos caminhos XDG,
      verificado com diretório temporário.
- [ ] O link do PRD no README aponta para um arquivo existente (teste simples ou checagem no CI).
- [ ] `tests/test_properties.py` passa com o perfil `ci`.
- [ ] Um config com `plot.export.theme: current` carrega com aviso, e um config com outra chave
      desconhecida continua falhando.
- [ ] `grep -rn "def reload" src/qe_studio/ui/widgets/workspace.py` não encontra nada.
- [ ] `tests/fake_ssh.py` não existe, e `grep -rn fake_ssh tests` não encontra nada.
- [ ] Pull pelo `ssh_server` com chave e com senha (askpass): status DONE, arquivos e datas
      preservados, e o log do servidor registra `rsync --server` com o método de autenticação certo.
- [ ] Chave de host desconhecida ou trocada, senha errada, porta fechada, banner travado e queda no meio
      da transferência terminam todos em FAILED, com a mensagem correspondente e sem arquivos parciais.
- [ ] Um comando fora da lista de permitidos enviado ao servidor recebe 127 e não é executado.
- [ ] Nenhum teste lê ou escreve em `~/.ssh` (o `ssh` roda com `-F <tmp>/ssh_config`).
- [ ] O fixture encerra o servidor sem threads vivos no fim da sessão.
