# Spec 15: Workers unificados, exportação em segundo plano e divisão do `MainWindow`

| | |
|---|---|
| **Prioridade** | 15 |
| **Status** | Implementada. Desvios: eram 7 variantes de worker, não 5 (`summary_view` e `diff_view` vieram nas specs 11 e 12), e todas usam `core/tasks.py`; os resultados passam por um único objeto despachante no thread da GUI, então não há objeto de sinais por tarefa nem `QTimer.singleShot(0)` para workers (sobram dois usos que não são workers, comentados: o próximo conflito do sync e os diálogos depois da detecção); os callbacks de um `TaskGroup` recebem a chave (`on_done(key, result)`); pools privados (detecção, contagem da grade, `.plot`) não têm pai Qt, porque um pool filho é destruído dentro do destrutor C++ do pai, às vezes com o GIL preso, e espera tarefas que precisam do GIL (precaução contra um travamento intermitente visto duas vezes na suíte durante a implementação, cuja causa não foi isolada; não se repetiu depois); a escrita **e a leitura** do `.plot` ficam numa fila de 1 thread (`ui/plot_settings.py:PlotSettingsStore`), o que garante a ordem sem I/O na GUI, e por isso carregar um gráfico tem duas etapas (dados no pool global, depois o `.plot` na fila); além do `closeEvent`, o `rename_path` também grava na hora (`flush_now(inside=)`, inclusive o `.plot` de um gráfico de arquivo, como o SCF) e espera as exportações em curso; fechar a janela espera todas as exportações pedidas, também as que ainda estão na fila (até 10 s); `export_plot()` devolve `bool` e o fim chega pelo sinal `export_finished(list[Path])`, que os testes esperam; módulos a mais para manter cada um com uma tarefa e o `MainWindow` abaixo de 400 linhas: `ui/plot_export.py` (`PlotExporter`), `ui/busy.py` (`BusyTracker`) e `ui/actions.py` (tabela `ACTIONS`: id, menu, texto, atalho e slot; `MainWindow._actions` guarda os `QAction`); o menu de contexto (`ItemActions.show`), o fechamento das abas de um caminho (`Workspace.close_tabs_under`) e a aplicação do config nos painéis (`apply_config`) saíram da janela; `TextPreview` guarda todos os campos do antigo `Loaded` (mais `omitted_lines`); `status_label` devolve o nível e `ui/file_types.py:level_token` o converte em cor; `core/detection.py` ganhou também `ManualTarget`, `mapping_message` e `plottable_modules`; a lista `ignore` do pyright foi esvaziada (o `pyproject.toml` a prometia para esta spec) e `tests/test_calculation_sizes.py` saiu, coberto por `tests/test_architecture.py` |
| **Depende de** | spec 7 (CI), spec 8 (contrato do módulo e tipagem) |
| **Usada por** | spec 17 (`SyncCoordinator`), spec 18 (registro de ações para a paleta) |
| **Esforço** | G |

## Itens de origem (`report.md` §2)

> **A1. `MainWindow` acumula 4 responsabilidades** (`main_window.py`, 991 linhas) […] → Extrair `LayoutController`, `PlotWorkflow`, `SyncCoordinator`; `MainWindow` fica como raiz de composição. Ganho: testar sem montar janela inteira; menos risco nas regras de thread.
>
> **A2. Boilerplate de worker repetido 5×** […] É exatamente a regra frágil do CLAUDE.md (sinal na própria thread do objeto). → `run_in_pool(fn, on_done, on_error, pool=…)` que encapsula tokens, cancelamento e tempo de vida.
>
> **A8. Perf de exportação e render**: `export_plot` roda `export_figure` no thread GUI: PNG 600 DPI + SVG + PDF de PDOS congela a janela. → worker (Figure próprio + `FigureCanvasAgg`; matplotlib não é formalmente thread-safe, então serializar com lock global).
>
> **O7** Cursor global de ocupado (`setOverrideCursor`) com contabilidade manual em 3 lugares. → Indicador local (spinner na aba/status).

Ordem pedida pelo usuário: esta refatoração vem **depois** das features (specs 9–13), para que o código
novo seja movido uma vez só.

Regras de arquitetura do `CLAUDE.md` (30/09/2026), que esta spec aplica ao código existente:
> - Evite escrever arquivos com mais de 500 linhas que centralizam tudo.
> - Na UI, src/qe_studio/ui deve ter apenas a logica da interface, não deve ter logica no backend. O backend deve ficar reservado ao core.
> - O programa deve ser feito de forma modulada que facilite a manutenção.

## Situação atual

**A2: seis variantes de worker:**
| Arquivo | Tarefa | Mantida viva por | Token / cancelamento |
|---|---|---|---|
| `ui/services.py:16-35,138-142` | `_DetectTask` (pool próprio, 2 threads) | `_finished` + `QTimer.singleShot(0, clear)` | `itertools.count`; `cancelled` checado só antes de rodar |
| `ui/main_window.py:99-125,713-718` | `_LoadTask` (pool global) | `singleShot(0, lambda: self._loads.pop(key))` | **nenhum**; só evita duplicar por chave |
| `ui/widgets/workspace.py:61-78,102-105` | `_LoadText` (pool global) | atributo `self._task` do `TextViewer` | nenhum; fechar a aba não cancela |
| `ui/widgets/file_grid.py:43-61,290-300` | `_CountTask` (pool próprio) | `_finished_counts` + `singleShot(0, clear)` | `_count_generation` |
| `core/sync/controller.py:94-112,243-252` | `_PlanTask` (pool global) | `_finished_tasks` + `singleShot(0, clear)` | `_run_id` |
| `core/sync/monitor.py:43-44,97-121` | `threading.Thread` daemon | lista `_probes`, podada no próximo `check()` | resultados ignorados após `stop()` |

O `monitor.py` usa threads daemon de propósito: o DNS ignora o timeout de conexão, e o destrutor de um
pool espera sem limite. Isso está documentado no CLAUDE.md.

**A8: exportação no thread da GUI:**
- `MainWindow.export_plot` (`main_window.py:870-903`) chama `export_figure` de forma síncrona;
- `core/plotting/export.py:38-71` (`render_figure` + um `savefig` por formato) monta uma figura Agg
  nova, renderiza e grava PNG (300/600 DPI), SVG e PDF via arquivo temporário + `os.replace`;
- quem chama: Ctrl+E (l.294), o painel (l.327), a barra do gráfico (l.751) e o **`auto_export` de todo
  Ctrl+G** (l.762-763). Ou seja, todo "Gerar Gráfico" trava a GUI durante a exportação;
- também no thread da GUI: `_flush_plot_files` (YAML) e `rename_item`.

**O7: cursor de ocupado:**
- `QApplication.setOverrideCursor` em `generate_plot_for` (l.643) e `_load` (l.710);
- `restoreOverrideCursor` em `_on_detected` (l.654) e `_finish_load` (l.717-718, com guarda);
- o pareamento depende da pilha interna do Qt. Se uma detecção nunca chegar, o cursor fica preso, e
  nenhum teste verifica isso.

**A1: `MainWindow` (991 linhas), métodos por responsabilidade:**
- *Layout e estado da janela:* `_build`, `_build_menus`, `_connect`, `_restore_state`, `_save_state`,
  `set_left_mode`, `set_panel_visible`, `_sync_panel_widths`, `_apply_panel_layout`, `fit_widths`
  (l.135-163), `toggle_theme`.
- *Fluxo de plot:*
  - `toggle_plot`, `preview_plot`, `generate_plot(_for)`, `_on_detected`, `_plot_detected`,
    `_map_manually`, `_load`, `_finish_load`, `_on_loaded`;
  - `_on_tab_changed`, `_on_param_changed`, `_on_limits_changed`, `_render_current`, `_on_rendered`,
    `_update_readout`, `_remap_current`, `export_plot`;
  - persistência `.plot`: `_mark_unsaved`, `_flush_plot_files`, `_on_tab_closing`, `_restore_defaults`.
- *Sync:* `_test_connection`, `_apply_cluster_label`, `start_sync`, `_ask_password`, `_run_sync`,
  `_ask_conflict`, `_on_sync_finished` (l.906-991).
- *Transversais:* `rename_path` (l.425-461), `reload_config` (l.587-611), `closeEvent` (l.381-390).

**Lógica de backend dentro de `ui/` (fere a regra do `CLAUDE.md`):**
| Onde | O que faz | Por que é backend |
|---|---|---|
| `ui/widgets/workspace.py:23-58` (`read_for_viewer`, `load_for_viewer`) | lê o arquivo, corta cabeça/cauda, decide os banners de log de job | leitura de arquivo e regra de negócio |
| `ui/file_types.py:19,54-89` (`JOB_LOG`, `is_job_log`, `viewer_kind`, `status_label`) | classifica arquivos (regex, leitura de 4 KB para achar NUL) e decide OK/INCOMPLETO/AVISO/ERRO | classificação por conteúdo |
| `ui/plot_session.py` | `PlotSession`: dataset + parâmetros + padrões + render com `rc_context` | não usa Qt nenhum |
| `ui/main_window.py:659-674` (`_plot_detected`) | escolhe entre resultados plotáveis completos | regra de detecção |
| `ui/main_window.py:726-745` (`_on_loaded`) | monta os parâmetros: padrão → `.plot` → legado → `apply_stored` | regra de persistência |
| `ui/main_window.py:870-903` (`export_plot`) | formatos, alvos existentes, `next_free_stem` | regra de exportação (só o diálogo é UI) |
| `ui/main_window.py:906-931` (`start_sync`) | sync ligado?, pasta remota, precisa de senha? | regra de sync (só os diálogos são UI) |
| `ui/widgets/fs_model.py:73-88` | casa `ui.hidden_dirs` com `fnmatch` | regra de filtro (o proxy Qt é UI) |

**Arquivos com mais de 500 linhas:** `ui/main_window.py` (991). O `core/calculations/bands.py` (504) é
dividido pela spec 13, que vem antes desta.

## Requisitos

### R1: Helper único de tarefas (A2)
1. Novo `src/qe_studio/core/tasks.py` (módulo com Qt, como `controller.py` e `monitor.py`; o CLAUDE.md é
   atualizado):
   ```python
   handle = run_task(fn, *args, on_done=cb, on_error=err_cb, pool=None, group="loads")
   handle.cancel()  # o resultado é descartado; fn pode consultar handle.cancelled
   handle.done  # bool
   ```
2. Garantias:
   - `on_done`/`on_error` rodam no thread da GUI, no próximo turno do loop;
   - a tarefa e o objeto de sinais ficam vivos até lá (o `QTimer.singleShot(0, …)` fica **só** aqui);
   - um token por tarefa; um resultado de tarefa cancelada ou substituída nunca chega ao callback;
   - `group`: um `TaskGroup` opcional que cancela a anterior do mesmo grupo e chave
     (`group.submit(key, fn, …)`), o padrão de `services.py` e `main_window._loads`;
   - `TaskGroup.shutdown(timeout_ms)`: cancela as pendentes e espera as em execução.
3. Migrar as 5 variantes com `QRunnable` (tabela acima) para `run_task`/`TaskGroup`. O `TextViewer`
   cancela a leitura ao ser destruído. O `monitor.py` **continua** com threads daemon (exceção
   documentada no próprio `tasks.py`).
4. Os callbacks são métodos ligados (regra do CLAUDE.md), e o helper guarda só referências fracas ao
   receptor quando ele é um `QObject`, para não estender a vida de widgets fechados.

### R2: Indicador local de ocupado (O7)
1. Sai todo `setOverrideCursor`/`restoreOverrideCursor`.
2. Detecção e carga de um gráfico mostram:
   - no rodapé, um spinner pequeno (o `CircularProgress` do `sync_dialog`, em tamanho reduzido) com
     "Detectando cálculo…" / "Carregando <tipo>…";
   - na aba de destino, se já existir, o ícone da aba trocado por um spinner até o render.
3. O indicador é controlado por contagem de tarefas ativas no `PlotWorkflow`, e não por pares
   set/restore: chega a zero → some.

### R3: Exportação em worker (A8)
1. `export_figure` roda via `run_task` no pool global. Cada exportação cria a própria `Figure` e o próprio
   `FigureCanvasAgg`, sem compartilhar artistas com a figura da tela.
2. Lock global `core/plotting/mpl_lock.py:MPL_LOCK` (`threading.RLock`) em volta de **todo** bloco que usa
   `matplotlib.rc_context` ou cria e renderiza figuras: `PlotSession.render` (tela) e `render_figure`
   (exportação). O `rcParams` é global, e o `rc_context` de um thread vazaria para o outro.
3. Na tela, `PlotView` tenta `MPL_LOCK.acquire(blocking=False)`. Se estiver ocupado (exportação em
   curso), reagenda o render com `QTimer.singleShot(50, …)` em vez de bloquear a GUI. O
   `_render_timer` existente continua debounciando edições.
4. A verificação de sobrescrita (`next_free_stem`, diálogo "Sobrescrever?") continua na GUI **antes**
   de disparar a tarefa. A gravação (tmp + `os.replace`) fica na tarefa.
5. Feedback: rodapé "Exportando…" com spinner. No fim, "Salvo em plots/bands.png, .svg, .pdf" (como
   hoje). Em erro, `QMessageBox.warning`, como hoje.
6. Fechar o app com exportação em curso: `closeEvent` espera o `TaskGroup` de exportação (até 10 s),
   para não deixar `.tmp` pela metade. Os `.tmp` órfãos de uma queda são ignorados e limpos na próxima
   exportação para o mesmo destino.
7. A escrita do `.plot` (`_flush_plot_files`) também vai para worker (YAML pequeno, mas em disco de
   rede pode travar), exceto no `closeEvent`, que continua síncrono para garantir a gravação.

### R4: Divisão do `MainWindow` (A1)
1. `ui/layout_controller.py:LayoutController(QObject)`: `fit_widths`, `set_panel_visible`,
   `set_left_mode`, splitters, restaurar/salvar estado (QSettings `layout/*`). Não conhece gráficos nem
   sync.
2. `ui/plot_workflow.py:PlotWorkflow(QObject)`:
   - detectar → escolher/mapear → carregar → sessão → render → exportar;
   - persistência `.plot`, readout do rodapé, indicador de ocupado (R2);
   - plotar arquivo específico (specs 9 e 12).

   Recebe `DetectionService`, `Workspace`, `ParamsPanel`, `FolderMemory`, config e `StatusBar` por
   injeção. Emite `plot_ready`, `message(text, level, timeout)` e `panel_requested(nome)`.
3. `ui/sync_coordinator.py:SyncCoordinator(QObject)`: `start_sync`, senha da sessão, conflitos,
   relatório final, rótulo do cluster/monitor. Base da spec 17.
4. `MainWindow` vira **raiz de composição**:
   - cria os widgets e os 3 controladores, monta menus e ações e liga os sinais;
   - fica com `rename_path`, `reload_config` e `closeEvent`, que orquestram os controladores (ex.:
     `rename_path` → `plot_workflow.flush(...)`, `close_tabs_under(...)`, `memory.rename`,
     `service.invalidate`).

   Meta: menos de 400 linhas.
5. Os controladores de `ui/` só **orquestram**: chamam o `core` (R5), abrem diálogos e atualizam
   widgets. Nenhuma regra de detecção, persistência, exportação ou sync fica neles.
6. Registro de ações: `MainWindow._actions: dict[str, QAction]`, com id estável (`plot.generate`,
   `plot.export`, `view.theme`, `files.refresh`…), atalho e texto. A spec 18 (atalhos e paleta) lê
   esse registro.
7. Testes novos instanciam `PlotWorkflow` e `SyncCoordinator` sem `MainWindow` (com `Workspace`,
   `ParamsPanel` e `StatusBar` reais ou falsos).

### R5: Backend sai de `ui/` (regra do `CLAUDE.md`)
1. Mover para `core/`, sem Qt e com testes próprios:
   | De | Para |
   |---|---|
   | `read_for_viewer`/`load_for_viewer` (`ui/widgets/workspace.py`) | `core/text_preview.py` (`TextPreview(text, banner, level, omitted_lines)`) |
   | `JOB_LOG`, `is_job_log`, `viewer_kind`, `status_label` (`ui/file_types.py`) | `core/file_kinds.py`. Na UI, `ui/file_types.py` fica só com `file_visual` (ícone + token de cor) e com o mapeamento nível → token |
   | `PlotSession` (`ui/plot_session.py`) | `core/plotting/session.py` |
   | escolha entre resultados plotáveis (`_plot_detected`) | `core/detection.py:plot_choice(results) -> Chosen \| Ambiguous \| NeedsMapping` |
   | montagem dos parâmetros (`_on_loaded`: padrão, `.plot`, legado, `apply_stored`) | `core/plotting/session.py:build_session(result, dataset, config, stored, memory)` |
   | plano de exportação (formatos, alvos existentes, próximo nome livre) | `core/plotting/export.py:plan_export(session) -> ExportPlan` |
   | pré-condições do sync (ligado?, pasta remota, senha necessária?) | `core/sync/request.py:prepare_sync(config, folder) -> SyncRequest \| SyncRefusal` |
   | casamento de `ui.hidden_dirs` (`fs_model.py`) | `core/paths.py:is_hidden(name, patterns)` |
2. Em `ui/` ficam só: a decisão de **como mostrar** (diálogo, rodapé, toast), widgets, modelos Qt e
   ligação de sinais.
3. Regra para as specs seguintes (16–20): toda lógica nova que não depende de widget nasce em `core/`.

### R6: Verificações automáticas das regras
1. `tests/test_architecture.py`:
   - **tamanho:** nenhum `.py` em `src/qe_studio` passa de 500 linhas. Uma lista de exceções explícita,
     com justificativa, começa **vazia**;
   - **camadas:** nenhum módulo de `core/` importa `qe_studio.ui` (verificação por AST dos imports);
   - **Qt no core:** só `core/sync/controller.py`, `core/sync/monitor.py` e `core/tasks.py` importam
     `PyQt6` (a lista do `CLAUDE.md`);
   - **leitura de arquivo na UI:** nenhum módulo de `ui/` chama `open(`, `read_text`, `read_bytes` ou
     `np.loadtxt`. Exceções: os recursos do próprio app (`ui/theme/manager.py`, que lê QSS, tokens e
     SVGs via `importlib.resources`).
2. O teste roda no CI (spec 7) como qualquer outro.

## Fora de escopo
- Exportação em **processo** separado (`multiprocessing`). Fica o lock; só se o lock se mostrar
  insuficiente (travamentos medidos), um processo entra numa spec futura.
- Mudanças de comportamento visíveis além do indicador de ocupado e da exportação não bloqueante.
- Reescrever o `monitor.py` (continua com threads daemon).

## Decisões assumidas (confirmar na revisão)
1. O helper fica em `core/tasks.py` (Qt dentro de `core/`, como o sync), para o `controller.py` também
   usá-lo. A alternativa seria `ui/workers.py` e manter o `controller` com o código próprio.
2. O lock global (R3.2) envolve também o render da tela. O render da tela adia (não bloqueia) enquanto
   exporta.
3. O `closeEvent` espera até 10 s pelas exportações (R3.6).
4. A meta de < 400 linhas é indicativa. O critério real é cada controlador ser testável sem a janela.
5. `PlotSession` vai para `core/` (R5.1) porque não usa Qt. O `ui/plot_session.py` é removido, e não
   mantido como reexportação.
6. A verificação de "leitura de arquivo na UI" (R6.1) é por padrão textual simples (AST de chamadas).
   Ela não pega tudo, mas barra o caso comum.

## Notas de implementação
- Cada passo deixa a suíte verde, e o R4 é mecânico depois que o R1 tirou o boilerplate e o R5 tirou o
  backend (ordem nas notas abaixo).
- Alterados:
  - `ui/services.py`, `ui/main_window.py`, `ui/widgets/workspace.py`, `ui/widgets/file_grid.py`;
  - `core/sync/controller.py`, `core/plotting/export.py`;
  - `ui/plot_session.py`, `ui/widgets/plot_view.py`, `ui/widgets/bars.py` (spinner no rodapé);
  - `CLAUDE.md` (seção "Threading rules": helper único, lock do matplotlib; seção "Architecture": os
    três controladores e os módulos movidos para `core/`);
  - `ui/file_types.py`, `ui/widgets/fs_model.py` (R5).
- Novos:
  - `core/tasks.py`, `core/plotting/mpl_lock.py`;
  - `ui/layout_controller.py`, `ui/plot_workflow.py`, `ui/sync_coordinator.py`;
  - `tests/test_tasks.py`, `tests/test_plot_workflow_unit.py`, `tests/test_sync_coordinator.py`;
  - `core/text_preview.py`, `core/file_kinds.py`, `core/plotting/session.py`, `core/sync/request.py`,
    `core/paths.py`;
  - `tests/test_architecture.py`.
- Removido: `ui/plot_session.py` (vai para `core/plotting/session.py`).
- Ordem sugerida atualizada: R1 → R2 → R5 → R3 → R4 → R6. Mover o backend para `core/` antes de dividir
  a janela deixa os controladores finos desde o início.
- Os testes atuais (`test_main_window.py`, `test_plot_workflow.py`, `test_sync_ui.py`) devem passar sem
  mudar o que verificam. Mudam só onde acessam atributos privados movidos.

## Critérios de aceite e testes
- [x] `grep -rn "QTimer.singleShot(0" src/qe_studio` só encontra `core/tasks.py` (e usos não ligados a
      workers, justificados em comentário).
- [x] `tests/test_tasks.py`:
  - o callback roda no thread da GUI;
  - uma tarefa cancelada não chama o callback;
  - uma nova tarefa do mesmo grupo e chave descarta a anterior;
  - `shutdown` espera as tarefas em execução;
  - fechar um `TextViewer` com leitura pendente não gera erro nem callback.
- [x] `grep -rn "OverrideCursor" src/qe_studio` não encontra nada. Depois de uma detecção cancelada, o
      cursor da aplicação é o padrão.
- [x] Exportar não bloqueia: durante uma exportação lenta (render falso com `sleep`), o loop de eventos
      processa um `QTimer` de 10 ms. O arquivo final existe, e não sobra `.tmp`.
- [x] Render na tela durante a exportação é adiado e acontece depois (sem deadlock, com timeout do
      teste).
- [x] `ui/main_window.py` com menos de 400 linhas. `PlotWorkflow` e `SyncCoordinator` testados sem a
      janela.
- [x] `tests/test_architecture.py` passa com a lista de exceções vazia: nenhum arquivo acima de 500
      linhas, `core/` sem import de `ui/`, Qt só nos 3 módulos permitidos e `ui/` sem leitura de arquivos
      de simulação.
- [x] `core/text_preview.py`, `core/file_kinds.py`, `core/plotting/session.py`, `core/sync/request.py` e
      `core/paths.py` são testados sem `QApplication`.
