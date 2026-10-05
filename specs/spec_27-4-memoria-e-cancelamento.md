# Spec 27-4: Memória dos datasets e cancelamento dos loaders

| | |
|---|---|
| **Prioridade** | 27-4 |
| **Status** | Proposta |
| **Depende de** | spec 14 (desempenho), spec 15 (`core/tasks.py`) |
| **Usada por** | spec 27-5 (o fechamento só fica rápido de verdade com loaders canceláveis) |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda o contrato de `core/tasks.py` (o que uma tarefa enxerga do cancelamento), toca parsers de vários módulos sem quebrar suas regras de arquitetura (Qt-free) e exige medir memória de forma confiável. |

## Itens de origem (`specs/report-04-10-26.md`)

- **M1 (Médio):** cache de datasets limitado por quantidade (8), não por bytes; as entradas sobrevivem ao fechamento das abas; o pico dos parsers é grande.
- **T3 (Baixo):** loaders longos não cancelam (`TaskHandle.cancel()` é só uma flag que a função não vê).

## Situação atual

- **Cache** (`core/calculations/base.py:429-453`, `load_cached`): chave `(kind, sorted((role, tuple(_stamp(p)))))` com `_stamp(p) = (str(path), mtime_ns, size)` (`:456`),
  `OrderedDict` LRU, `LOAD_CACHE_SIZE = 8`, remove a entrada mais antiga enquanto `len > 8`. Nada mede bytes. A carga roda **fora do lock** (`:443`): duas threads que perdem na
  mesma chave carregam as duas vezes (pico dobrado). Nada limpa `_LOAD_CACHE`: `DetectionService.invalidate` (`ui/services.py:95`) só mexe em resultados e sniffs; fechar a aba
  (`PlotWorkflow._on_tab_closing`, `plot_workflow.py:354`) só grava e descarta ajustes. `bands_dos` carrega as duas metades por `load_cached` (`bands_dos/data.py:31-32`):
  um par ocupa até 3 vagas. Testes: `test_plotting.py:248` (`test_load_cache_reuses_dataset`), `test_busy_indicator.py:73` (monkeypatch de `load_cached`).
- **Datasets:** `BandsDataset` (`bands/data.py:86`: `bands: BandData(x, energies (nb,nk))`, `bands_down`), `PdosDataset` (`pdos/data.py:17`: `data: PdosData` com `energy`, `series`
  de `Channel(up, down)` e `total`), `BandsDosDataset` (`bands_dos/data.py:17`: um de cada), `ScfDataset` e `RelaxDataset` (listas pequenas de dataclasses congeladas). `nbytes`
  e `getsizeof` não aparecem em `src/`.
- **Parsers** (medidos com `tracemalloc` no relatório): `read_gnu` (`core/qe/bands_x.py:33`) usa `np.loadtxt(io.StringIO(text))`, `np.split`, `np.allclose` por bloco e `np.array([b[:,1] …])`
  (cópia): ≈ 5× o texto (≈ 19,8 MB de pico para 4 MB), ≈ 7× contando o `read_text` do chamador (`bands/data.py:135,174`); um `.gnu` de 60 MB passaria de 400 MB (extrapolado). `read_filband`
  (`:135-148`): `findall` de `str` → lista de `float` → `np.array`: ≈ 9× (18,8 MB para 2,2 MB). `gnu_shape` (`:71`) já lê em blocos de 4 MB (`GNU_CHUNK_BYTES`) e **não** é problema.
  `load_pdos` (`core/qe/projwfc.py:188`): um `np.loadtxt(path, skiprows=1, usecols=…)` por arquivo, em série (pouca memória, mas tempo proporcional ao número de arquivos).
- **Cancelamento** (`core/tasks.py`): `TaskHandle.cancel()` (`:83`) só liga `_cancelled`; `_Runnable.run` (`:179`) chama `self.fn(*args, **kwargs)` sem o handle (criado em `_start`, `:210`); o
  cancelamento só vale antes de a tarefa começar e na entrega (`_deliver`, `:130`). `TaskGroup.submit` (`:253`) cancela a anterior da chave; `cancel_all`/`shutdown` só ligam flags e esperam.
  Pontos de submissão: `PlotWorkflow._load` (`plot_workflow.py:267-270`: `load_plot` → `module.load_cached` → `load`), `SummaryView.refresh` (`summary_view.py:109`: `run_task(summarize, …)`),
  `TextViewer` (`text_viewer.py:161`: `run_task(read_preview, path, full, …)`), `diff_view`, paleta, `create_folder`. Fechar a aba **não** cancela a carga pendente: a aba abre quando ela termina.
- `core/qe/*` é Qt-free e não pode importar `core/tasks.py` (que usa Qt). `tests/test_tasks.py:63,75,89,104` cobre cancelamento antes/depois de começar, substituição e `shutdown`.

## Requisitos

### R1: Cancelamento cooperativo
1. **`core/cancel.py`** (Qt-free, entra em `QT_FREE` de `test_architecture.py`): `class Cancelled(Exception)`; `check() -> None` que levanta `Cancelled` se a tarefa corrente foi cancelada e
   não faz nada fora de uma tarefa; `is_cancelled() -> bool`. O estado é um `threading.local` posto por `core/tasks.py` (`_Runnable.run` registra o `TaskHandle` na thread e o limpa no `finally`).
2. `_Runnable.run` trata `Cancelled` como cancelamento: não chama `on_error`, não loga como falha, não entrega resultado. Tarefas sem `check()` não mudam de comportamento.
3. **Onde consultar** (sempre em intervalos curtos, nunca por linha):
   - `summarize_lines` / `_observe` (`core/qe/summary/__init__.py:44-61`) a cada ~10 000 linhas; `parse_relax` (`core/qe/relax.py:81`) idem;
   - `load_pdos` entre arquivos; `read_gnu` e `read_filband` entre fases (leitura, parse, montagem); `read_preview(full=True)` entre blocos de leitura;
   - `load_cached` antes de começar e depois de `load` (não guarda no cache o resultado de uma tarefa cancelada).
4. **Fechar a aba cancela a carga pendente:** `PlotWorkflow._on_tab_closing` cancela a chave em `_loads` e tira `busy` e `_loading`; `SummaryView` e `TextViewer` já cancelam ao fechar
   (confirmar no teste).
5. Testes (`test_tasks.py` e um por loader): tarefa que chama `check()` num laço e é cancelada termina em ≤ um intervalo sem `on_error`; fora de uma tarefa `check()` não faz nada; `Cancelled`
   levantada dentro de `summarize`/`load_pdos` com a flag ligada não chama `on_done` nem `on_error`; fechar a aba durante a carga (loader lento por monkeypatch) não abre a aba depois.

### R2: Cache por bytes (M1)
1. **`core/sizing.py:nbytes_of(obj) -> int`** (Qt-free): soma `ndarray.nbytes` percorrendo dataclasses (`dataclasses.fields`), tuplas, listas, dicionários e `Optional`, com profundidade
   limitada e sem seguir ciclos (conjunto de `id`s visitados); outros objetos contam 0. Genérico: nenhum dataset precisa de código próprio.
2. `load_cached`: além das 8 entradas, `LOAD_CACHE_BYTES = 256 * 1024 * 1024` (constante nomeada). Depois de carregar, `nbytes_of(dataset)`; entradas são expulsas (as mais antigas
   primeiro) até caber; um dataset **maior que o orçamento inteiro** é devolvido mas não guardado.
3. **Carga única por chave:** uma segunda chamada com a mesma chave enquanto a primeira carrega espera pela mesma carga (um `threading.Event`/`Future` por chave em andamento) em vez de
   carregar de novo.
4. **Esvaziamento:** `drop_cached(under: Path | None = None, *, min_bytes: int = 0)` remove as entradas cujos arquivos (as chaves guardam os caminhos) estão sob `under` (todas se `None`) e têm pelo
   menos `min_bytes`. Chamado por `DetectionService.invalidate(folder)` (F5 e sync; sem pasta = todas) e por `PlotWorkflow._on_tab_closing` com `min_bytes = 4 MB` (datasets pequenos
   ficam: recarregar custa milissegundos; os grandes são o problema).
5. Testes: `nbytes_of` de `BandData`, `PdosData` (com spin) e `BandsDosDataset` bate com a soma dos arrays; cache com três datasets sintéticos de 100 MB e orçamento de 256 MB guarda só os
   dois mais novos; dataset de 300 MB não é guardado; duas threads pedindo a mesma chave chamam `load` uma vez; `drop_cached(under=pasta)` remove só as entradas da pasta; `invalidate` esvazia.

### R3: Picos dos parsers (M1)
1. **`read_gnu`:** aceita `Path` (ou continua aceitando texto em `read_gnu_text` para quem já tem o texto) e usa `np.loadtxt(path)` (leitor em C por blocos), sem `StringIO` nem cópia do texto;
   `bands/data.py:135,174` passam o caminho. Mantém a validação de blocos (`np.allclose` entre abscissas) e a forma de saída.
2. **`read_filband`:** troca `findall` → lista de `str` → lista de `float` por `np.fromiter((float(m.group()) for m in _FLOATS.finditer(text)), dtype=float)` (ou `count` quando o cabeçalho dá
   `nbnd·nks`): sem listas intermediárias. A regex continua (números colados em Fortran, `-116.798-116.798`).
3. **Critério de memória** (`tracemalloc`, arquivos sintéticos de `tests/synthetic.py`: `.gnu` de ~4 MB e filband de ~2 MB): pico de `read_gnu` ≤ 2,5× o tamanho do arquivo; de
   `read_filband` ≤ 3×; resultados idênticos aos de antes (comparação elemento a elemento com os caminhos antigos, mantidos só nos testes).
4. `gnu_shape`, `load_pdos` e o sniff não mudam, a não ser pelo `check()` de R1.

## Fora de escopo
- Cache em disco, `memmap` ou carregamento sob demanda de partes do dataset.
- Streaming do `bands_dos`/`grid` (os datasets já usam `load_cached`).
- Cancelar o sync (já tem `kill`) ou o export (já espera por `shutdown`).
- O fechamento da janela em si: spec 27-5 (aproveita o `cancel_all` com tokens).

## Decisões assumidas (confirmar na revisão)
1. Orçamento de **256 MB** (constante nomeada, ajustável); a contagem de 8 entradas continua como segundo limite.
2. Fechar a aba só esvazia datasets ≥ 4 MB; pequenos permanecem para reabrir instantâneo. O relatório sugere esvaziar sempre; este limiar evita recarregar à toa.
3. `check()` é um *thread-local* (e não um argumento novo em toda função): assim os parsers de `core/qe/` não dependem de `core/tasks.py` e as assinaturas públicas não mudam.
4. `read_gnu` por caminho muda a assinatura de um parser público: quem passava texto usa `read_gnu_text` (um alias fino sobre o mesmo núcleo).

## Notas de implementação
- Novos: `core/cancel.py`, `core/sizing.py`; ambos na lista `QT_FREE` de `tests/test_architecture.py`.
- Alterados: `core/tasks.py` (`_Runnable.run`), `core/calculations/base.py`, `core/qe/bands_x.py`, `core/qe/projwfc.py`, `core/qe/relax.py`, `core/qe/summary/__init__.py`,
  `core/text_preview.py`, `core/calculations/bands/data.py`, `ui/services.py`, `ui/plot_workflow.py`, `tests/test_tasks.py`, `tests/test_plotting.py`, `tests/test_bands_*.py`.
- `tests/synthetic.py` já tem `make_gnu`; um gerador de filband sintético entra ali (sempre em `tmp_path`, nunca em `tests/fixtures/`).
- Os testes de memória usam `tracemalloc` (rápidos, tamanhos de poucos MB) e **não** são `perf`.

## Critérios de aceite e testes
- [ ] `core/cancel.py` e `core/sizing.py` sem PyQt6; `core/` sem `ui`; arquivos < 500 linhas.
- [ ] Tarefa cancelada no meio termina sem `on_done`/`on_error`; sem tarefa, `check()` é inofensivo.
- [ ] Loaders (`summarize`, `parse_relax`, `load_pdos`, `read_gnu`, `read_filband`, `read_preview(full)`) respeitam `check()`.
- [ ] Fechar a aba durante a carga não abre a aba depois; fechar a aba esvazia datasets ≥ 4 MB.
- [ ] Cache: respeita o orçamento de bytes; dataset gigante não é guardado; carga única por chave; `invalidate` esvazia.
- [ ] Picos: `read_gnu` ≤ 2,5× e `read_filband` ≤ 3× o arquivo; saídas idênticas às antigas.
- [ ] `ruff`, `pyright` sem regressão; suíte `-m "not realdata and not perf"` verde.
