# Spec 14: Desempenho da detecção e memória de pastas

| | |
|---|---|
| **Prioridade** | 14 |
| **Status** | Rascunho para revisão |
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
  - `core/qe/pw_input.py`, `core/qe/pw_output.py`, `core/sniff.py`;
  - `core/calculations/base.py`, `core/calculations/{bands,pdos,relax}.py`;
  - `core/detection.py`, `ui/services.py`;
  - `ui/main_window.py` (`_LoadTask` passa o `sniff`);
  - `core/config.py` (`ui.paranoid_refresh`), `config.example.yaml`.
- `FolderMemory` precisa conhecer `local_root`: o construtor recebe a raiz, e `reload_config`
  (`main_window.py:587-611`) recria a memória se a raiz mudar.
- Registrar nesta seção, durante a implementação, a tabela "antes/depois" de cada medição do R1.

## Critérios de aceite e testes
- [ ] `tests/test_perf_detection.py` existe, roda no job `perf` do CI e tem a linha de base registrada.
- [ ] Importar `qe_studio.ui.main_window` não carrega `ase` (`sys.modules`).
- [ ] `detect_folder` chama `sniff` no máximo uma vez por arquivo da pasta (contador com um sniff falso).
- [ ] F5 não relê arquivos inalterados: o contador de `_sniff_uncached` fica em zero numa segunda
      detecção depois do `invalidate()`. Um arquivo apagado sai do cache.
- [ ] Um `.gnu` sintético de 80 MB é detectado como `GNU_DATA` com o `shape` correto, sem `loadtxt` no
      sniff.
- [ ] `PwOutput` idêntico, antes e depois, para todas as saídas das fixtures. Numa saída sintética de
      20 MB com cabeçalho de 100 KB, `n_kpoints` e `n_electrons` são lidos.
- [ ] `FolderMemory`: um `folders.json` antigo com chave absoluta dentro do `local_root` migra para
      relativa e continua resolvendo o mapeamento. Um JSON corrompido gera a cópia `.corrompido-*`, e a
      memória volta vazia.
