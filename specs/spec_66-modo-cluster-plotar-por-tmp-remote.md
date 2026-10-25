# Spec 66: plotar no modo cluster: cópia em `tmp_remote/`, figuras em `tmp_remote/plots_remote/`

| | |
|---|---|
| **Prioridade** | 66: a última da rodada; precisa do modo cluster (65) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 65 (modo cluster: `RemoteController`, `RemoteBrowser.mirror_of`, seleção na lista remota), spec 63 (o dry run compara pelo conteúdo: um segundo plot só baixa o que mudou), spec 17 e 27-3 (pull, prévia, `recheck_local`), spec 22 (bandas + DOS de duas pastas), spec 32 (nomes e pasta das exportações), spec 3 (`<kind>.plot`), spec 48 (`.lain/` fora do rsync: o mesmo mecanismo de exclusão fixa) |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): abre a única exceção à regra "nunca sobrescrever sem perguntar" e muda a pasta das exportações e dos `.plot`, lida em quatro módulos, além da detecção e das exclusões do rsync |

## Itens de origem (`Ideias.md`, 25/10/2026, e decisão de 25/10/2026)

> - As funções de plot continua funcionando na visualização de arquivos e pastas remotas, mas apenas para a leitura, ou seja, os arquivos são copiados para o computador local antes de serem plotados. Ou seja, plotar um grafico no ambiente remoto baixa automaticamente o conteudo necesario para a plotagem para o computador local.

Decisão do usuário (25/10/2026, substitui a "pasta local espelho" que ele escolheu antes):

> Mudei de ideia sobre a pergunta anterior, quando fizer plot no ambiente remoto, invez de baixar o nescesario para o ambiente local, quero que seja criado uma pasta chamada 'tmp_remote' dentro da pasta espelhada localmente, nela são os arquivos do que precisariam ser baixados, e dentro dela seria criado uma pasta 'plots_remote' para os plots feitos diretamente no ambiente remoto. Isso evita qualquer tipo de conflito com os arquivos locais, além disso, por ser uma pasta temporaria, se fizer um segundo plot no ambiente remoto e conflitar com o conteudo de 'tmp_remote' da pasta espelho local, o conteudo de 'tmp_remote' deve ser sobrescrito, sem perguntar ao usuario, mas isso é só apenas para as pastas 'tmp_remote', elas continuam na memoria até o usuario apagar elas.

Também decidido na mesma conversa: a prévia do plano só aparece "quando precisa" (arquivo acima de 100 MB); a listagem (dry run) acontece
sempre. "Continuam na memória" = ficam no disco, entre sessões, até o usuário apagá-las.

Exemplo: plotar a pasta remota `<remote_root>/ilita/Bands` copia o conteúdo dela para `<local_root>/ilita/Bands/tmp_remote/` e as
figuras de "Gerar" vão para `<local_root>/ilita/Bands/tmp_remote/plots_remote/`.

## Situação atual

- **Pasta das exportações e dos ajustes.** `core/plotting/names.py:13` (`PLOTS_DIR = "plots"`) é lida em quatro lugares:
  `core/plotting/export.py:28` (`plots_dir`: figuras e CSV), `core/plotting/plot_file.py:71` (`plot_file_path`: `<kind>.plot`),
  `core/plotting/saved.py:36` (`was_plotted`, que o "Plot" da barra lateral usa para decidir se só mostra) e
  `core/structure3d/image_file.py:38` ("Print" da janela 3D). Os nomes vêm de `export_prefix(folder, root)` (`names.py:20`): o caminho
  a partir do projeto, unido por `-`.
- **Detecção olha as subpastas.** `core/calculations/listing.py:14` (`IGNORED_SUBDIRS = ^(tmp|plots|out|.*\.save|\..*)$`) é a lista do
  que **não** é varrido; `FolderListing.scan` (`:25-39`) junta os arquivos de PDOS das subpastas **imediatas** (`_pdos_files`, um nível
  só). A cópia mantém a hierarquia da pasta remota, que o `pdos.qsub` deixa assim (`resources/templates/qsub/pdos.qsub.j2:15-16`,
  `mv *pdos_atm#* orbitals/`): saídas e `pdos_tot` no topo, arquivos por átomo em `orbitals/`. **Reproduzido** com os arquivos de
  `tests/fixtures/al_pdos_flat` nesse layout, num `PDOS/` local com a mesma estrutura e a cópia em `PDOS/tmp_remote/`
  (`PDOS/tmp_remote/pdos.dat.pdos_tot` e `PDOS/tmp_remote/orbitals/pdos.dat.pdos_atm#1(Al)_wfc#1(s)` …):
  - `FolderListing.scan(PDOS)` lista os arquivos locais **e** `tmp_remote/pdos.dat.pdos_tot`; os de `tmp_remote/orbitals/` ficam de
    fora (dois níveis abaixo);
  - o papel `pdos_tot` do módulo PDOS (`core/calculations/pdos/module.py:89`, globs `*pdos_tot` e `orbitals/*pdos_tot`, com
    `fnmatch`, cujo `*` atravessa `/`) aceita os dois `pdos_tot`, e `_rank` (`core/calculations/base.py:468`) escolhe o mais novo. Com a
    cópia mais nova que o local, `detect_folder(PDOS)` usa `tmp_remote/pdos.dat.pdos_tot`: o gráfico da pasta **local** sai com a DOS
    total do cluster e as projeções locais, **sem aviso**;
  - um espelho que só tem `tmp_remote/` (a pasta nunca baixada) não é detectado como PDOS (`detect_folder` vazio), e
    `detect_folder(PDOS/tmp_remote)` acha a PDOS completa da cópia, como deve.
- **Exclusões fixas do rsync.** `core/sync/rsync.py:160` (dry run do pull) e `:206` (dry run do envio) põem `PROJECT_DATA_EXCLUDE`
  (`.lain/`, spec 48) antes de `sync.exclude`; nada exclui `tmp_remote`. Sem exclusão, "Enviar ao cluster" de uma pasta mandaria a cópia
  `tmp_remote/` de volta para o cluster.
- **O pull pergunta e confere.** `core/sync/controller.py:80-92` (`_use_plan`): `LOCAL_NEWER` encerra sem transferir; com
  `confirm_plan` abre a prévia; depois `_begin_conflicts` (`:94`) pergunta arquivo a arquivo (PRD §5.4) e `_recheck` (`:108`) tira o que
  mudou localmente. `core/sync/request.py:prepare_sync` acha o lado do cluster a partir da pasta local: para `<espelho>/tmp_remote` daria
  `<remoto>/tmp_remote`, que não existe.
- **Como se plota hoje.** O "Plot" da barra lateral chama `MainWindow.plot_button` (`ui/main_window.py:381`, `PlotButton.click`:
  mostra um plot já feito, ou plota e salva com `ui.auto_generate_plot`); "Gerar" dos ajustes e Ctrl+G chamam `generate_plot`
  (`:384`, `GeneratePlot.click`, que plota e salva em `plots/`); duas pastas selecionadas que formam bandas + DOS viram a figura combinada
  (`ui/generate_plot.py:34`, `PairTarget.from_selection`). Tudo recebe pastas **locais**.
- **Regras gerais no `CLAUDE.md`:** "never overwrite a user file without asking" e "Nothing else is written into simulation folders"
  (além de `plots/` e `<kind>.plot`); esta spec cria a exceção e precisa reescrevê-las.
- Tamanhos: `core/sync/controller.py` 186, `core/sync/request.py` 207, `core/sync/rsync.py` 383, `core/plotting/names.py` 52,
  `core/calculations/listing.py` 80, `ui/main_window.py` cerca de 434/450 depois das specs 64 e 65.

## Requisitos

### R1: os nomes `tmp_remote` e `plots_remote`

1. Novo `core/scratch.py` (Qt-free, em `QT_FREE`): `SCRATCH_DIR = "tmp_remote"`, `SCRATCH_PLOTS_DIR = "plots_remote"`,
   `scratch_of(mirror: Path) -> Path` (`mirror / SCRATCH_DIR`) e `is_scratch(folder: Path) -> bool` (o nome é exatamente
   `tmp_remote`).
2. `core/plotting/names.py`: `plots_folder(folder: Path) -> Path`: `folder / "plots_remote"` quando `is_scratch(folder)`, senão
   `folder / "plots"`. Os quatro usos de `PLOTS_DIR` (`export.py:28`, `plot_file.py:71`, `saved.py:36`, `image_file.py:38`) passam a
   chamá-la. Uma pasta `tmp_remote` aberta pela árvore **local** também exporta em `plots_remote` (a regra é o nome).
3. Nomes das figuras: `export_prefix` não muda; uma figura de `ilita/Bands/tmp_remote` se chama `ilita-Bands-tmp_remote-bands.png`
   (decisão 3).
4. **Testes** (`tests/test_scratch.py`, novo): `plots_folder` para `…/tmp_remote` e para uma pasta comum; `plot_file_path`,
   `plots_dir` e `was_plotted` de uma pasta `tmp_remote` olham `plots_remote`; uma pasta comum continua em `plots` (os testes de
   exportação e `.plot` existentes passam sem mudança).

### R2: a cópia não entra na detecção da pasta-mãe nem no rsync

1. `core/calculations/listing.py:IGNORED_SUBDIRS` ganha `tmp_remote` e `plots_remote`.
2. `core/sync/rsync.py`: `tmp_remote/` vira exclusão fixa nos dry runs do pull e do envio, ao lado de `.lain/` (uma constante em
   `core/scratch.py`, `SCRATCH_EXCLUDE = "tmp_remote/"`). Nunca é enviada ao cluster nem trazida dele.
3. **Testes:** `tests/test_detection.py::test_tmp_remote_pdos_does_not_join_the_parent` (o caso reproduzido acima, com
   `copy_fixture` de `al_pdos_flat` no layout do `pdos.qsub` nos dois lugares e o `pdos_tot` da cópia mais novo: a pasta-mãe usa o
   `pdos.dat.pdos_tot` local e a listagem dela não tem nada de `tmp_remote/`; falha hoje); `test_tmp_remote_copy_is_detected_on_its_own`
   (`detect_folder(PDOS/tmp_remote)` acha a PDOS da cópia, com os arquivos de `tmp_remote/orbitals/`);
   `tests/test_sync_rsync.py::test_tmp_remote_is_never_synced` (as duas linhas de comando têm `--exclude=tmp_remote/`);
   `tests/test_sync_push.py`: um envio de uma pasta com `tmp_remote/` não lista nada dela na prévia (rsync real).

### R3: baixar para `tmp_remote`, sobrescrevendo sem perguntar

1. `core/sync/request.py`: `prepare_scratch(config, mirror: Path, *, resolved_root=None) -> SyncRequest | SyncRefusal`: a pasta local é
   `scratch_of(mirror)` e o lado do cluster é o de `mirror` (não o de `tmp_remote`). Recusa, como o envio, a raiz ("Escolha uma pasta de
   cálculo para plotar; a raiz não é copiada.") e um projeto ("Escolha uma pasta de cálculo para plotar; o projeto inteiro não é
   copiado."). `SyncScope` ganha `scratch: bool`, com o título "Baixando para plotar: {label}".
2. `core/sync/controller.py`: `SyncController(..., scratch: bool = False)`. Com `scratch`:
   - **todo** item do plano é transferido, seja `NEW`, `UPDATE` ou `LOCAL_NEWER` (um arquivo de `tmp_remote` mudado à mão também volta
     ao do cluster); sem pergunta de conflito, sem `recheck_local` e sem o fim "local mais recente";
   - a prévia só abre quando o plano tem um arquivo acima de `LARGE_FILE_BYTES` (`core/sync/planner.py:21`, 100 MB); senão transfere
     direto. `sync.confirm_plan` não muda isso;
   - plano vazio termina `UP_TO_DATE` (nada a baixar: plota o que já está lá);
   - nunca apaga: um arquivo que sumiu do cluster continua em `tmp_remote`.
   O pull normal (`scratch=False`) não muda em nada.
3. `ui/sync_coordinator.py`: `start_scratch(mirror, on_ready: Callable[[Path], None])` monta o `SyncController` com `scratch=True`, abre
   o `SyncDialog` de sempre (progresso e cancelar, PRD §5.5) e, no fim `DONE` ou `UP_TO_DATE`, chama `on_ready(scratch_of(mirror))`.
   Falha ou cancelamento: a mensagem de hoje e nada é plotado. Com um sync em andamento: "Aguarde a sincronização em andamento." no
   rodapé.
4. **Testes** (`tests/test_scratch_pull.py`, novo; rsync real com pastas locais como "cluster", `sync_helpers.run_sync`):
   - a primeira cópia cria `<espelho>/tmp_remote/` (e o espelho, se não existia) sem prévia e sem pergunta;
   - um segundo plot com o arquivo do cluster mudado **sobrescreve** a cópia sem `conflict_needed` (com o pull normal, o mesmo caso
     pergunta: o teste mostra os dois);
   - um arquivo de `tmp_remote` editado à mão (mais novo) volta ao do cluster;
   - os arquivos locais da pasta espelho (fora de `tmp_remote`) nunca são tocados, mesmo com o mesmo nome dos do cluster;
   - um arquivo de 101 MB no cluster abre a prévia (`plan_ready`); recusar a prévia não plota;
   - `tmp_remote/plots_remote/<kind>.plot` sobrevive a uma segunda cópia;
   - raiz e projeto recusados com os textos do R3.1.

### R4: "Plotar" no modo cluster

1. Menu do item remoto (spec 65 R5): "Plotar" em pastas. A barra lateral ("Plot"), "Gerar" dos ajustes e Ctrl+G com o modo cluster
   ligado agem sobre a seleção da lista remota, ou a pasta remota atual sem seleção: `MainWindow.plot_button` e `generate_plot` ganham uma
   primeira linha cada (`if self.remote.plot(generate=…): return`).
2. `RemoteController.plot(generate: bool) -> bool` (`True` quando o modo cluster tratou o pedido):
   - uma pasta: `start_scratch(espelho)`; pronto, chama o mesmo caminho local com a cópia: `plot_workflow.button.click(cópia, [])` (o
     "Plot") ou `plot_workflow.generator.click(cópia, [])` ("Gerar", que salva em `plots_remote`);
   - duas pastas: copia uma, depois a outra (um sync por vez) e chama `generator.click(cópia_a, [cópia_a, cópia_b])` ou o equivalente do
     "Plot": se elas formam bandas + DOS, sai a figura combinada, salva no `plots_remote` da pasta de bandas;
   - arquivos, ou mais de duas pastas: rodapé "Selecione uma ou duas pastas para plotar." e nada é baixado.
3. O plot abre como hoje (aba no workspace, painel de ajustes); o modo cluster continua ligado e "Árvore" volta à árvore remota. A árvore
   local, ao voltar ao modo local, mostra as pastas `tmp_remote` (o `synced` de hoje atualiza).
4. **Testes** (`tests/test_remote_plot.py`, novo; o "cluster" é uma cópia de fixture servida como pasta local, `copy_fixture`; o
   `RemoteController` com a listagem falsa da spec 65): "Plotar" de uma pasta de bandas abre a aba do plot com os dados de
   `tmp_remote`; "Gerar" escreve a figura em `tmp_remote/plots_remote/` e nada em `plots/` do espelho; duas pastas (bandas + PDOS, a
   fixture `al_pdos_orbitals` e uma de bandas) dão a figura combinada; um arquivo selecionado dá a mensagem; com o modo desligado, "Plot"
   e "Gerar" fazem o de hoje (os testes de plot existentes passam).

### R5: as regras do projeto

1. `CLAUDE.md`, "Data integrity": "never overwrite a user file without asking, **except** inside `tmp_remote/`, the scratch copy of a
   remote plot (spec 66), which a new copy overwrites". "Where state lives": `tmp_remote/` (cópia do cluster) e
   `tmp_remote/plots_remote/` (figuras e `.plot` dessa cópia) entram na lista do que vai para pastas de simulação. "Sync safety": a cópia
   para `tmp_remote` não passa pela prévia salvo arquivo grande, e `tmp_remote/` nunca é sincronizada.
2. `specs/Archived/spec_0-PRD.md` §5.4: a pergunta de conflito vale para todo arquivo **fora** de `tmp_remote/`.

## Fora de escopo

- "Plotar" de um **arquivo** remoto (saída de SCF ou relax): plote a pasta; outra spec se fizer falta.
- Apagar as pastas `tmp_remote` pelo Lain (botão "Limpar cópias"): o usuário as apaga quando quiser (decisão do usuário); o Lain não tem
  "Apagar" hoje.
- Esconder `tmp_remote` da árvore local ou da paleta: ficam à vista, para o usuário saber que existem e apagá-las.
- Baixar só os arquivos "necessários" a cada tipo de gráfico: a identificação é pelo conteúdo, nunca pelo nome (PRD §3), então a pasta
  inteira é copiada (as exclusões de `sync.exclude` já tiram os pesados: `*.wfc*`, `*.save/`, `tmp/`…).
- Visualização 3D e "Abrir com XCrysDen" no modo cluster.

## Decisões assumidas (confirmar na revisão)

1. **Copia a pasta inteira** (subpastas incluídas, menos `sync.exclude`): é o que garante que a detecção por conteúdo ache o que precisa
   (a PDOS precisa de `orbitals/`).
2. **Arquivo grande (> 100 MB) mostra a prévia** (escolhido antes da mudança para `tmp_remote` e mantido): é a única pergunta; não há
   limite de tamanho total.
3. **Nomes das figuras com `tmp_remote`:** `ilita-Bands-tmp_remote-bands.png`, sem caso especial em `export_prefix`; diz de onde a figura
   veio. A alternativa é tirar o `tmp_remote` do prefixo (uma linha em `export_prefix`).
4. **Raiz e projeto recusados**, como no envio: plotar um projeto inteiro copiaria todos os cálculos dele.
5. **`plots_remote` vale para qualquer pasta chamada `tmp_remote`**, também aberta pela árvore local: a regra é o nome, não o modo.
6. **Nada é apagado** em `tmp_remote` por uma cópia nova; "sobrescrito" vale para os arquivos que vêm do cluster.

## Notas de implementação

- Novos: `core/scratch.py` (novo, Qt-free, em `QT_FREE`); `tests/test_scratch.py`, `tests/test_scratch_pull.py`,
  `tests/test_remote_plot.py` (novos).
- Alterados: `core/plotting/names.py` (`plots_folder`), `core/plotting/export.py`, `core/plotting/plot_file.py`,
  `core/plotting/saved.py`, `core/structure3d/image_file.py` (usam `plots_folder`), `core/calculations/listing.py`
  (`IGNORED_SUBDIRS`), `core/sync/rsync.py` (exclusão fixa), `core/sync/request.py` (`prepare_scratch`, `SyncScope.scratch`),
  `core/sync/controller.py` (`scratch`), `ui/sync_coordinator.py` (`start_scratch`), `ui/remote_controller.py` (novo na spec 65: `plot`, "Plotar" no
  menu), `ui/main_window.py` (uma linha em `plot_button` e outra em `generate_plot`), `tests/test_architecture.py` (`QT_FREE`), catálogo
  `lain.po`/`.mo`.
- Ordem: R1 e R2 (sem UI; a suíte de exportação e detecção verde) → R3 → R4 → R5.
- Limites: `ui/main_window.py` cerca de 436/450; nenhum outro arquivo perto do limite.
- Documentação ao implementar: `README.md` (no "Modo cluster" da 65: "Plotar" copia para `tmp_remote/`, figuras em `plots_remote/`,
  a cópia é sobrescrita sem perguntar e fica até ser apagada, nunca é sincronizada); `CLAUDE.md` e PRD como no R5.
- i18n: textos novos em `_()`, depois `scripts/i18n.py update`, tradução e `compile`.

## Critérios de aceite e testes

- [ ] Fora de `tmp_remote` nada muda: exportações, `.plot`, detecção e pull passam sem mudar expectativas (`test_figure_regression.py`,
      goldens, testes de sync).
- [ ] Figuras e `.plot` de uma cópia ficam em `tmp_remote/plots_remote/` (`tests/test_scratch.py`, `tests/test_remote_plot.py`).
- [ ] A PDOS de `tmp_remote` não entra na pasta-mãe (`test_tmp_remote_pdos_does_not_join_the_parent`); `tmp_remote/` nunca vai nem vem
      pelo rsync (`test_tmp_remote_is_never_synced`, `tests/test_sync_push.py`).
- [ ] Uma segunda cópia sobrescreve sem perguntar, só dentro de `tmp_remote`; arquivo grande abre a prévia (`tests/test_scratch_pull.py`).
- [ ] "Plot", "Gerar" e Ctrl+G no modo cluster plotam a cópia, uma pasta ou o par bandas + DOS (`tests/test_remote_plot.py`).
- [ ] Passo manual de aceite: no cluster real, plotar uma pasta de bandas no modo cluster, depois de novo, e ver a figura em
      `tmp_remote/plots_remote/`.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
