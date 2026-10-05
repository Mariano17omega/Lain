# Spec 27-5: Fechamento da janela, diálogos abertos, erros inesperados e folga em `main_window.py`

| | |
|---|---|
| **Prioridade** | 27-5 |
| **Status** | Implementada |
| **Depende de** | spec 15 (controladores, `main_window.py`), spec 26 e 23 (diálogos não modais); 27-4 (cancelamento cooperativo, dependência fraca); 27-3 (tira `rename_path` de `main_window.py`) |
| **Usada por** | spec 31 (precisa de linhas livres em `main_window.py`) |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): reordena o encerramento do programa inteiro (sync, exports, stores, pools) com um orçamento de tempo, corrige um achado do relatório que a verificação mostrou ser parcialmente falso e extrai métodos de um arquivo central sem quebrar os testes que o usam. |

## Itens de origem (`specs/report-04-10-26.md`)

- **T1 (Médio):** fechar a janela pode ficar mais de 30 s travado e ainda sai com threads vivas.
- **B8 (Baixo, "provável"):** diálogos não modais perdem edições ao fechar a janela principal. **A verificação desta spec corrige o achado** (ver abaixo).
- **B5 (Baixo):** `excepthook` abre um modal por exceção.
- **Q2 (Médio):** `main_window.py` tem 496/500 linhas; qualquer feature nova quebra `test_architecture`.

## Situação atual

- **T1.** `ui/main_window.py:269-283` (`closeEvent`), na ordem, tudo na GUI thread e com a janela visível:
  1. `sync.shutdown()` → `controller.shutdown(5000)`: `waitForFinished(5000)`, depois `kill()` + `waitForFinished(1000)` (até 6 s); `monitor.stop()` não espera;
  2. `plot_workflow.shutdown()`: `_loads.cancel_all()` (não espera) e `exporter.shutdown()` → `tasks.wait(EXPORT_WAIT_MS = 10_000)` (até 10 s);
  3. `plot_settings.flush_now()` (`DRAIN_MS = 5000`);
  4. `plot_settings.shutdown()`: `_reads.shutdown(5000)` e `_writes.shutdown(5000)`, cada um com o seu prazo (até 10 s);
  5. `panel_layout.save()`, `navigation.shutdown()` (flush síncrono), `settings.sync()`;
  6. `service.shutdown(2000)`, `files.shutdown()` (1000 ms), `explorer.shutdown()`, `super().closeEvent`.
  Pior caso ≈ 34 s, mais `pool.waitForDone(5000)` em `ui/app.py:91` depois de `app.exec()`. Não há `hide()`; os retornos booleanos dos `shutdown`/`waitForDone` são **ignorados**,
  então o programa sai com threads do pool global vivas (`summarize`, `load_pdos`, `read_gnu`, `read_preview`, `diff_view`, `create_folder`, paleta) sem nenhum registro.
- **B8 (verificado).** `CalcCreateDialog` e `GridDialog` são filhos da janela principal com `WA_DeleteOnClose` (`calc_create_controller.py:120-127`, `grids_controller.py:76`). Um experimento
  offscreen (Qt 6.11) mostrou: o diálogo **recebe** `closeEvent`, mas **depois** de o `closeEvent` da janela principal terminar todo o seu encerramento, e um `ignore()` do diálogo **não**
  segura a saída (`exec()` retorna). Logo, `CalcCreateDialog` (`ask_discard`, `dialog.py:50`; `_may_close` `:205-213`, que também recusa fechar durante `_busy`) pergunta tarde demais; o que
  o usuário digitou já foi perdido quando ele responde "Não". **`GridDialog` não tem** `ask_discard`, `closeEvent` nem controle de edição pendente (só pergunta ao apagar `grid_dialog.py:180`
  e ao substituir `:197`): a parte do relatório sobre ele é falsa. Cada controlador guarda `self.dialog` (limpo em `finished`/`destroyed`); `HelpController.dialog` idem; não há registro central.
- **B5.** `ui/app.py:38-51` (`install_excepthook`, instalado em `main` na `:65`, antes da `QApplication`): faz `log.error("erro inesperado", exc_info=…)` e, se há `QApplication`, abre
  `QMessageBox.critical(None, …)` (modal, com loop aninhado) com "Tipo: valor" e o caminho do log. Sem deduplicação, sem trava de reentrada, sem toast. **Não há testes** (`grep excepthook tests`
  não acha nada). O `Toast` vive na janela (`window.toast`).
- **Q2.** `ui/main_window.py` (496 linhas; `tests/test_architecture.py:14` `LIMIT = 500`, `SIZE_EXCEPTIONS` vazio). Métodos e início: `__init__` 72, `_build` 124, `_build_controllers` 161, `_connect` 204
  (49 linhas), `_restore_folder` 253-263, `closeEvent` 269-283, `on_folder_selected` 294, `rename_path` 371-407 (37 linhas; a spec 27-3 a extrai), `reload_config` 447, `_apply_loaded` 468,
  `start_sync` 485, `start_project_sync` 489, `_on_synced` 493-496. Controladores têm `for_window(window)` (`Help`, `Palette`, `FirstRun`, `Derive`, `CalcCreate`, `Grids`, `Focus`);
  `LayoutController` e `PlotWorkflow` são montados em `_build_controllers`.

## Requisitos

### R1: Fechamento rápido e com prazo (T1)
1. **`ui/shutdown.py:ShutdownSequence`** (ou função `shutdown(window)`): recebe os passos como lista de `(nome, callable(prazo_ms) -> bool)` registrados pelo `MainWindow` e um
   **orçamento total** (`TOTAL_MS = 8000`, constante nomeada). Ordem:
   1. `window.hide()` (o usuário não vê mais nada travado);
   2. cancelar o que é cancelável (`_loads.cancel_all()`, `summary`/`text_viewer`, `service`, grids; a spec 27-4 faz as tarefas obedecerem);
   3. sync/push: `shutdown(min(2000, restante))` (`kill` depois do prazo);
   4. exportações em curso: esperam até `min(EXPORT_WAIT_MS, restante)` (**não** são abortadas antes disso: integridade das figuras);
   5. **uma** drenagem de `.plot` (`flush_now`, depois `shutdown` dos pools de leitura e escrita com o **prazo restante**, não 5 s + 5 s + 5 s cada);
   6. stores (`navigation.flush`, layout, `QSettings.sync()`) — sempre rodam, mesmo com o orçamento esgotado (são rápidos e é o estado do usuário);
   7. `service.shutdown`, `files.shutdown`, `explorer.shutdown`.
2. Cada passo devolve `True` se terminou no prazo. Os que estouram viram `log.warning("encerramento: <passo> não terminou em <ms> ms")`; o resumo (`ok`/estouros) vai para o log em `info`.
3. `ui/app.py:main`: o retorno de `pool.waitForDone(...)` passa a ser usado. Se ainda houver tarefas depois do prazo, `log.error` (lista os passos pendentes) e, **depois de o estado ter sido
   gravado**, `os._exit(0)` em vez de deixar o interpretador finalizar com threads do Qt rodando Python (crash ou espera sem fim).
4. **Meta:** com tudo ocioso, o processo sai em < 1 s; com loaders cancelados (27-4), < 2 s; pior caso (exportação grande) ≤ `TOTAL_MS` + o tempo da exportação. Testes com os `shutdown` dos
   controladores substituídos por duplos que dormem: a sequência respeita o orçamento, registra o passo lento, ainda roda os stores e devolve; `closeEvent` esconde a janela antes de qualquer espera.

### R2: Diálogos antes de fechar (B8)
1. `CalcCreateController.close_dialog() -> bool` e `GridsController.close_dialog() -> bool` (e `HelpController` para o de atalhos, que não tem estado): fecham o diálogo se existir e devolvem `True`
   se ele realmente fechou (`CalcCreateDialog._may_close` perguntou e o usuário disse "Sim", ou não havia edição); `False` se o usuário respondeu "Não" ou a criação está em andamento (`_busy`).
2. `closeEvent` chama isso **antes** de qualquer encerramento: se algum devolver `False`, `event.ignore()` e nada mais acontece (a janela segue aberta, o diálogo à frente).
3. `GridDialog` não ganha pergunta nova (não tem estado que se perca: "Gerar" salva; cancelar descarta o rascunho por desenho). A decisão fica registrada em "Decisões assumidas".
4. Testes: com `dialog.ask_discard` patchado como nos testes existentes (`test_calc_create_ui.py:19`, `test_calc_create_dialog.py:67`): "Não" mantém a janela principal aberta (`window.isVisible()`) e
   o diálogo vivo; "Sim" fecha os dois; sem edições fecha direto; durante a criação (`_busy`) a janela principal não fecha.

### R3: `excepthook` sem enxurrada de modais (B5)
1. `install_excepthook` ganha estado: chave de deduplicação `(tipo, str(valor), arquivo:linha do último frame)`; a mesma chave dentro de 10 s só incrementa um contador; trava de reentrada (uma
   exceção levantada **enquanto** a anterior é tratada vai só para o log).
2. Apresentação: se há `window.toast`, um toast `error` "Erro inesperado: <tipo>: <valor> (ver o log)" com "Detalhes" = traceback e caminho do log; senão (antes da janela existir) a
   `QMessageBox.critical` de hoje, **uma vez**. Toda ocorrência vai para o log, com " (xN)" quando repetida.
3. A janela se registra: `app.set_excepthook_window(window)` (função de módulo; o hook guarda uma referência fraca).
4. `tests/test_excepthook.py` (novo): duas chamadas iguais seguidas → um toast e contador 2; exceção diferente → outro toast; passados 10 s (relógio injetado) → mostra de novo; reentrada não abre
   nada; sem janela → uma caixa (patch de `QMessageBox.critical`).

### R4: Folga em `main_window.py` (Q2)
1. Extrações (nenhuma muda comportamento; os atalhos de `ACTIONS` e a fachada que os testes/`scripts/screenshot.py` usam continuam):
   - `closeEvent` → `ui/shutdown.py` (R1); `MainWindow.closeEvent` fica com ≈ 8 linhas (diálogos, `ShutdownSequence.run()`, `super().closeEvent`);
   - `rename_path` → `RenameController` (**spec 27-3**; se esta spec vier antes, ela mesma faz a extração descrita lá);
   - `_restore_folder` (`:253-263`) → `NavigationController.restore(last_folder)`;
   - `start_sync`, `start_project_sync`, `_on_synced` (`:485-496`) → `SyncCoordinator` (`start_project`, `on_synced`), apontados pelos `slot` de `ACTIONS` (`sync.start`, `sync.project`).
2. Meta: `main_window.py` ≤ **450 linhas**. `tests/test_architecture.py` troca o limite de 500 por 450 **só para `ui/main_window.py`** (entrada `PER_FILE_LIMIT = {"ui/main_window.py": 450}`), de modo que a
   folga não seja gasta de volta sem querer; os demais arquivos continuam em 500.
3. Nenhuma extração pode introduzir `open(`/`read_text` em `ui/`.

## Fora de escopo
- Cancelamento cooperativo dos loaders (27-4), `rename_path` (27-3) e a perda de edições do `GridDialog` (não existe).
- Reescrever o `ConnectionMonitor` ou o ciclo de vida do `QThreadPool` global.
- Um relatório de falhas para o usuário (só log e toast).

## Decisões assumidas (confirmar na revisão)
1. `TOTAL_MS = 8000` e `os._exit(0)` só depois de gravar tudo e logar: a alternativa (esperar para sempre ou finalizar com threads vivas) é pior; o valor é uma constante nomeada.
2. As exportações de figuras **não** são abortadas antes do seu prazo próprio (10 s): perder meio arquivo é pior do que esperar com a janela escondida.
3. `GridDialog` não pergunta nada ao fechar com a janela principal (não há edição não salva a proteger); o relatório se enganou aqui.
4. O toast substitui o modal do `excepthook` quando há janela; o modal só existe antes da janela (erro de inicialização).
5. O limite de 450 linhas só vale para `main_window.py`; é uma regra de manutenção para as specs 31+ (ajustável).

## Como foi implementado (desvios do texto acima)
- O passo das exportações espera o `EXPORT_WAIT_MS` inteiro e esse tempo **não** conta no `TOTAL_MS` (a decisão 2 vale mais que o `min(…, restante)` do R1.1.4); `ShutdownSequence` nunca pula um passo: sem orçamento ele recebe 0 ms e faz só a parte que não espera, então os stores são sempre gravados.
- `panel_layout.save()` roda antes do `hide()` (a geometria é lida com a janela ainda na tela); o resto dos stores fica depois, como no R1.
- `close_dialogs` pergunta primeiro ao diálogo que pode recusar (Criar cálculo); só se ele concordar os de grids e atalhos fecham (um "Não" não deixa o diálogo de grids já perdido).
- O `Toast` não tinha o nível `error` (um nível desconhecido virava `info`): ganhou `LEVELS["error"]` e a regra no `toast.qss`.
- `main_window.py` já tinha 463 linhas (a 27-3 tirou `rename_path`): ficou com 445. `refresh_folder` na janela é o que o `SyncCoordinator` recebe como `refresh`; `NavigationController.restore()` usa só o explorador (`current_folder()`), não `files.folder`.
- `app.finish(code, pool, lock, report, exit_now=os._exit)` é o fim de `main` (testável); `POOL_WAIT_MS` = 2 s. O `excepthook` vive em `ui/excepthook.py` (`ExceptionReporter`); `ui/app.py` o reexporta.

## Notas de implementação
- Novos: `ui/shutdown.py`, `tests/test_shutdown.py`, `tests/test_excepthook.py`.
- Alterados: `ui/main_window.py`, `ui/app.py`, `ui/calc_create_controller.py`, `ui/grids_controller.py`, `ui/help_controller.py`, `ui/navigation_controller.py`, `ui/sync_coordinator.py`,
  `ui/actions.py` (`slot`s), `ui/plot_workflow.py`/`ui/plot_settings.py`/`ui/services.py` (assinaturas de `shutdown` com prazo restante e retorno `bool`), `tests/test_architecture.py`.
- Os `shutdown` existentes passam a receber o prazo e a devolver `bool` (hoje devolvem `None` ou ignoram); chamadores antigos (`tests/`) seguem funcionando com o padrão atual.
- `CLAUDE.md`: seções "Main window and controllers" (nova lista de controladores) e "Threading rules" (orçamento de encerramento).

## Critérios de aceite e testes
- [ ] `closeEvent` esconde a janela primeiro e respeita o orçamento; etapa lenta registrada em log; stores gravados mesmo com estouro.
- [ ] `app.main` usa o retorno de `waitForDone`; com tarefa pendente simulada, loga e sai por `os._exit` (patch) depois de gravar.
- [ ] Diálogo do "Criar cálculo" com edição: "Não" mantém a janela principal; "Sim" fecha tudo; criação em andamento impede o fechamento.
- [ ] `excepthook`: deduplicação, reentrada e toast cobertos; log com contagem.
- [ ] `main_window.py` ≤ 450 linhas; `test_architecture.py` com o limite por arquivo; `ui/` sem `open(`/`read_text`.
- [ ] Atalhos de `ACTIONS` (sync, projeto inteiro, renomear) e a fachada usada por `scripts/screenshot.py` continuam funcionando.
- [ ] `ruff`, `pyright`, suíte `-m "not realdata and not perf"` verdes.
