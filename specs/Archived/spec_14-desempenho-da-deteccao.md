# Spec 14: Desempenho da detecção e memória de pastas

| | |
|---|---|
| **Prioridade** | 14 |
| **Status** | Implementada. Desvios: a fórmula das bandas vem das linhas `tau(` do cabeçalho da saída SCF (`core/qe/structure.py`, o mesmo código do relax e do resumo), sem ASE e sem memo, em vez do `read_structure` memoizado (decisão de 03/10/2026: o campo não aparece na interface, e o ASE levava 371 ms numa SCF de 15 MB); vale também acima de 16 MB, e o `vc-relax.out` da fixture, que o ASE não lia, ganha fórmula; `parse_pw_output(head, tail=None)`: sem cauda, o texto é o arquivo inteiro e as chamadas antigas não mudam; a regex única de Fermi casa as frases como o pw.x as escreve (como o scanner do resumo), sem `re.I`, que a deixava 6× mais lenta (331 contra 54 ms em 15 MB); o R3 também guarda o nome relativo de cada arquivo da listagem e testa o conteúdo antes dos globs (era o custo da detecção a quente); o `FolderMemory` foi para `core/folder_memory.py`, o JSON é `{"version": 2, "folders": {…}}` (uma pasta chamada `version` colidiria com uma chave solta), a raiz muda por `set_root` (sem recriar a memória, que o serviço e os testes injetam), um arquivo fora da pasta mas dentro da raiz fica como `../outra/arquivo`, a detecção lê os mapeamentos da pasta numa consulta só (`mappings`), um JSON que não é objeto ou com `version` desconhecida também vira cópia `.corrompido-*`, e o aviso de corrompido tem prioridade sobre os do config na barra de status; o ganho do `.gnu` não é velocidade (o `loadtxt` já era C), e sim o fim do limite de 64 MB e memória limitada a um bloco de 4 MB |
| **Depende de** | spec 7 (job `perf` no CI) |
| **Usada por** | spec 16 (favoritos/recentes usam a mesma chave relativa de A5) |
| **Esforço** | M |

## Itens de origem (`report.md` §2)

> **O1** `.gnu` é lido e parseado por completo **no sniff** (até 64 MB) e de novo no `load`.
> **O2** `invalidate()` sem argumento limpa **todo** o `SniffCache` (`services.py:108-111`), mas as entradas já validam por (mtime, size).
> **O3** `match()` sniffa todos os arquivos **por módulo** (×5).
> **O4** ASE (pesado) importado no start por `sniff.py:18` → `pw_input.py:16`.
> **O5** `parse_pw_output` varre até 16 MB com `finditer` por padrão (×4 Fermi, `_last`).
> **O8** Sem teste de latência da **detecção** (só plot tem `-m perf`).
> **A5.** `FolderMemory` guarda caminho absoluto resolvido (`detection.py:36`): mover a pasta do projeto ou usar outra máquina perde mapeamentos manuais e rótulos. → chave relativa a `local_root`.
>
> Riscos (§6): O2 assume que (mtime, size) basta […]. Claims de custo (O4, O5) são **hipóteses não medidas**; cada uma deve ganhar um teste `-m perf` (O8) antes da mudança.

## Situação atual

- **O8:** os testes `perf` cobrem só o plot:
  - `tests/test_plotting.py:236-256`: uma pasta, 100 bandas;
  - `tests/test_relax.py:278-287`: relax com 100 passos.

  Nada mede um projeto grande, saídas enormes, o F5 ou o tempo de início.
- **O4 (medido):** `qe_studio.core.sniff` leva 324 ms para importar, 263 ms deles do `ase.io.espresso`
  (que puxa `ase.spacegroup`, `ase.dft.kpoints` e scipy). A cadeia é `app.py:83` → `main_window` →
  `core.calculations` → `bands.py` → `sniff` → `pw_input.py:16`, e roda antes do `window.show()`.
  `pw_output.read_structure` já importa o ASE só quando é usado (l.151).
- **O3:**
  - `CalculationModule.match` (`core/calculations/base.py:177`) faz
    `sniffs = {path: sniff(path) for path in listing.files}` **em cada módulo**;
  - `detect_folder` (`core/detection.py:100-123`) chama os 3 módulos principais e, se nenhum casa, os
    *fallback*. São de 3N a 5N consultas, cada uma com `stat()` e lock;
  - `infer_from_neighbours` (`base.py:236-261`) sniffa a pasta pai e as irmãs `*scf*`;
  - o explorador pede detecção de toda pasta que pinta (`ui/widgets/explorer.py:61`).
- **O2:** `DetectionService.invalidate()` sem argumento (`ui/services.py:102-114`) apaga `_results`,
  chama `self.sniff_cache.clear()` (l.109) e repede as pastas pendentes. Quem chama: `refresh` (F5,
  `main_window.py:498`) e `reload_config`. As entradas do `SniffCache` já são validadas por
  `(st_mtime_ns, st_size)` (`core/sniff.py:187-203`), então o `clear()` só obriga a reler o que continua
  válido.
- **O1:**
  - `_sniff_uncached` (`core/sniff.py:129-134`) lê o `.gnu` inteiro (até `GNU_READ_LIMIT` = 64 MB) e
    roda `np.loadtxt` só para guardar `shape`;
  - um `.gnu` acima de 64 MB cai em `UNKNOWN` e **nunca é detectado**, sem aviso;
  - `bands.load` relê e reprocessa o mesmo arquivo (`bands.py:337-339`).
- **Cache errado nos `load`:**
  - `bands.py` e `pdos.py` importam o `sniff` padrão do módulo (`bands.py:19`, usado em l.310 e 366;
    `pdos.py:263`), e não o `SniffCache` do serviço. A saída SCF é processada de novo;
  - `bands.load` ainda lê a SCF inteira pelo ASE (`read_structure`, l.328);
  - `BandsModule.finalize` roda `read_bands_input` (ASE) a cada detecção sem `bands_out`
    (l.203-207), sem cache.
- **O5:**
  - o sniff chama `parse_pw_output` sobre `_read_text(path, size, 16 MiB, tail=1 MiB)`
    (`sniff.py:152`): o arquivo inteiro até 16 MB, senão 8 KB do início + 1 MB do fim;
  - `parse_pw_output` (`pw_output.py:97-146`) faz 4 `finditer` completos (padrões de Fermi, sem
    diferenciar maiúsculas), 5 `search` e cerca de 14 buscas `in`;
  - acima de 16 MB, campos que aparecem só no começo (k-pontos, elétrons, bandas, alat) precisam estar
    nos primeiros 8 KB, o que falha em sistemas grandes (cabeçalho longo de pseudopotenciais).
- **A5:**
  - `FolderMemory` (`core/detection.py:16-97`) usa como chave `str(Path(folder).resolve())` (l.36, 43,
    60), e os arquivos dos mapeamentos ficam como foram dados (l.50);
  - é guardado em `$XDG_DATA_HOME/qe-studio/folders.json` (`core/appdirs.py:12-17`), com escrita
    atômica;
  - um JSON corrompido vira `{}` em silêncio (l.31-32), e o próximo `save` **sobrescreve** o arquivo:
    perda de dados.

## Requisitos

### R1: Medir primeiro (O8)
1. `tests/test_perf_detection.py` (`@pytest.mark.perf`), com geradores sintéticos em `tests/synthetic.py`:
   - **projeto grande:** ~500 pastas em 3 níveis, com mistura de bandas/PDOS/relax/SCF copiados das
     fixtures (`copy_fixture`) e arquivos de texto comuns. Mede `detect_folder` em todas as pastas, a
     frio e a quente;
   - **saída enorme:** um pw.x relax sintético de ~200 MB, gerado em `tmp_path` e repetindo passos da
     `si.rel.out`. Mede `sniff` a frio;
   - **F5:** mede `DetectionService.invalidate()` + nova detecção de 50 pastas já vistas;
   - **import:** `python -X importtime -c "import qe_studio.ui.main_window"` em subprocesso. Mede o tempo
     total e falha se `ase` aparecer na lista.
2. Linha de base: os números atuais (máquina do desenvolvedor) ficam registrados nas notas desta spec
   antes de qualquer otimização, e os limites dos testes são definidos a partir deles (ex.: 50 % da
   linha de base, ou orçamentos absolutos documentados).
3. Cada otimização (R2–R6) só é feita se o teste correspondente mostrar ganho. Os números depois de cada
   uma também vão para as notas.

### R2: Import tardio do ASE (O4)
1. `pw_input.py`: `from ase.io.espresso import read_fortran_namelist` passa para dentro de `parse_input`.
2. Nenhum módulo carregado até o `window.show()` importa `ase` (o teste de import do R1.1 garante).

### R3: Sniffs uma vez por pasta (O3)
1. `detect_folder` calcula `sniffs = {p: sniff(p) for p in listing.files}` uma vez e passa para
   `module.match(listing, sniffs, sniff, forced=…)`. A assinatura de `match` muda, e
   `manual_result`/`_Manual` seguem a mesma regra.
2. `infer_from_neighbours` guarda os sniffs das pastas vizinhas num dicionário da própria chamada de
   `detect_folder`, para não sniffar a mesma pasta duas vezes quando bandas e PDOS procuram o SCF.

### R4: F5 sem jogar fora o cache válido (O2)
1. `DetectionService.invalidate()` sem argumento descarta `_results` e repede as pendentes, mas **não**
   chama `sniff_cache.clear()`. Passa a chamar `sniff_cache.prune()`: remove as entradas cujo arquivo
   não existe mais (um `stat` cada).
2. Risco registrado (`report.md` §6): um arquivo reescrito com o mesmo tamanho e o mesmo `mtime_ns` não
   seria percebido. Com `mtime_ns` e rsync `-t`, isso é desprezível. A opção de config
   `ui.paranoid_refresh: false` (padrão) restaura o `clear()` total quando `true`.

### R5: `.gnu` e saídas grandes (O1, O5)
1. O sniff do `.gnu` não usa `loadtxt`. Lê em streaming, conta as linhas numéricas de duas colunas e os
   reinícios de `x` (blocos), e devolve `shape = (blocos, linhas/blocos)`. Valida só as primeiras e as
   últimas linhas (2 floats). Sem limite de tamanho: o corte de 64 MB some, e o arquivo grande passa a
   ser detectado.
2. `parse_pw_output` passa a receber **cabeça** e **cauda** separadas (`parse_pw_output(head, tail)`):
   - campos "primeira ocorrência" (versão, k-pontos, elétrons, bandas, alat, spin, calculation) vêm da
     cabeça, que passa de 8 KB para 256 KB (`PW_HEAD_BYTES`);
   - campos "última ocorrência" (Fermi, convergência, `JOB DONE`, marcadores de relax) vêm da cauda
     (1 MB), com uma única regex combinada para os 4 padrões de Fermi (alternância com grupos nomeados)
     e `rfind` para as frases fixas;
   - arquivos ≤ 16 MB continuam lidos inteiros (cabeça = cauda = texto), mas com a regex única.
3. Regressão: para todas as fixtures, o `PwOutput` antes e depois é **idêntico** (teste que compara os
   dataclasses).

### R6: `load` usa o cache do serviço
1. `CalculationModule.load(result, sniff)`: o `sniff` vem do `_LoadTask` (o `SniffCache` do serviço), e
   não do `sniff` padrão. `bands.py:19` e `pdos.py:263` deixam de importar o `sniff` global.
2. `read_bands_input` é memoizado por `(path, mtime_ns, size)` (`functools.lru_cache` sobre o carimbo,
   tamanho 256).
3. `read_structure` (ASE) em `bands.load` só roda para obter a fórmula e é memoizado pelo carimbo do
   arquivo. Saídas > 16 MB pulam a fórmula ("—").

### R7: `FolderMemory` portátil e seguro (A5)
1. Chave = caminho **relativo a `paths.local_root`** (POSIX, `"."` para a raiz). Pastas fora do
   `local_root` (raro, só por config) continuam com o caminho absoluto, prefixado por `abs:`.
2. Os arquivos dentro dos mapeamentos também ficam relativos à pasta da simulação.
3. Migração automática na primeira leitura: chaves absolutas que estão dentro de `local_root` viram
   relativas, e o arquivo é regravado. Um campo `version: 2` no JSON evita migrar de novo.
4. JSON ilegível: o arquivo é renomeado para `folders.json.corrompido-<data>`, um aviso é registrado no
   log e na barra de status ("folders.json estava corrompido; cópia salva em …"), e a memória começa
   vazia. Nunca sobrescreve sem guardar a cópia.
5. `FolderMemory.rename` (spec 5) continua funcionando com chaves relativas.

## Fora de escopo
- Detecção incremental com `QFileSystemWatcher` (F10, adiado).
- Índice persistente de sniffs entre sessões (cache em disco).
- Paralelizar a detecção além dos 2 threads atuais.

## Decisões assumidas (confirmar na revisão)
1. Os limites dos testes `perf` são definidos **depois** de medir a linha de base (R1.2), e não
   fixados agora.
2. `ui.paranoid_refresh` (R4.2) existe como válvula de escape, com padrão desligado.
3. A cabeça para os campos "primeira ocorrência" é de 256 KB (R5.2). Se uma fixture real mostrar
   cabeçalhos maiores, o valor sobe.
4. `FolderMemory` não guarda mais caminhos absolutos para pastas dentro do projeto (R7.1). Trocar o
   `local_root` para outra cópia do mesmo projeto preserva os mapeamentos.

## Notas de implementação
- Alterados:
  - `core/qe/pw_input.py` (ASE tardio, `read_input` memoizado), `core/qe/pw_output.py`,
    `core/qe/bands_x.py` (`gnu_shape`), `core/sniff.py` (`prune`, cabeça e cauda);
  - novo `core/qe/structure.py` (`SITE`, `format_formula`, `header_formula`), usado por
    `core/qe/relax.py`, `core/qe/summary/{scan,build}.py` e `core/calculations/bands/data.py`;
  - `core/calculations/base.py` (`match(listing, sniffs, sniff, forced)`, `load(result, sniff)`,
    `load_cached(result, sniff)`, nomes relativos em cache no `FolderListing`),
    `core/calculations/{bands,pdos}/`, `relax.py`, `scf.py`;
  - `core/detection.py` (`sniff_once`), novo `core/folder_memory.py`, `ui/services.py`;
  - `ui/main_window.py` (`_LoadTask` recebe o `sniff` do serviço, `memory.set_root`, aviso de
    `folders.json` corrompido, `paranoid_refresh`);
  - `core/config.py` (`ui.paranoid_refresh`), `config.example.yaml`.
- Testes novos: `tests/synthetic.py` (geradores), `tests/test_perf_detection.py`,
  `tests/test_folder_memory.py` (com os dois testes de memória que estavam em `test_detection.py`),
  `tests/test_pw_output_regression.py` + `tests/pw_output_golden.json` (capturado do parser antigo,
  antes do R5, para as 15 saídas pw.x das fixtures).

### Medições (`uv run pytest -m perf -s tests/test_perf_detection.py`)

Máquina do desenvolvedor (x86_64, 20 threads, SSD, Python 3.11), mediana de 3 execuções, em ms.
Projeto sintético de `tests/synthetic.py`: 520 pastas em 3 níveis (8 × 8 × 7), folhas alternando
bandas, PDOS, relax, SCF e texto.

| Medição | Linha de base | R2 | R3 | R4 | R5 | Final | Orçamento |
|---|---|---|---|---|---|---|---|
| `detect_folder` nas 520 pastas, a frio | 869 | 971 | 762 | — | 573 | 548 | 1500 |
| `detect_folder` nas 520 pastas, a quente | 361 | 277 | 74 | — | 83 | 72 | 180 |
| `sniff` de relax de 200 MB (cabeça + cauda) | 32 | 23 | — | — | 8 | 8 | 100 |
| `sniff` de relax de 15 MB (lido inteiro) | 446 | 339 | — | — | 118 | 117 | 220 |
| `sniff` de `.gnu` de 60 MB | 541 | 492 | — | — | 493 | 493 | 1500 |
| F5 (`invalidate()`) + detecção de 50 pastas | 96 | 83 | 59 | 7 | — | 7 | 48 |
| `import qe_studio.ui.main_window` (`-X importtime`, subprocesso) | 827 | 403 | — | — | — | 385 | 600 |

"—": não medido nessa etapa (a mudança não toca a medição). R6 e R7 entram na coluna "Final".

O relax de 200 MB já era rápido: acima de 16 MB o sniff lê só 8 KB + 1 MB. O caso caro do O5 é a
saída logo abaixo de 16 MB, lida inteira. Um `.gnu` acima de 64 MB não era detectado (`UNKNOWN`).

Observações:
- R2: a detecção a frio sobe, porque o ASE passa a ser importado no primeiro input lido, dentro dela.
- R3: a quente, o custo estava no `Path.relative_to` de cada arquivo para cada glob de cada papel
  (60 % do tempo). Com o nome relativo em cache e o teste de conteúdo antes do glob, caiu de 277 para
  74 ms.
- R5: com a regex única ainda com `re.I`, o relax de 15 MB ficou em 403 ms; sem `re.I`, em 118 ms.
- R6: na carga das bandas, o `read_structure` (ASE) levava 371 ms numa SCF de 15 MB, e a fórmula
  pelo cabeçalho leva 0,02 ms. O `read_input` memoizado responde em 1 µs, contra 0,1 ms do
  `parse_input` de um input pequeno.
- R7: com um `FolderMemory`, a detecção a quente pagava um `resolve()` por módulo e por pasta
  (+37 ms nas 520 pastas). `mappings(folder)` faz uma consulta só por pasta.
- Os orçamentos ficam em cerca de metade da linha de base onde a etapa prometia ganho, e são absolutos
  onde não prometia, com margem para máquinas mais lentas. O job `perf` do CI não bloqueia o merge.

## Critérios de aceite e testes
- [x] `tests/test_perf_detection.py` existe, roda no job `perf` do CI e tem a linha de base registrada.
- [x] Importar `qe_studio.ui.main_window` não carrega `ase` (`sys.modules`).
- [x] `detect_folder` chama `sniff` no máximo uma vez por arquivo da pasta (contador com um sniff falso).
- [x] F5 não relê arquivos inalterados: o contador de `_sniff_uncached` fica em zero numa segunda
      detecção depois do `invalidate()`. Um arquivo apagado sai do cache.
- [x] Um `.gnu` sintético de 80 MB é detectado como `GNU_DATA` com o `shape` correto, sem `loadtxt` no
      sniff.
- [x] `PwOutput` idêntico, antes e depois, para todas as saídas das fixtures. Numa saída sintética de
      20 MB com cabeçalho de 100 KB, `n_kpoints` e `n_electrons` são lidos.
- [x] `FolderMemory`: um `folders.json` antigo com chave absoluta dentro do `local_root` migra para
      relativa e continua resolvendo o mapeamento. Um JSON corrompido gera a cópia `.corrompido-*`, e a
      memória volta vazia.
