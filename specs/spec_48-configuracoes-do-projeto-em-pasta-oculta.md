# Spec 48: Configurações do projeto em `<local_root>/.lain/`: copiar a pasta raiz leva mapeamentos, grids, átomos, favoritos e recentes

| | |
|---|---|
| **Prioridade** | 48 (depois da 47). Independente das specs 33–47; não toca `ui/main_window.py` (450/450). |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 14 (`FolderMemory`, chaves relativas à raiz), spec 16 (`NavigationStore`, favoritos e recentes), spec 21 (`CompoundStore`), spec 23 (`GridStore`), spec 27-3 (`atomic_write_text`, `set_aside_corrupt`, trava de instância), spec 31 (Projetos: a raiz é a unidade, `list_projects`, `validate_project_name`), spec 17 e 27 (comandos do rsync) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1 e R5: P; R2 e R3: M; R4 e R6: P) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda o lugar de quatro arquivos de dados do usuário usados em todo o app, com migração de dados reais, e a ligação precisa caber em `main_window.py` (450/450) e `plot_workflow.py` (481/500). |

## Itens de origem (pedido de 14/10/2026, depois da conversa sobre o assunto)

> Que tal centralizar esses arquivos de configuração em uma pasta 'configuration' dentro do 'local_root' assim, se copiar a pasta dos projetos, vai copiar as configurações também?

> Gostei da ideia de usar uma pasta oculta (.lain/) para salvar as configurações e excluir ela do botão dropdown de projetos. Quero que inclua os 'Rencentes'/'Favoritos' na pasta de configurações. Crie uma nova spec com essas considerações. E não inclua os arquivos '.plot' nessa mudança

"Esses arquivos" são os quatro do diretório de dados do usuário: `folders.json` (mapeamentos manuais e rótulos de k-points),
`grids.json`, `compounds.json` (átomos da PDOS por composto) e `navigation.json` (favoritos e recentes). Decisões do usuário no pedido:

- a pasta é oculta e se chama `.lain/` (a primeira ideia, `configuration`, foi trocada);
- fica fora do dropdown de projetos;
- **entram** "Recentes" e "Favoritos";
- os `.plot` **não** entram: continuam em `<simulação>/<kind>.plot`, sem mudança.

O que ficou de fora do pedido e foi decidido na conversa (a spec o assume, ver "Decisões assumidas"): `config.yaml` (credenciais do cluster), o
QSettings (tema, layout, escala, último projeto e última pasta) e `lain.lock` continuam no diretório do usuário.

## Situação atual

- **R1 (onde os dados moram).** `core/appdirs.py:15-20` `data_dir()` = `$XDG_DATA_HOME/qe-studio` (`~/.local/share/qe-studio`), e é o
  padrão de quatro stores: `folder_memory.py:31` (`folders.json`), `nav_store.py:35` (`navigation.json`), `grid_store.py:36`
  (`grids.json`) e `compounds.py:130` (`compounds.json`). `lock_path()` (`appdirs.py:34-36`) também. Na máquina do usuário o diretório tem
  `compounds.json`, `folders.json`, `grids.json`, `lain.lock` e `navigation.json` (visto com `ls`). Nenhum arquivo acompanha a pasta dos
  projetos: copiá-la para outra máquina deixa mapeamentos, grids, seleção de átomos e favoritos para trás.
- **R2 (um arquivo para todas as raízes).** Os formatos já são relativos à raiz, de propósito (spec 14 R7, spec 16, spec 23), mas o
  arquivo é um só por usuário:
  - `FolderMemory._key` (`folder_memory.py:39-43`) devolve o caminho relativo sem identificar a raiz: duas raízes com a pasta `ilita/Bands`
    compartilham a mesma entrada (lido no código; não reproduzido com duas raízes reais). `set_root` (`:152-158`) só troca a base das chaves.
  - `NavigationStore.set_root` (`nav_store.py:46-50`) guarda `self._key = str(self._root.resolve())` e `_entry` (`:103-108`) usa essa chave
    no mapa `projects`: o **caminho absoluto resolvido** da raiz. Uma cópia da raiz em outro lugar tem outra chave e perderia os favoritos
    mesmo que o arquivo viajasse.
  - `GridStore` (`grid_store.py:47-51`) é `set_root` + um mapa de nomes: duas raízes dividem os nomes das grades.
  - `CompoundStore` (`compounds.py:121-134`) não tem raiz nem `set_root`.
- **R3 (quem constrói e quem chama `set_root`).** `main_window.py:88-91` (`FolderMemory()`, `NavigationStore()`, `CompoundStore()`,
  `memory.set_root`) e `:439-440` (`memory.set_root` / `navigation.set_root` ao recarregar a configuração); `navigation_controller.py:50` e
  `:93` (`store.set_root`); `grids_controller.py:71` e `:126` (`store.set_root(self._root())` antes de cada uso);
  `plot_workflow.py:106` (`Stores(compounds or CompoundStore(), grids or GridStore())`). Nenhum chama `set_root` do `CompoundStore`.
  `tests/conftest.py:144-154` passa os quatro caminhos (`tmp_path / "memory.json"`…), então a suíte não toca o diretório de dados.
- **R4 (gravação).** Todos gravam com `atomic_write_text` (`appdirs.py:63-80`: `mkdir(parents=True)`, temporário único, `fsync`,
  `os.replace`). Um erro de escrita sobe como exceção (para o `excepthook`, que mostra um toast); um arquivo ilegível é renomeado para
  `<nome>.corrompido-<data>` (`set_aside_corrupt`) e, se isso falha, o store passa a `_read_only` e não grava. Nenhum caminho de leitura
  ou escrita conhece a ideia de "pasta não gravável": numa raiz em disco somente leitura o app falharia a cada gravação.
- **R5 (a pasta já não aparece, mas por acidente).** Um nome com ponto inicial é pulado em `projects.py:62` (`list_projects`),
  `folder_index.py:41` (índice da paleta), `fs_model.py:184` (árvore e grade), `paths.py:26` (`count_entries`) e
  `calculations/listing.py:14` (`IGNORED_SUBDIRS` tem `\..*`); `validate_project_name` recusa nome com ponto (`projects.py:97-98`) e
  `create_project` o valida de novo. Nada disso cita `.lain`: é o efeito da regra "arquivos com ponto não aparecem", sem teste que prenda
  o nome. O sync: `dry_run_command` (`core/sync/rsync.py:153`) exclui `config.sync.exclude` e `push_dry_run_command` (`:208`) mais
  `push_exclude` (`config.py:59`: `plots/`, `*.plot`). Essas listas vêm do `config.yaml`, que o usuário pode trocar inteiras. O pull
  nunca apaga o que só existe localmente (spec 17: "arquivos só locais não bloqueiam o pull"), e o push é sempre de uma pasta de
  cálculo (`prepare_push` recusa a raiz e o projeto); se alguém copiar a raiz inteira para o cluster por fora do Lain, um pull seguinte
  listaria `.lain/*.json` como atualização.
- **R6 (o usuário não vê onde está).** `help_controller.py:127` ("Sobre" mostra `Dados: <data_dir()>`) e `open_data_dir` (`:107-117`) só
  conhecem o diretório do usuário; `tests/test_help.py:137` e `:188` fixam isso.
- **Testes que leem os arquivos pelo caminho antigo:** `tests/test_grid_workflow.py:101` (`data_dir() / "grids.json"` depois de rodar a
  janela), `tests/test_compounds.py:95` e `tests/test_grid_spec.py:88` (o caminho padrão sem raiz).
- **Tamanhos (`wc -l`):** `main_window.py` 450 (limite 450), `plot_workflow.py` 481, `core/calculations/base.py` 457, `folder_memory.py`
  242, `grid_store.py` 219, `compounds.py` 237, `nav_store.py` 202, `rsync.py` 365, `appdirs.py` 94, `help_controller.py` 134.

## Requisitos

### R1: O módulo novo `core/project_data.py`: onde ficam as configurações de uma raiz

1. Novo `src/qe_studio/core/project_data.py` (arquivo novo, Qt-free, entra em `QT_FREE`), a **única** fonte de `".lain"` no código:
   `PROJECT_DATA_DIR = ".lain"` e os nomes dos quatro arquivos (`folders.json`, `grids.json`, `compounds.json`, `navigation.json`, os de
   hoje: formato e nome não mudam).
2. `locate(root: Path) -> Location`, `Location(folder: Path, fallback: bool, notice: str | None)`, sem exceção e sem criar nada:
   1. `root` não é uma pasta → `fallback`, sem `notice` (o estado vazio da primeira execução já avisa);
   2. `<root>/.lain` existe: é pasta com `os.access(W_OK | X_OK)` → `folder = <root>/.lain`; é arquivo, ou pasta sem permissão →
      `fallback` com `notice`;
   3. `<root>/.lain` não existe: `os.access(root, W_OK | X_OK)` → `folder = <root>/.lain` **sem criá-la** (nasce na primeira gravação:
      `atomic_write_text` já faz `mkdir(parents=True)`); senão `fallback` com `notice`.
3. O `fallback` é `data_dir() / "roots" / <16 primeiros hex de sha256(str(root.resolve()))>`: uma pasta por raiz no diretório do usuário,
   com os mesmos quatro arquivos e os mesmos formatos (R2). O texto do `notice` (R4) cita a pasta da raiz e a do fallback.
4. `locate` não guarda estado: cada chamada custa 2–3 `stat`; os stores só trocam de arquivo quando o `folder` mudou (R2.3).
5. **Testes** (`tests/test_project_data.py`, novo; tmp dirs; os de permissão com `os.chmod`, pulados com `os.geteuid() == 0`):
   - raiz gravável sem `.lain` → `<root>/.lain`, e a pasta **não** existe depois de `locate`;
   - `.lain` existente e gravável → ela; `.lain` arquivo comum → `fallback` com `notice`; raiz `0o555` → `fallback` com `notice`;
   - raiz que não é pasta → `fallback`, `notice` vazio; duas raízes → duas pastas de `fallback` diferentes, estáveis entre chamadas;
   - `".lain"` aparece em um só módulo de `src/` (teste por AST/`grep` em `test_architecture.py`: o módulo novo `project_data.py` e o comentário de quem o
     cita ficam de fora, só as constantes).

### R2: Os quatro stores seguem a raiz

1. `FolderMemory`, `NavigationStore`, `GridStore` e `CompoundStore` (que ganha `set_root(root)`) deixam de fixar o arquivo em
   `data_dir()` quando **não** recebem `path`: em `set_root(root)` chamam `locate(root)` e usam `<folder>/<nome>.json`. Quem recebe
   `path` explícito (a suíte, `scripts/`) fica **fixado**: `set_root` troca só a base das chaves, como hoje. Sem `set_root`, o caminho
   é o de hoje (`data_dir() / "<nome>.json"`): `test_compounds.py:95` e `test_grid_spec.py:88` passam sem mudança.
2. Chaves: `FolderMemory`, `GridStore` e `CompoundStore` mantêm o formato (versão 2, 1 e 1). `NavigationStore`, quando segue a raiz, usa a
   chave `"."` no mapa `projects` (o formato é o mesmo, a versão 1): o arquivo da raiz vale em qualquer lugar onde a pasta for copiada.
   Fixado (ou sem `set_root`), mantém `str(root.resolve())` como hoje.
3. Trocar de arquivo (a raiz mudou na recarga da configuração, ou `locate` deu outro `folder`): 1) grava o que estiver pendente no arquivo
   antigo (`NavigationStore.flush`); 2) troca `path`; 3) esquece o que estava em memória (`_folders`, `_grids`, `_compounds`,
   `_projects`) e `_read_only` / `_warning`; a próxima leitura vem do arquivo novo (e migra, R3). O mesmo `folder` não faz nada.
   Resultado: **cada raiz tem o seu arquivo e nada de uma raiz entra no arquivo de outra**.
4. Ligação **sem linhas novas em `main_window.py`**: `main_window.py:91` e `:439` (`memory.set_root`) e `navigation_controller.py:50` /
   `:93` já chamam `set_root`; `GridsController` já o chama antes de cada uso. Para o `CompoundStore`: `core/calculations/base.py:Stores`
   ganha `set_root(root)` (repassa a `compounds` e `grids`) e o `PlotWorkflow` a chama com `self._config().paths.local_root` no início
   de `_load` (`plot_workflow.py:277`) e antes de `session.persist` (`:403`); `GridLoader` (`grid_loader.py:143`, `:165`) já tem
   `self._root()`. Custo medido do `locate` repetido: R1.4.
5. Um store construído por `FolderMemory()` etc. no `MainWindow` (sem `path`) segue a raiz; os de `tests/conftest.py:144-154` (com `path`)
   não: **nenhum teste existente cria `.lain/`** salvo os que pedem (R6). `window_factory` ganha o argumento `follow_root=True`, que não
   passa os caminhos e deixa o `MainWindow` construir os seus.
6. **Testes** (`tests/test_project_data_stores.py`, novo):
   - cada store, sem `path`, escreve em `<root>/.lain/<nome>.json` depois de `set_root(root)`, e lê de volta em outra instância;
   - **isolamento**: duas raízes na mesma sessão (`set_root(a)`, grava, `set_root(b)`, grava, `set_root(a)`): cada arquivo só tem o
     que é da sua raiz; o `FolderMemory` com a pasta `x` mapeada na raiz A não devolve nada para `x` na raiz B;
   - **cópia**: `shutil.copytree(root_a, root_b)` (a pasta `.lain` vai junto) e um store novo em `root_b` devolve os favoritos, os
     mapeamentos (arquivo mapeado relativo à pasta), as grades (`GridStore.get` com os caminhos em `root_b`) e a seleção de átomos;
   - `NavigationStore` da raiz copiada: favoritos e recentes aparecem (chave `"."`);
   - store com `path` explícito: nada é criado em `<root>/.lain`;
   - trocar de raiz com recentes pendentes grava no arquivo da raiz antiga (nada se perde, nada vaza para a nova).

### R3: Migração única do diretório de dados antigo

1. Quando o arquivo da raiz **não existe** e o arquivo de `data_dir() / "<nome>.json"` existe, o store importa o que é desta raiz
   (leitura lazy, na mesma thread em que o store lê hoje; a escrita do arquivo novo é a primeira gravação do store). O arquivo antigo
   **nunca** é alterado nem apagado: outra raiz ainda pode precisar dele. Importar é idempotente (depois da primeira vez, o arquivo
   novo existe).
2. O que é "desta raiz" (funções puras em `core/`, com `exists` injetado, no estilo do `NavigationStore`: `prune_missing_recents`):
   - `folders.json`: a entrada cuja pasta existe sob a raiz (`(root / key).is_dir()`, `"."` = a raiz) e as `abs:` que caem dentro dela
     (o `_rehome` de hoje); as demais ficam de fora;
   - `grids.json`: a grade sem células, ou com pelo menos uma célula cujo caminho existe sob a raiz;
   - `compounds.json`: **tudo** (a chave é a sequência de espécies: não há como ligar à raiz);
   - `navigation.json`: a entrada de `str(root.resolve())`, gravada com a chave `"."`; favoritos e recentes relativos como estão.
3. Importar não pergunta e não abre diálogo; registra `log.info("<arquivo>: N itens importados de <antigo>")`. Se o arquivo antigo
   estiver ilegível, o store segue vazio **sem** renomear o antigo (ele não é seu: só o arquivo da raiz é "set aside").
4. Apagar o arquivo da raiz de propósito faz o próximo início importar de novo (o antigo continua lá): aceito, dito em "Decisões".
5. **Testes** (`tests/test_project_data_migration.py`, novo; o `data_dir()` antigo montado em `tmp_path` com `XDG_DATA_HOME`):
   - um `folders.json` antigo com entradas de duas raízes: a raiz A importa as suas, a B (aberta depois) as suas, o arquivo antigo fica
     byte a byte igual;
   - `grids.json` com uma grade da raiz, uma de outra e uma sem células: importa a primeira e a terceira;
   - `compounds.json` importado inteiro; `navigation.json` com duas raízes importa só a atual, com chave `"."`;
   - o arquivo da raiz já existente nunca é sobrescrito pelo antigo; antigo corrompido: store vazio, o antigo intocado;
   - segunda abertura: nenhuma leitura do antigo (o arquivo da raiz existe).

### R4: Raiz somente leitura: o fallback e o aviso

1. `Location.fallback` (R1) aplica o mesmo R2 e o mesmo R3 sobre `data_dir()/roots/<hash>/`; a migração do antigo vale para ele também.
2. O `notice` sai pelo canal que a janela já lê no início: `FolderMemory.load_warning()` devolve o aviso de arquivo corrompido, ou, se
   não houver, o `notice` do `locate` (o texto, em português: "A pasta do projeto não é gravável: as configurações ficam em <pasta
   do fallback>." / ".lain não é uma pasta: as configurações ficam em <pasta do fallback>."), e vai para o log. Mostrado uma vez por
   abertura da raiz.
3. A decisão é tomada ao definir a raiz (início e recarga da configuração). Um erro de escrita no meio da sessão continua o caminho de
   hoje (exceção → `excepthook` → toast): não há troca de local ao vivo (ver "Fora de escopo").
4. **Testes** (`tests/test_project_data_stores.py`): raiz `0o555` → os quatro stores gravam em `data_dir()/roots/<hash>/`, nada é
   criado na raiz, `load_warning()` traz o aviso; a mesma raiz com a permissão restaurada e `set_root` de novo volta para `.lain/`
   (o que estava no fallback **não** é copiado: ver decisão 7).

### R5: `.lain` fora das listas, do sync e dos nomes de projeto, e provado por teste

1. Sem código novo de filtragem: a regra do ponto inicial já exclui `.lain` (Situação atual, R5). A spec **a transforma em contrato**
   com os testes abaixo, e a documentação passa a citar o nome.
2. `core/sync/rsync.py`: `dry_run_command` (`:153`) e `push_dry_run_command` (`:208`) acrescentam `--exclude=.lain/` **sempre**,
   antes dos padrões do `config.yaml` (constante `PROJECT_DATA_EXCLUDE = PROJECT_DATA_DIR + "/"`): a proteção não depende da lista
   que o usuário editou. O pull e o push só transferem o que o dry run listou (`--files-from`), então os dois ficam cobertos.
   `DEFAULT_EXCLUDES` / `DEFAULT_PUSH_EXCLUDES` e o `config.example.yaml` **não mudam** (nenhuma das duas cópias).
3. O nome: `create_project(root, ".lain")` e `validate_project_name(".lain", …)` já devolvem "O nome não pode começar com ponto"; o
   teste fixa isso (e que nenhuma `ProjectError` deixa a pasta criada).
4. **Testes** (`tests/test_project_data_hidden.py`, novo; a raiz da fixture `raiz` com um `.lain/` de verdade, com os quatro arquivos):
   - `list_projects` não devolve `.lain`; `list_folders` não a lista; `count_entries(raiz)` não a conta;
   - `FolderListing.scan(raiz)` não a lê (`IGNORED_SUBDIRS`); `detect_folder(raiz)` não muda;
   - janela sobre `raiz` (`window_factory(follow_root=True)`): o dropdown "Projeto", a árvore (`tree_names`), a grade (`names`) e a paleta
     (`>`/`/`) não têm `.lain`; "Criar projeto…" com `.lain` mostra a mensagem e não cria nada;
   - `test_sync_rsync.py`: `--exclude=.lain/` está nos dois comandos, também com `sync.exclude: []` e `push_exclude: []`;
   - `test_sync_integration.py`: um remoto local que tem um `.lain/folders.json` criado pelo teste (cópia da raiz feita por fora) → o pull não o lista nem o
     baixa; o arquivo local de mesmo nome fica intacto.

### R6: O usuário vê onde estão as configurações

1. "Sobre" (`help_controller.py:127`): a linha `Dados` continua (lock, log e a pasta de `fallback` moram lá) e ganha uma linha
   **"Configurações do projeto"** com `<root>/.lain` (ou a pasta de `fallback`, ou "nenhuma" sem raiz). O valor vem de `locate`,
   chamado ao abrir o diálogo (3 `stat`, ação do usuário).
2. "Abrir pasta de dados" (`open_data_dir`, `:107-117`) não muda de comportamento: abre o diretório do usuário. **Sem ação nova** na paleta
   nem no menu (a pasta é oculta: o usuário a alcança pelo gerenciador, com "mostrar ocultos", ou pela linha do "Sobre").
3. **Testes** (`tests/test_help.py`): a linha nova com a raiz gravável e com a raiz somente leitura (aponta o fallback);
   `rows["Dados"] == str(data_dir())` e a abertura da pasta de dados continuam como estão.

## Fora de escopo

- **Os `.plot`** (`bands.plot`, `pdos.plot`, `relax.plot`, `view3d.plot` da spec 47, `grid` não tem): ficam em `<simulação>/<kind>.plot`.
  Decisão do usuário.
- **`config.yaml`, QSettings (`window/*`, `layout/*`, `explorer/*`, `ui/theme`, `calc_create/mode`…) e `lain.lock`**: seguem no
  diretório do usuário: credenciais e preferências de máquina não viajam com a pasta dos projetos.
- **Fusão de gravações** (duas instâncias, ou duas pessoas, na mesma raiz compartilhada): continua "o último a gravar vence", sem
  `merge`; a trava de instância (`lain.lock`) segue global do usuário e **não protege** outra máquina nem outro usuário na mesma pasta.
  Decisão: risco aceito e documentado (decisão 6). Um merge por operação nos quatro stores é outra spec.
- **Troca de local ao vivo** quando a escrita falha no meio da sessão, e **cópia** do que estava no fallback para `.lain/` quando a
  permissão volta: a escolha é feita ao definir a raiz (R4.3); o que ficou no fallback continua lá (decisão 7).
- **Importar de uma cópia** ("trazer as configurações de outra pasta") e **exportar** só as configurações: o gesto é copiar a pasta.
- **Uma `.lain/` por projeto** (`<raiz>/<projeto>/.lain`): a spec 31 decidiu que os dados ficam chaveados pela raiz; copiar um
  projeto solto não leva as configurações. Decisão da conversa: a raiz inteira é a unidade (decisão 2).
- **Recentes por usuário** numa raiz compartilhada: entram na pasta como o pedido diz (decisão 5).
- **`.lain` no Windows** (o atributo "oculto" do sistema): o nome com ponto basta para o Lain; marcar o atributo não é feito.

## Decisões assumidas (confirmar na revisão)

1. **Nome e lugar:** `<paths.local_root>/.lain/` (o nome do produto, pasta oculta), uma só por raiz, nunca dentro de um projeto nem de uma
   pasta de simulação. O pedido diz "dentro do `local_root`" e "`.lain/`": é isso.
2. **A raiz inteira é a unidade que se copia.** Copiar só um projeto não leva as configurações (o `.lain` não está dentro dele). A
   alternativa, uma pasta por projeto, foi descartada na conversa porque os grids e os compostos cruzam projetos e a spec 31 já
   chaveia tudo pela raiz.
3. **Formato dos arquivos não muda** (nenhum `FORMAT_VERSION` sobe). A única novidade é a chave `"."` do mapa `projects` do
   `navigation.json` da raiz: ela existe porque a chave de hoje é o caminho absoluto, que quebra numa cópia.
4. **Migração por filtragem**, copiando e nunca movendo: o arquivo antigo não é tocado (outras raízes precisam dele, e é o "desfazer").
   Para os compostos, que não têm ligação com a raiz, importa-se tudo. Se preferir menos ruído, a alternativa é começar vazio.
5. **Recentes e favoritos entram**, como pedido. Recentes são hábito de quem usa, então numa raiz compartilhada os recentes de
   duas pessoas se misturam (o último a gravar vence). Se incomodar, voltar os recentes para o diretório do usuário é uma mudança
   pequena no `NavigationStore` (favoritos ficariam).
6. **Raiz compartilhada:** o app não detecta nem avisa. `QLockFile` em NFS é pouco confiável e o `lain.lock` é do usuário, não da raiz;
   a spec 27-3 já aceitou "o último a gravar vence" entre duas instâncias.
7. **Fallback por raiz em `data_dir()/roots/<hash>/`** (e não os arquivos únicos de hoje): mantém "cada raiz com o seu arquivo" e um só
   caminho de código. O preço é que o que foi gravado lá não volta sozinho para `.lain/` quando a raiz fica gravável.
8. **A pasta `.lain` só nasce na primeira gravação**: abrir o Lain numa raiz e não mexer em nada não cria nada nela.
9. **`--exclude=.lain/` fixo no código do rsync**, e não só na lista padrão do `config.yaml`, porque o usuário substitui a lista
   inteira ao editá-la.
10. **Os stores com `path` explícito ficam fixados** (a suíte e os scripts): nenhum teste existente passa a criar `.lain/`; os que leem
    `data_dir() / "grids.json"` depois de rodar a janela (`test_grid_workflow.py:101`) passam a ler `<root>/.lain/grids.json`.
11. **Supera** a frase "nunca dentro de pasta de simulação (elas sincronizam)" das specs 14, 16, 21 e 23 **só quanto ao lugar**:
    `.lain/` não é uma pasta de simulação, é excluída do sync e tem o nome fixo no rsync.

## Notas de implementação

- **Novos:** `src/qe_studio/core/project_data.py`; `tests/test_project_data.py`, `tests/test_project_data_stores.py`,
  `tests/test_project_data_migration.py`, `tests/test_project_data_hidden.py`.
- **Alterados:**
  - `core/folder_memory.py`, `core/nav_store.py`, `core/grid_store.py`, `core/compounds.py`: `set_root` relocaliza (R2), migração lazy
    (R3), `path` explícito fixa; `compounds.py` ganha `set_root`; `nav_store.py` a chave `"."`; `folder_memory.load_warning` o `notice` (R4).
  - `core/calculations/base.py`: `Stores.set_root` (457 linhas, cabe).
  - `ui/plot_workflow.py` (481 linhas): duas linhas, em `_load` e `_on_param_changed`; se passar de 490, mover o bloco de
    `pop_warnings` para `Stores`.
  - `core/sync/rsync.py`: `PROJECT_DATA_EXCLUDE` nos dois dry runs.
  - `ui/help_controller.py`: a linha "Configurações do projeto" (`locate` no `about_rows`).
  - `tests/conftest.py`: `window_factory(follow_root=)`; `tests/test_grid_workflow.py:101` lê o caminho novo;
    `tests/test_architecture.py`: `core.project_data` em `QT_FREE` e o teste do nome único (R1.5).
- **Limites:** `ui/main_window.py` **não muda** (450/450); `FS_ALLOWED` não muda (nenhuma chamada de disco nova em `ui/`: `locate` e
  a migração estão em `core/`).
- **Ordem:** R1 → R2 → R3 → R4 (R4 só liga o `notice` que o R1 produz) → R5 e R6 em qualquer ordem, depois dos R1–R2.
- **Documentação ao implementar:** `CLAUDE.md`: "Detection pipeline" (`FolderMemory`: onde mora e a chave), "Projetos (spec 31)" ("os dados
  ficam chaveados pela `local_root`" passa a "ficam em `<local_root>/.lain/`"), "Atom selection in the PDOS" (`CompoundStore`), "Grids of plots"
  (`GridStore`), "Navigation" (`NavigationStore`, chave `"."`), "Threading rules" (a trava e o "dois a gravar"), "Sync" (o rsync) e as
  "Testing notes" (`follow_root`); `README.md` (onde ficam os dados do usuário, se citar); `specs/Archived/spec_0-PRD.md` só se
  disser o contrário (não verificado).

## Critérios de aceite e testes

- [ ] **O que não muda:** `.plot`, `config.yaml`, QSettings e `lain.lock` seguem como estão; `uv run pytest -m "not realdata and not perf"`
      passa sem regenerar nenhum golden e `test_fixtures_untouched.py` continua verde (R2.5: `window_factory` fixa os caminhos).
- [ ] Os quatro stores sem `path` gravam em `<root>/.lain/<nome>.json` e a pasta só existe depois da primeira gravação
      (novos: `test_project_data.py`, `test_project_data_stores.py`).
- [ ] **Cópia:** `copytree` da raiz para outro lugar, em outro caminho absoluto, devolve mapeamentos, grades, átomos, favoritos e
      recentes (`test_project_data_stores.py`).
- [ ] **Isolamento:** duas raízes na mesma sessão não trocam entradas, e trocar de raiz grava o pendente na antiga
      (`test_project_data_stores.py`).
- [ ] **Migração:** filtrada por raiz, antigo intocado, idempotente, corrompido sem efeito no antigo (novo: `test_project_data_migration.py`).
- [ ] **Somente leitura:** os quatro stores no fallback, o aviso pelo canal de `load_warning`, nada criado na raiz
      (`test_project_data_stores.py`, pulado como root).
- [ ] **`.lain` invisível:** dropdown, árvore, grade, paleta, índice, contagem de itens e detecção não a mostram; "Criar projeto…" a
      recusa (novo: `test_project_data_hidden.py`).
- [ ] **Sync:** `--exclude=.lain/` nos dois comandos mesmo com listas vazias, e um pull não traz uma `.lain/` do remoto
      (`test_sync_rsync.py`, `test_sync_integration.py`).
- [ ] "Sobre" mostra a pasta das configurações do projeto, e "Abrir pasta de dados" continua abrindo `data_dir()` (`test_help.py`).
- [ ] `".lain"` só aparece em `core/project_data.py` (`test_architecture.py`); `core/project_data.py` importa sem PyQt6.
- [ ] Passo manual de aceite (só a mão do usuário prova): copiar a raiz real para outro lugar, apontar `paths.local_root` para a cópia e
      ver os favoritos, as grades e os mapeamentos.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
