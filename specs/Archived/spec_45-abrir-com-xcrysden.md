# Spec 45: "Abrir com XCrysDen" no menu de contexto dos inputs e saídas do pw.x

| | |
|---|---|
| **Prioridade** | 45 (pequena e independente: liga um programa externo que o usuário já tem; pode sair antes de `spec_end`) |
| **Status** | Implementada (13/10/2026). Desvios:<br>- `FileActions.xcrysden` tem padrão `None` (os construtores de três campos continuam válidos).<br>- Habilitado, o tooltip do item é o padrão do Qt (o texto do item), não vazio: só o motivo do item desabilitado é escrito.<br>- Pasta com um `xcrysden` sem bit de execução dá "<caminho do script> não é executável." (o caminho do script, não o da pasta).<br>- Os 7 testes de R3.8 viraram 10 funções (inputs e saídas parametrizados; o 'sem item' em arquivos de outros programas, em pasta, em seleção e sem sniff ficou em três testes). Nenhum comportamento diferente da spec. |
| **Depende de** | spec 5 (menu de contexto: `ItemActions`, `add_action`, `_launch` com `QProcess.startDetached`), spec 43 (`FileActions`, o item "Visualização 3D" por sniff em cache e `Structure3DController.for_window`, onde o item se liga sem crescer `main_window.py`) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho da spec 43 R4.1 (item por sniff em cache) e das specs 24 / 27 (item desabilitado com o motivo no tooltip); nenhum contrato novo, nenhum arquivo perto do limite. |

## Itens de origem (`Ideias.md`)

> Quero implementar uma segunda visualização 3D das estruturas a partir do scf.
>
> Quero que no menu do botão direito do mouse tenha seja adicionado a opção "Abrir com XCrysDen". Onde abre o arquivo com o xcrysden usando '--pwi', por exemplo 'xcrysden --pwi scf.in'
>
> - O caminho de instalação do xcrysden deve ser lido do arquivo 'config.yaml' na chave 'xcrysden_path'.
>
> - Se o 'xcrysden_path' estiver vazio, então a opção "Abrir com XCrysDen" deve ser desabilitada.
>
> - O "Abrir com XCrysDen" só deve aparecer se o arquivo for um arquivo '.in' ou '.out' do pw.x

Interpretação:

- A "segunda visualização 3D" é o XCrySDen, programa externo; a primeira é a janela própria da spec 43. O Lain não desenha nada novo: um item de
  menu chama o programa com o arquivo.
- **Decisão do usuário:** o item fica *desabilitado* (visível) com `xcrysden_path` vazio; só aparece para `.in` / `.out` do pw.x.
- O exemplo do pedido só mostra `--pwi` (input). Para `.out` o pedido lista o arquivo como elegível sem dar a opção: o XCrySDen tem `--pwo`
  para a saída do pw.x (verificado, "Situação atual", R4) e é a usada.

## Situação atual

- **R1 (configuração).** `core/config.py`: `PathsConfig` (`:83`) tem só `local_root` e `remote_root`, com o validador `_expand`
  (`expandvars` + `expanduser`). Toda seção herda `_Section` (`:79`, `extra="forbid"`) e `AppConfig` (`:226`) só tem seções: um
  `xcrysden_path` hoje, no topo ou em `paths:`, é recusado ao carregar (**reproduzido** com `parse_config`:
  `• xcrysden_path: chave desconhecida` e `• paths.xcrysden_path: chave desconhecida`). `JobsConfig.pseudo_dir` (`:218`) com
  `_blank_is_none` (`:222`) é o precedente de texto opcional em que vazio vale "não definido". `config.example.yaml` (115 linhas) e
  `src/qe_studio/resources/config.example.yaml` são idênticos e `tests/test_config.py` os mantém assim. "Recarregar config.yaml" troca
  `MainWindow.loaded` (`ui/main_window.py:436`, `_apply_loaded`) e `MainWindow.config` (`:114`) lê `self.loaded.config` a cada uso, então
  quem lê a configuração na hora de usar acompanha a recarga sem código novo.
- **R2/R3 (menu).** `ui/widgets/context_menu.py` (343 linhas): `FileActions` (`:53`) tem `plot_kind`, `is_output` e `structure`
  (`sniff.kind is FileKind.PW_IN`); `file_actions_of` (`:119`) lê só o sniff em cache e, num miss, pede a detecção e devolve
  `FileActions(None, False, False)`; `menu` (`:139`) põe "Plotar", "Resumo", "Visualização 3D" e "Gerar SCF convergido" no alto, com um
  separador quando há algum (`:170`), e usa o padrão *desabilitado com o motivo no tooltip* (`scf`, `push`, `setToolTipsVisible`).
  `multi_menu` (`:192`) não tem ações por item. Não há item para o XCrySDen: "Abrir com ▸" (`_fill_open_with`, `:235`) lista só programas
  registrados no `.desktop` para o MIME do arquivo e "Outro programa…" (`open_with_other`, `:266`) pede o comando a cada vez e põe o
  caminho do arquivo no fim.
- **R3 (lançamento).** `_launch` (`:271`) é `QProcess.startDetached(argv[0], argv[1:], str(path.parent))`, sem shell; falha vira `log.warning`
  e a mensagem de rodapé `Não foi possível abrir {arquivo} com {nome}.` (`:275`). `ui/widgets/context_menu.py` tem 4 chamadas de disco
  em `FS_ALLOWED` (`tests/test_architecture.py`), que não podem crescer.
- **Limite de `main_window.py`.** O arquivo tem **450 linhas**, o `PER_FILE_LIMIT` (`tests/test_architecture.py:19`): nenhuma linha pode
  entrar. `ItemActions` é montado em `:176` com três argumentos. `Structure3DController.for_window` (`ui/structure3d_controller.py:52-57`)
  já alcança `window.item_actions` e é chamado em `main_window.py:208`.
- **R4 (o XCrySDen).** Na instalação do usuário (`~/Projetos/xcrysden-1.6.2-bin-shared/`): `xcrysden` é um script POSIX `sh` executável
  (`-rwxr-xr-x`); `usage:120-128` lista `--pwi` / `--pw_inp file` ("Load structure from pw.x input file") e `--pwo` / `--pw_out file` (saída
  do pw.x); `Tcl/parseComLinArg.tcl:122-156` trata os dois e, com arquivo inexistente, mostra `ErrorDialog "… doesn't exists !!!"` e sai.
  O script inicia `xcrys … > /dev/null &` e fica em `wait $!`: vive enquanto a janela existir. O relatório
  `Documentation/Relatorios/Relatorio_visualizacao_3D_da_estrutura.md:616` dava as duas opções "de memória"; agora estão verificadas, **só na
  1.6.2** (outras versões: não verificado).
- **Testes que já descrevem esses menus** e vão mudar (o item aparece, desabilitado, em todo menu de input ou saída do pw.x aberto
  pelo clique): `tests/test_structure3d_ui.py:52-64` (`[ITEM, *MENU]` e o separador em `actions()[1]`); `tests/test_file_grid_menu.py:154-175`
  (`len(...actions()) == 7`, a coluna `top`); `tests/test_scf_from_relax_ui.py:35-37` (`menu_texts(menu)[:3]`, separador em `[3]`). Os
  testes que chamam `ItemActions.menu(...)` direto, sem `xcrysden=`, não mudam (`test_structure3d_ui.py:67-71`).

## Requisitos

### R1: A chave `paths.xcrysden_path`

1. `PathsConfig.xcrysden_path: str | None = None`. Validador, no molde de `JobsConfig._blank_is_none`: `strip()`; vazio, só espaços ou `null`
   → `None`; senão `os.path.expandvars` + `expanduser` (como `local_root`), devolvido como `str`. **Não** verifica se existe: o
   arquivo muda entre recargas, e é o menu que diz o motivo (R3.4).
2. As duas cópias do `config.example.yaml`, na seção `paths:` depois de `remote_root`:

   ```text
     # Where XCrySDen is installed: its folder (the one holding the `xcrysden` script) or the script
     # itself. Empty: "Abrir com XCrysDen" in the right-click menu stays disabled.
     # Reload with "Recarregar config.yaml".
     xcrysden_path: ""
   ```

3. Fora de `paths:` a chave continua "chave desconhecida" (decisão 1). Sem outra mudança em `core/config.py`: nenhum aviso de carregamento
   (o tooltip do menu já diz o que falta).
4. **Testes:** `tests/test_config.py`: padrão `None`; `""`, `"   "` e `null` → `None`; `" ~/xcrysden "` → `str(Path.home() / "xcrysden")`;
   `"$SIMS/x"` expandido; o exemplo continua carregando e as duas cópias idênticas (teste existente); `with_local_root` do exemplo muda só
   a linha de `local_root`.

### R2: `core/xcrysden.py` (novo, Qt-free)

Entra em `QT_FREE` (`tests/test_architecture.py:67`).

1. `option_for(kind: FileKind) -> str | None`: `PW_IN` → `"--pwi"`, `PW_OUT` → `"--pwo"`, qualquer outro `None`. Decide-se pelo **conteúdo**
   (o sniff), nunca pelo sufixo (princípio de detecção do `CLAUDE.md`).
2. `locate(configured: str | None) -> Located`, `Located(executable: Path | None, problem: str)`; nunca levanta (um `OSError` é "não
   encontrado"):

   | `configured` | resultado |
   |---|---|
   | `None` | sem executável; `problem` = "Defina paths.xcrysden_path no config.yaml para abrir com o XCrysDen." |
   | uma pasta com `xcrysden` executável | `<pasta>/xcrysden`, `problem` = "" |
   | um arquivo executável | ele mesmo, `problem` = "" |
   | não existe | "XCrysDen não encontrado: <caminho>." |
   | pasta sem `xcrysden` | "Não há o executável xcrysden em <pasta>." |
   | arquivo sem permissão de execução | "<caminho> não é executável." |

3. `command(executable: Path, option: str, path: Path) -> list[str]` = `[str(executable), option, os.path.abspath(path)]`: sem shell
   (nome com espaço é um argumento), e um caminho relativo (`paths.local_root` pode ser relativo) vira absoluto, porque `_launch` roda
   com o diretório da pasta do arquivo e o argumento seria resolvido ali de novo.
4. **Testes** (`tests/test_xcrysden.py`, novo, sem Qt; scripts de mentira em `tmp_path` com `chmod`): `option_for` dá valor só para `PW_IN` e
   `PW_OUT` sobre **todos** os `FileKind`; cada linha da tabela de `locate` (a pasta, o arquivo, os três problemas, `None`);
   `command` com espaço no nome do arquivo e com caminho relativo.

### R3: O item "Abrir com XCrysDen"

1. `FileActions` ganha `xcrysden: str | None` (a opção de `option_for(sniff.kind)`); `file_actions_of` a preenche e, num miss do cache,
   devolve `None` e pede a detecção (o item aparece no menu seguinte, como "Visualização 3D").
2. `ItemActions.xcrysden_path: Callable[[], str | None]`, padrão `lambda: None` (como `push_state`: quem sabe de onde vem o liga);
   `menu(..., xcrysden: str | None = None)` recebe a opção (como `structure=`); `show()` passa `actions.xcrysden`.
3. **Posição:** item de primeiro nível (não dentro de "Abrir com ▸"), logo depois de "Visualização 3D" e antes de "Gerar SCF
   convergido": `Plotar`, `Resumo`, `Visualização 3D`, `Abrir com XCrysDen`, `Gerar SCF convergido`, separador, o resto. A condição do
   separador (`:170`) inclui o item. Numa saída `.out` do pw.x (sem "Visualização 3D") ele vem depois de "Resumo".
4. **Estado:** `locate(self.xcrysden_path())`. Executável achado → habilitado; senão **desabilitado**, com o `problem` como tooltip
   (`menu.setToolTipsVisible(True)`, como "Gerar SCF convergido"). Texto exato: `Abrir com XCrysDen`.
5. **Disparo:** `_launch(command(executable, option, path), path, "XCrysDen")`: `QProcess.startDetached`, diretório de trabalho = a pasta
   do arquivo, sem shell. Se o processo não inicia: a mensagem de rodapé existente, `Não foi possível abrir <arquivo> com XCrysDen.`
   Sem janela, sem spinner e sem toast quando inicia.
6. O item não existe no `multi_menu` nem em pastas (nenhuma é `PW_IN` / `PW_OUT`).
7. **Ligação sem crescer `main_window.py`:** `Structure3DController.for_window` (que já tem `window.item_actions`) faz
   `window.item_actions.xcrysden_path = lambda: window.config.paths.xcrysden_path`, lido a cada menu: "Recarregar config.yaml" vale sem
   reiniciar. O docstring do controlador passa a dizer que o item de menu do XCrySDen mora ali, ao lado do "Visualização 3D".
   `main_window.py` fica com 450 linhas.
8. **Testes** (`tests/test_xcrysden_menu.py`, novo, `main_window` + `demo_project`, `QMenu.exec` trocado como em `test_structure3d_ui.py`, a
   fixture `launched` de `conftest.py:199`, um `xcrysden` de mentira executável em `tmp_path`, o caminho posto em
   `window.config.paths.xcrysden_path`):
   - `test_the_item_is_in_pw_inputs_and_outputs_only`: presente em `03_bands/bands.in`, `01_relax/si.rel.in` (inputs pw.x),
     `02_scf/scf.out`, `03_bands/bands.out`, `04_pdos/nscf.out`, `01_relax/si.rel.out` (saídas pw.x); ausente em `03_bands/bands_pp.out`
     (bands.x), `04_pdos/projwfc.out`, `03_bands/bands.dat.gnu`, numa pasta, numa seleção de dois arquivos e num arquivo ainda sem
     sniff (pede a detecção).
   - `test_an_empty_path_disables_the_item_with_the_reason`: sem configuração o item existe, `isEnabled()` é falso e o tooltip é o
     da tabela de R2.
   - `test_a_folder_or_the_script_launches_xcrysden`: com a pasta e com o próprio script, `triggered` →
     `launched == [(<script>, ["--pwi", str(arquivo)], str(pasta do arquivo))]`; numa saída, `--pwo`.
   - `test_a_wrong_path_is_disabled_with_its_reason`: inexistente, pasta sem o script, script sem bit de execução; nada é lançado.
   - `test_a_config_reload_applies_without_restart`: `window.load_config_file(<config.yaml em tmp_path>)` com e sem a chave; o item
     alterna entre habilitado e desabilitado no menu seguinte.
   - `test_order_and_separator`: `menu(path, summary=True, structure=True, scf="", xcrysden="--pwi")` →
     `["Resumo", "Visualização 3D", "Abrir com XCrysDen", "Gerar SCF convergido"]`, separador logo depois.
   - `test_a_failed_start_is_reported`: `QProcess.startDetached` devolvendo `(False, 0)` → a mensagem do rodapé do R3.5.
   - **Testes existentes que mudam** (R3.3: o item aparece, desabilitado, com a configuração padrão, nos menus abertos pelo clique):
     `test_structure3d_ui.py` (`test_the_item_is_only_in_pw_inputs`: `[ITEM, *MENU]` vira `[ITEM, XCRYSDEN, *MENU]` e o separador
     sai do índice 1 para o 2; `test_the_item_comes_after_resumo…` chama `menu()` direto e **não** muda);
     `test_file_grid_menu.py` (`["Plotar", "Resumo", *MENU]` e `len(actions) == 7` ganham o item, o separador vai ao índice 3; a coluna
     `top` das saídas e inputs pw.x idem); `test_scf_from_relax_ui.py` (`[:3]` → `[:4]`, o separador em `[4]`). Menus de pasta, de
     seleção múltipla e de arquivos que não são do pw.x **não** mudam (`test_multi_selection.py`, `test_bands_dos_ui.py`,
     `test_favorites_ui.py` passam sem edição).

## Fora de escopo

- **Falha do próprio XCrySDen depois de iniciar** (sem `DISPLAY`, erro do Tcl, estrutura que não lê): o Lain não acompanha o processo; o
  stdout do script vai para `/dev/null`. Só a falha de *iniciar* é dita (R3.5).
- **Outros arquivos** (`.xsf`, `.cube`, `.xyz`, saídas do bands.x / projwfc.x) e as outras opções do XCrySDen (`--xsf`, `--cube`…): o
  pedido é o pw.x; cada formato novo é um `FileKind` a mais em `option_for`.
- **O que o `--pwo` mostra** (última estrutura, animação de um relax): é do XCrySDen.
- **Seleção múltipla:** o XCrySDen abre um arquivo; o item não entra no `multi_menu` (as ações por item ficam ocultas, spec 16 R5).
- **Aviso na carga da configuração** para um caminho que não existe: o tooltip do item já diz (R2).
- **Windows:** o executável é `xcrysden` (o do pacote Linux, verificado); o do Windows não foi verificado.
- **Argumentos extras ou nome do executável configurável**: a chave é só o caminho.
- **Ação em `ui/actions.py:ACTIONS` / paleta Ctrl+K:** como "Visualização 3D", é um item de contexto de um arquivo, não uma ação da janela.
- **A janela da spec 43** não muda.

## Decisões assumidas (confirmar na revisão)

1. **A chave mora em `paths:`** (`paths.xcrysden_path`), não no topo do arquivo: todas as chaves do `config.yaml` estão numa seção e `paths`
   é onde estão os caminhos. O pedido diz só "a chave `xcrysden_path`". Uma chave no topo continua recusada com "chave desconhecida"
   (reproduzido). A alternativa, no topo, custa um campo em `AppConfig` e a linha do exemplo sem indentação.
2. **"Caminho de instalação" = a pasta *ou* o executável.** O pedido não diz qual; a instalação do usuário tem o `xcrysden` na raiz da
   pasta (`xcrysden-1.6.2-bin-shared/xcrysden`), então as duas formas valem (R2.2).
3. **`.out` abre com `--pwo`**: o exemplo do pedido só traz `--pwi`; a opção existe no XCrySDen 1.6.2 (verificada em `usage` e no Tcl).
4. **"Do pw.x" é pelo conteúdo** (`FileKind.PW_IN` / `PW_OUT` do sniff em cache), não pelo sufixo `.in` / `.out`: um input do pw.x chamado
   `.inp` entra, um `bands.in` do bands.x não. Um arquivo ainda sem sniff não mostra o item até a detecção acabar (igual ao
   "Visualização 3D", spec 43 R4.1). Se o usuário preferir o sufixo, a diferença é uma linha em `option_for`, mas o item apareceria em
   inputs do bands.x e do projwfc.x, que o `--pwi` não lê.
5. **Caminho preenchido mas errado também desabilita** o item, com o motivo no tooltip: o pedido só fala do vazio.
6. **O item é de primeiro nível**, junto da "Visualização 3D" (as duas são visualizações da estrutura), não dentro de "Abrir com ▸".
7. **Texto `Abrir com XCrysDen`**, a grafia do pedido (a do programa é "XCrySDen", usada nos comentários e no `CLAUDE.md`).
8. **A ligação fica em `Structure3DController.for_window`** porque `main_window.py` está em 450/450; é a mesma família de menu e o
   mesmo ponto onde a spec 43 já liga `structure_requested`. A alternativa (um controlador próprio) custa duas linhas em
   `main_window.py` que não existem.

## Notas de implementação

- **Novos:** `core/xcrysden.py`, `tests/test_xcrysden.py`, `tests/test_xcrysden_menu.py`.
- **Alterados:** `core/config.py` (394 linhas; um campo e um validador), `config.example.yaml` e
  `src/qe_studio/resources/config.example.yaml` (idênticos), `ui/widgets/context_menu.py` (343; `FileActions`, `file_actions_of`,
  `menu`, `show`, o docstring do módulo, uma função de disparo), `ui/structure3d_controller.py` (104; uma linha e o docstring),
  `tests/test_architecture.py` (`QT_FREE` + `qe_studio.core.xcrysden`; `FS_ALLOWED` **não** muda), `tests/test_config.py` e os três
  arquivos de teste de R3.8.
- **Limites:** `ui/main_window.py` em 450/450 não recebe nenhuma linha (R3.7); nenhum outro arquivo passa de ~410.
- **Ordem:** R1 e R2 independentes; R3 depende dos dois.
- **Documentação ao implementar:** `CLAUDE.md` (seção "Context menu (spec 5)": o item, `xcrysden_path` e a ligação em
  `Structure3DController.for_window`; seção "Visualização 3D (specs 43, 44)": uma linha dizendo que o XCrySDen é a segunda visualização,
  externa); `README.md` (o parágrafo do botão direito, `:105-112`, e a descrição da configuração, se houver); `config.example.yaml`.

## Critérios de aceite e testes

- [ ] Sem a chave (padrão), nada muda no que o Lain faz: a carga do `config.yaml` é a mesma e os menus de pasta, de seleção múltipla e de
  arquivos que não são do pw.x são iguais (`test_multi_selection.py`, `test_bands_dos_ui.py`, `test_favorites_ui.py` sem edição).
- [ ] `paths.xcrysden_path` vazio, espaços ou `null` = `None`; `~` e `$VAR` expandidos (`test_config.py`).
- [ ] `option_for` dá `--pwi` / `--pwo` só para `PW_IN` / `PW_OUT`; `locate` cobre pasta, arquivo e os três problemas; `command` não passa
  por shell e absolutiza o caminho (`test_xcrysden.py`, novo).
- [ ] O item aparece só em inputs e saídas do pw.x, desabilitado e com o motivo quando a chave está vazia ou errada, e habilitado quando
  aponta para a pasta ou para o script (`test_xcrysden_menu.py`, novo).
- [ ] O clique lança `[<xcrysden>, "--pwi" | "--pwo", <arquivo absoluto>]` na pasta do arquivo, sem shell; falha ao iniciar vira a
  mensagem do rodapé (`test_xcrysden_menu.py`).
- [ ] "Recarregar config.yaml" muda o estado do item sem reiniciar (`test_xcrysden_menu.py`).
- [ ] `main_window.py` continua com 450 linhas; `FS_ALLOWED` igual; `core.xcrysden` carrega sem Qt (`test_architecture.py`).
- [ ] Os menus de `test_structure3d_ui.py`, `test_file_grid_menu.py` e `test_scf_from_relax_ui.py` passam com o item novo.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
- [ ] **Passo manual de aceite** (precisa de `DISPLAY` e do XCrySDen, fora da CI): com
  `paths.xcrysden_path: ~/Projetos/xcrysden-1.6.2-bin-shared`, clicar com o botão direito num `scf.in` ▸ "Abrir com XCrysDen" abre a
  janela do XCrySDen com a estrutura; o mesmo numa saída `.out` do pw.x.
