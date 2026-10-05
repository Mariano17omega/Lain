# Spec 27-8: Interface fluida — grid, sistema de arquivos na GUI thread e invalidação da detecção

| | |
|---|---|
| **Prioridade** | 27-8 |
| **Status** | Parcial: R1, R3, R4 e R5 implementados; R2 (passo 3, desenhar em worker) pendente |
| **Depende de** | spec 14 (desempenho da detecção), spec 15 (workers), spec 23 (Grids), spec 22 (bandas + DOS) |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): começa por medir e o restante são correções localizadas com teste. **Trocar para Opus 5.5** só se o R1 mostrar que o grid estoura o orçamento e o R2 exigir desenhar em worker (mudança de arquitetura do `PlotView`). |

## Itens de origem (`specs/report-04-10-26.md`)

- **T2 (Médio):** o grid (até 6×6) é desenhado inteiro na GUI thread a cada edição, sem orçamento de perf.
- **T4 (Baixo):** sistema de arquivos (`resolve`, `exists`, `is_dir`, leitura do início de arquivos) na GUI thread; o teste de arquitetura não vigia isso.
- **T5 (Baixo):** `invalidate(pasta)` apaga os resultados de todas as pastas irmãs.
- **B4 (Baixo):** `_detect` engole qualquer exceção e grava `[]` como resultado válido.

## Situação atual

- **T2.** `params.changed` → `PlotWorkflow._on_param_changed` (`plot_workflow.py:359`) reinicia `_render_timer` (single-shot, `RENDER_DEBOUNCE_MS = 120`, `:52`, `:112-115`) → `_render_current` →
  `PlotView.render` (`ui/widgets/plot_view.py:242`): tenta `MPL_LOCK.acquire(blocking=False)` (se ocupado, `_retry` a cada `RETRY_MS = 50`), roda `session.render(figure, style)` e `canvas.draw_idle()`;
  o desenho Agg também é na GUI thread (`ScaledFigureCanvas.draw`, `:43`, mesmo *try-lock*). Para um grid, `render_grid` (`core/calculations/grid/render.py:40`) faz `figure.clear()`, uma `SubFigure`
  por célula, `session.render(cell, …)` por célula e `fit_cell` (`render.py:73`; `core/plotting/cell_layout.py:23`: `PASSES = 2` de `get_window_extent`/`get_tightbbox` em todos os eixos e
  `subplots_adjust`) por célula. `grid_session.build_grid_session` (`core/plotting/grid_session.py:15`) monta a sessão. Testes de perf existentes: `test_perf_detection.py` (`@pytest.mark.perf`:
  detecção, sniff, refresh, import; fixtures de sessão com `tests/synthetic.py`, `BUDGET`, `report(name, s)`, `timed(fn)`) e testes inline de latência (`test_plotting.py:254`, `test_scf.py:353`,
  `test_relax.py:279`, `test_bands_spin_render.py:321`, estilo `perf_counter() < 0.5`). **Não há perf de grid, de bandas + DOS nem de PDOS com muitos átomos.** Ajudantes: `tests/plot_grid_helpers.py`
  (`session_of`, `grid_of(cells, tmp, rows, cols, name, stores)`, `draw(session, dpi=72)`, refs `BANDS`, `PDOS`, `RELAX`, `SCF`, `BANDS_DOS`) e `tests/atoms_helpers.py:pdos_folder(root, species=("Al","Al"),
  name="pdos")` (N átomos = N entradas em `species`). `pyproject.toml:41-47`: marcadores `realdata` e `perf`; `addopts = "-m 'not realdata'"` (perf **roda** no pytest local); o CI roda
  `-m "not realdata and not perf"` e tem um job `perf` à parte, `continue-on-error`.
- **T4.** `SyncCoordinator.show_scope` (`ui/sync_coordinator.py:118-135`) faz até 3 chamadas a `sync_scope` (pasta, projeto inteiro, push), cada uma com `.resolve()` ×2 em `core/sync/request.py:152-153` e
  mais ×2 em `prepare_sync` → `remote_dir_for` (`core/sync/rsync.py:49-50`): até 12 `resolve` por troca de pasta (`main_window.py:298`, `:97`, `:106`). `push_state` (`sync_coordinator.py:116`) faz
  `is_dir()` + `push_availability` → `prepare_push` (`request.py:60-71`, mais resolves e `is_dir`) ao montar o menu de contexto (`ui/widgets/context_menu.py:97`). `grids_controller.py:98`
  (`describe`) chama `path.exists()` por referência. `core/plotting/export.py:56` `plan_export` (docstring "Stats the targets (GUI thread)": `existing_targets` `:32` e o laço de `.exists()` de
  `next_free_stem` `:36`, chamado por `ui/plot_export.py:44`). `context_menu.py` usa `is_dir()` (`:89,185,199,208`) e `looks_like_input` (`:199`, lê o início do arquivo) e `setup_page.py:194` também.
  `tests/test_architecture.py` (`test_the_ui_does_not_read_files`, `:131-144`) percorre o AST de `ui/` (exceto `UI_READERS = {"ui/theme/manager.py"}`) e proíbe só `open`, `read_text`, `read_bytes`,
  `loadtxt` (`READ_CALLS`, `:27`). Um `grep` acha 37 chamadas a `resolve/exists/is_dir/…` em 17 arquivos de `ui/` hoje.
- **T5.** `_affected` (`ui/services.py:24-33`) é verdadeira para `folder is None`, para chaves sob a pasta e para qualquer pasta com o mesmo pai (`Path(key).parent == Path(folder).parent`);
  `invalidate` (`:95-113`) apaga os resultados, poda ou limpa os sniffs e reinicia as tarefas ativas com `fresh=True`. A dependência real é de `infer_from_neighbours`
  (`core/calculations/base.py:330-358`): procura o papel `scf_out` nos arquivos do **pai** e nas irmãs diretas cujo nome casa `*scf*` (um nível), só se o papel ainda não foi achado; só os
  módulos de bandas (`bands/module.py:118`) e de PDOS (`pdos/module.py:118`) a chamam. Logo `_affected` é mais largo que a dependência. Lacuna oposta: `_within` só olha para baixo; invalidar uma
  subpasta ignorada (`IGNORED_SUBDIRS`, `base.py:44`, ex.: `<calc>/orbitals`) não limpa o resultado da pasta do cálculo.
- **B4.** `ui/services.py:17-21` `_detect`: `except Exception: return []`, sem `log` (o módulo nem tem logger). `_on_done` guarda `[]` e emite `detected`: uma falha parece "sem cálculo
  aqui". `request` (`:61`) submete só com `on_done`; se `_detect` relançasse, `TaskHandle._deliver` logaria "background task failed", `_on_done` nunca rodaria, `results()` reagendaria sem fim
  e o `busy` `detect:{key}` do `PlotWorkflow` nunca terminaria. `SniffCache.sniff` (`core/sniff.py:228-244`) devolve `UNKNOWN` só em `OSError` (stat ou `_sniff_uncached`); qualquer outra exceção de
  `parse_pw_output`/`parse_bandsx_output` (por exemplo um `ValueError`) sobe (`_sniff_input` já tem o seu `except Exception`). Um único arquivo estranho zera a pasta inteira até o F5.

## Requisitos

### R1: Medir o grid (T2) — primeiro
1. `tests/test_perf_grid.py` (novo, `@pytest.mark.perf`, no estilo e com as fixtures de `test_perf_detection.py`): mede `render_grid` + `canvas.draw()` (via `plot_grid_helpers.draw`) de
   (a) grid 6×6 de células mistas (bandas, PDOS, relax, SCF, bandas + DOS), (b) grid 6×6 só de PDOS, (c) uma PDOS com 100 átomos (`atoms_helpers.pdos_folder(species=("Al",)*100)`) e (d) uma figura
   de bandas + DOS. `BUDGET` inicial: **1,0 s** por render de grid (o relatório sugere agir acima disso) e 0,5 s para as figuras simples (a mesma meta do PRD §7). `-m perf -s` imprime os números.
2. A **linha de base medida** entra nas "Notas" desta spec, no mesmo formato da spec 14. Se todas estiverem dentro do orçamento, **R2 não é implementado** e a spec só registra os números e
   mantém o teste como guarda.

### R2: Só se R1 estourar — reduzir o custo (T2)
Em ordem de custo/benefício, parando na primeira que cumprir o orçamento (cada passo com a sua medição antes/depois):
1. `fit_cell`: uma passada (`PASSES = 1`) durante a edição (parâmetros mudando) e duas na passada final (timer de 400 ms depois da última edição); ou cache do `tightbbox` por célula que não mudou
   (`PlotSession.params` igual).
2. Debounce adaptativo: 120 ms para figuras simples, 400 ms para `GridDataset`.
3. Render em worker (decisão de arquitetura): `Figure` + `FigureCanvasAgg` próprios, como a exportação (`export_figure`, sob `MPL_LOCK`), e a imagem resultante trocada no `PlotView`; as interações
   (pan/zoom, readout) usam o desenho final. **Se for preciso este passo, trocar o modelo da implementação para Opus 5.5.**

### R3: Sistema de arquivos na GUI thread (T4)
1. **Reduzir os `resolve`:** `SyncCoordinator` guarda a raiz resolvida (recalculada em `set_config`/troca de raiz) e o escopo "projeto inteiro" calculado uma vez por configuração;
   `sync_scope(config, folder, *, resolved_root=None)` e `prepare_sync/prepare_push/remote_dir_for` aceitam a raiz já resolvida. `show_scope` passa de até 12 `resolve` para 1 por troca de pasta
   (o da pasta). `push_state` usa o mesmo caminho.
2. **Vigiar:** `test_architecture.py` ganha um 2º conjunto `FS_CALLS = {"resolve", "exists", "is_dir", "is_file", "stat", "iterdir", "glob", "rglob", "samefile"}` e a lista `FS_ALLOWED`
   (arquivo → contagem) com as chamadas que existem hoje (37 em 17 arquivos), de modo que **uma chamada nova em `ui/` falha o teste** e a lista só pode diminuir (o teste também falha se a contagem
   real ficar *menor* que a registrada, para a lista ser atualizada). Não vigia `ui/theme/manager.py`.
3. Os pontos quentes citados em "Situação atual" ficam documentados (um comentário curto em cada) como "aceitos: disco local" ou são movidos para `run_task`; `plan_export` ganha o aviso explícito na
   docstring de que roda na GUI. Nada de leitura de **conteúdo** nova em `ui/`.
4. Testes: `sync_scope` com `resolved_root` dá o mesmo resultado que sem; contador de `Path.resolve` (monkeypatch) por `show_scope` ≤ 1; o teste de arquitetura reprova uma chamada nova de exemplo
   (arquivo sintético) e aprova a lista atual.

### R4: Invalidação da detecção (T5)
1. `core/calculations/base.py` exporta `is_neighbour_scf(name)` (o predicado de nome), `neighbour_scf_folders(folder) -> list[Path]` (as irmãs diretas cujo nome casa `*scf*`) e `reads_from(key, folder)` (a detecção de `key` pode ler arquivos de `folder`: `key` está sob `folder`, ou `folder` é uma irmã `*scf*` de `key`); `infer_from_neighbours` passa a usar `neighbour_scf_folders`.
   `DetectionService._affected` usa `reads_from`. **A dependência é das irmãs que leem a SCF, não o contrário:** `bands_a` e `pdos_a` leem `scf_a`; a SCF não lê ninguém. As duas pontas não podem divergir (um teste as liga).
2. **Lacuna:** a detecção de `<calc>` lê os arquivos PDOS das subpastas imediatas que não são ignoradas (`FolderListing.scan`; `orbitals` **não** está em `IGNORED_SUBDIRS`). `feeds_parent(folder)` (um `scandir`) diz se `folder` alimenta o pai; então invalidar `folder` invalida também `folder.parent`. Uma subpasta sem arquivos PDOS (ou ignorada) não invalida o pai.
3. As irmãs que não são afetadas **mantêm** o resultado (não voltam a "detectando…"). F5 sem pasta (`invalidate()`) continua limpando tudo (`SniffCache.prune`, spec 14).
4. Testes: projeto com `scf_a`, `bands_a`, `pdos_a`, `relax_a` e `nested/pdos_b`: invalidar `bands_a` limpa só `bands_a` (a raiz e as irmãs mantêm); invalidar `scf_a` limpa `scf_a` e as irmãs (o serviço não sabe, antes da detecção, quais leem a SCF) e deixa `nested/pdos_b`; invalidar `<calc>/orbitals` (com arquivos PDOS) limpa `<calc>`, mas uma subpasta sem PDOS não; `reads_from` e `neighbour_scf_folders` concordam em todas as irmãs, e `infer_from_neighbours` usa `neighbour_scf_folders`.

### R5: Detecção que não zera a pasta (B4)
1. `SniffCache.sniff` captura **qualquer** `Exception` por arquivo: devolve `FileKind.UNKNOWN`, grava `log.exception("sniff falhou: <arquivo>")` (uma vez por (arquivo, mtime, tamanho)) e guarda o
   `UNKNOWN` no cache como as demais entradas, para o arquivo estranho não ser relido a cada chamada.
2. `_detect` ganha `log` e deixa de engolir: a exceção sobe e `DetectionService.request` passa `on_error`, que loga, guarda um resultado `[]` marcado como **falha** (`self._failed[key] = True`),
   emite `detected` (o busy termina) e mostra no rodapé, uma vez por pasta, "Falha ao detectar <pasta> (veja o log)". O F5 limpa a marca e tenta de novo. `peek_results` continua devolvendo `[]`.
3. Testes: monkeypatch de `parse_pw_output` levantando `ValueError` num dos arquivos → a pasta ainda detecta os outros e o arquivo vira `UNKNOWN` (com log); `_detect` que levanta → `detected`
   emitido, mensagem uma vez, `busy` termina, F5 tenta de novo.

## Fora de escopo
- Reescrever o desenho do `PlotView` ou do `fit_cell` além de R2.
- Mover tudo o que toca o disco em `ui/` para workers (R3 só vigia e reduz o caso quente).
- Cancelamento dos loaders e cache de datasets (27-4) e o fechamento (27-5).
- Cache de `looks_like_input` nos menus.

## Decisões assumidas (confirmar na revisão)
1. Orçamento de **1 s** para o grid 6×6 (o relatório diz "se passar de ~1 s"); 0,5 s para as figuras simples (PRD §7).
2. O teste de arquitetura de R3.2 usa uma **lista de exceções que só diminui** em vez de zerar as 37 chamadas agora.
3. Falha de detecção mostra uma mensagem no rodapé (não toast, não modal): é um defeito de arquivo, não do usuário.
4. Se o R1 passar, R2 não é feito e a spec fica "implementada" só com a medição e o teste de guarda.

## Notas de implementação
- Novos: `tests/test_perf_grid.py`.
- Alterados: `ui/sync_coordinator.py`, `core/sync/request.py`, `core/sync/rsync.py`, `ui/services.py`, `core/sniff.py`, `core/calculations/base.py`, `tests/test_architecture.py`,
  `tests/test_services*.py`, `tests/test_sniff*.py` e, só se R2 for necessário, `core/plotting/cell_layout.py`, `core/calculations/grid/render.py`, `ui/plot_workflow.py`, `ui/widgets/plot_view.py`.
- A linha de base de R1 entra aqui, na seção "Notas", ao implementar.

## Critérios de aceite e testes
- [ ] `-m perf -s` imprime os tempos de grid 6×6 (misto e PDOS), PDOS de 100 átomos e bandas + DOS; todos dentro do orçamento (ou R2 aplicado até cumprir). **Impresso; o grid 6×6 está fora (2,4 s): R2 passo 3 pendente.**
- [x] `show_scope` faz ≤ 1 `resolve` por troca de pasta; `sync_scope` com `resolved_root` equivale ao anterior.
- [x] `test_architecture.py` reprova uma chamada nova de `resolve/exists/is_dir/…` em `ui/` e a lista de exceções não cresce.
- [x] Invalidar uma pasta só limpa ela, as pastas que leem os seus arquivos (as irmãs, se ela é `*scf*`; o pai, se ela tem arquivos PDOS); as demais mantêm o resultado.
- [x] Arquivo que quebra o parser vira `UNKNOWN` com log e não zera a pasta; `_detect` com falha termina o busy, mostra a mensagem e o F5 tenta de novo.
- [x] `ruff`, `pyright`, suíte `-m "not realdata and not perf"` verdes.

### Implementação (R1, R3, R4, R5)

- Novos: `tests/test_perf_grid.py`, `tests/test_neighbours.py`.
- **R5.** `SniffCache.sniff` captura qualquer `Exception` (menos `cancel.Cancelled`), loga `sniff falhou: <arquivo>` e guarda o `UNKNOWN` no cache.
  `DetectionService._detect` não engole mais; `_on_error` loga, guarda `[]` marcado em `_failed`, emite `detected` e depois o sinal novo
  `message` ("Falha ao detectar <pasta> (veja o log)", uma vez por pasta; `invalidate` limpa a marca). `MainWindow` liga `service.message` ao rodapé.
- **R4.** Ver R4.1/R4.2 acima. `DetectionService.invalidate` calcula `feeds_parent(folder)` uma vez (um `scandir` na GUI thread) e passa o pai a `_affected`.
  Desvios do texto original: (a) a direção da dependência (o texto dizia que invalidar `bands_a` limpava `scf_a`, e invalidar `scf_a` deixaria `bands_a` velha);
  (b) `orbitals` não está em `IGNORED_SUBDIRS`: a lacuna real é o pai ler os PDOS das subpastas, não as pastas ignoradas (que o pai nunca lê).
- **R3.** `remote_dir_for(..., resolved_root=)` e `remote_dir_of`, `prepare_sync` / `prepare_push` / `push_availability` / `sync_scope` com `resolved_root=`;
  `SyncCoordinator._set_root` guarda a raiz resolvida e o escopo do projeto inteiro por configuração; `show_scope` faz 1 `resolve` (era até 12).
  `FS_CALLS` / `FS_ALLOWED` em `test_architecture.py`: 35 chamadas em 17 arquivos (o relatório contava 37; o AST conta as que existem hoje).
  Os pontos quentes têm comentário "aceito: disco local" (`context_menu`, `setup_page`, `grids_controller`) e `plan_export` avisa na docstring que roda na GUI.

### Medições (R1) — `uv run pytest -m perf -s tests/test_perf_grid.py`

Máquina do desenvolvedor (x86_64, Python 3.11), mediana de 3 execuções, `plot_grid_helpers.draw` (render do módulo + `canvas.draw()` Agg, 72 dpi).

| Medição | Linha de base | Orçamento |
|---|---|---|
| Grid 6×6 misto (bandas, PDOS, relax, SCF, bandas + DOS) | 2 430 ms | 1 000 ms — **fora** |
| Grid 6×6 só de PDOS | 2 730 ms | 1 000 ms — **fora** |
| PDOS de 100 átomos | 67 ms | 500 ms |
| Bandas + DOS | 74 ms | 500 ms |

Onde vai o tempo do grid misto: render 1,67 s (dos quais `fit_cell` 1,33 s, quase tudo em `get_tightbbox` → `_update_ticks`) + `canvas.draw()` 0,8 s.
Experimentos fora do repositório (R2): `PASSES = 1` → 2,13 s; sem `fit_cell` nenhum → 1,77 s (o `draw` sobe para 1,3 s sem o layout). Os passos 1 e 2 do R2
(menos passadas, debounce maior) não chegam a 1 s nem em teoria, e o passo 1 ainda exige uma passada final que bloqueia de novo. **Só o passo 3 (render em worker) cumpre.**
Os dois testes de grid estão `xfail(strict=True)` até lá (o teste passa a falhar como XPASS quando o R2 chegar: o marcador sai).
