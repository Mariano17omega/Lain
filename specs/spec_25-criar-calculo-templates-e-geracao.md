# Spec 25: Criar cálculo — templates, extração do SCF e geração da pasta (backend)

| | |
|---|---|
| **Prioridade** | 25 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 24 (`InputEditor`, `next_free`/`write_new`) |
| **Usada por** | spec 26 (a janela só mostra e chama este backend) |
| **Esforço** | G |

## Itens de origem (`Ideias.md`)

> - crie um modulo para criar scripts e inputs de calculos (relax, vc-relax, scf, dos, bandas, etc) de forma grafica. [...]
> -- Crie uma pasta 'src/qe_studio/resources/templates/qsub/' e 'src/qe_studio/resources/templates/qe/' e organize os arquivos de templates por tipo de calculo usando a biblioteca Jinja2.
> -- Em 'src/qe_studio/resources/templates/qe/' vão ficar os templates dos scripts do cluster.
> -- Em 'Documentation/Referencia_de_scripts_QSUB' tem exemplos de scripts do cluster, que servirão de base [...] Nos scripts a linha '#$ -N "name"' define o nome que será exibido no scheduler do cluster. A linha '#$ -pe physica NP' define o numero NP de nucleos usados no calculo. Além do nome, cada script deve ter os parametros NP (Numero de nucleos), nk (Numero de k-points). 'qsub' é a extenção dos scripts [...] Os arquivos qsub devem ter um nome que descrevam o tipo de calculo e os parametros, por exemplo: 'relax.qsub', 'scf.qsub', 'pdos.qsub', 'bandas.qsub', etc.
> -- Em 'src/qe_studio/resources/templates/qe/' vão ficar os templates dos inputs, por exemplo 'projwfc.in', 'bands_pp', 'pp_mehg_charge.in', etc.
> -- Nessa janela de configuração de calculo, obrigadoriamente deve ser informado um input de SCF. A partir dele são extraidas as informações para gerar outros inputs, tipo o de NSCF (Só copiar e editar o "calculation = 'nscf'"), o prefix, etc. As informações que não podem ser obtidas do scf inicial, devem ser solicitadas na interface grafica. Por exemplo, pontos de simetria para o calculo de bandas. Se o calculo for de bandas, o usuario deve informar os pontos de simetria, usando a biblioteca Pymatgen. Caso contrário, o usuario pode informar uma rede de k-points manual. os pontos devem ser em K_POINTS crystal_b.
> -- O usuario pode editar as configurações do input e do script, preenchedo campos definidos na interface grafica. Por padrão os valores são preenchidos com valores extraidos do input de SCF. Se o usuario não informar um valor para algum campo, o valor padrão do template será usado. O usuario não editar texto manualmente.
> -- O usuario especifica o local onde será criado a pasta onde será salvo as coisas. O tipo de calculo define o prefixo da pasta, o nome da pasta que o usuario definir será o sufixo, por exemplo: "bandas_Al" ou "relax_Si"
> -- A criação desses calculos não devem substituir os existentes. Caso já existam arquivos com o mesmo nome, os arquivos devem ser salvos com um sufixo, por exemplo: "bandas_Al_1", "relax_Si_1", etc.
> -- A criação desses calculos é feita localmente, o usuario deve enviar os arquivos gerados para o cluster usando a ferramenta de sincronização.
> -- Add uma aba extra para descrição [...] O texto deve ser salvo em um arquivo .md na mesma pasta onde será criado o calculo.
> -- A pasta só é criada após o usuario preencher todas as informações obrigatorias e clicar em "Criar". Se o usuario cancelar, a janela é fechada sem criar nada.

Esta spec é o backend (Qt-free, testável sem janela); a spec 26 é a janela. Tipos da v1, por decisão do
usuário: `scf`, `relax`, `vc-relax`, `bandas`, `pdos`. `dos.x`, cargas (`pp.x`) e ELF 3D ficam para depois
(o registro de tipos foi feito para isso).

## Situação atual

- **As pastas de templates não existem.** `src/qe_studio/resources/templates/`, `templates/qsub/` e `templates/qe/`
  são a estrutura **sugerida** em `Ideias.md`, não algo já criado: hoje `resources/` tem só `__init__.py` e
  `config.example.yaml`. Esta spec cria as pastas e os arquivos (R2), seguindo essa estrutura.
- **Não existe gerador.** Nada em `core/` escreve inputs ou scripts. `core/qe/pw_input.py` só lê (`parse_input`
  via ASE, `read_input`, `QEInput.cards` com o texto bruto de cada card). O editor que preserva formatação nasce
  na spec 24 (`InputEditor`).
- **Sem dependências:** `.venv` e `uv.lock` não têm `jinja2` nem `pymatgen` (nem `spglib`); `pyproject.toml:6-13`
  lista `PyQt6`, `matplotlib`, `numpy`, `ase`, `pyyaml`, `pydantic`. O CI roda Python 3.11 e 3.12 com `uv sync`.
  O ASE já oferece caminho de bandas (`ase.dft.kpoints.bandpath`, `Cell.bandpath`), mas o pedido é pymatgen.
- **Recursos empacotados:** `src/qe_studio/resources/` tem `__init__.py` e `config.example.yaml`. O hatch empacota
  `src/qe_studio` inteiro (`pyproject.toml:37-38`, sem include/exclude). `config_template.template_text()`
  (`core/config_template.py:18-21`) lê com `files("qe_studio.resources").joinpath(...)`; subpastas não precisam ser
  pacotes. `tests/test_config.py:199-203` exige `config.example.yaml` da raiz idêntico ao de `resources/`.
- **Config:** `core/config.py` compõe `AppConfig` de seções `_Section(BaseModel)` com `extra="forbid"`
  (l.65-66, 179-184): `paths`, `cluster`, `sync`, `plot`, `ui`. Não há janela de configuração por decisão do PRD
  §6: ajuste novo = modelo pydantic + `config.example.yaml`.
- **Scripts de referência** (`Documentation/Referencia_de_scripts_QSUB/*.qsub`, SGE): todos têm o shebang, os
  banners `####`, `PWCOMMAND="/opt/espresso-7.1/bin/pw.x -nk N"`, o cabeçalho `#$ -N "nome"`, `#$ -pe physica NP`,
  `#$ -cwd`, `#$ -j y`, e **o mesmo bloco Intel MPI** (`OMP_NUM_THREADS=1`, `I_MPI_SHM=bdw_avx2`, dois
  `. /opt/intel/oneapi/.../vars.sh`, `MPICOMMAND="…/mpiexec -bootstrap ssh"`), e terminam em `exit 0`. Variam:

  | script | `-N` | NP | `-nk` | passos |
  |---|---|---|---|---|
  | `bands.qsub` | `BD010o1` | 64 | 4 | scf, bands (`pw.x`), `bands.x -i bands_pp.in` (sem mpiexec) |
  | `PDOS.qsub` | `pdo2` | 64 | 8 | `proj.in` por heredoc, scf, nscf, `projwfc.x`, `mkdir -p orbitals; mv *wfc* orbitals/` |
  | `relax.qsub` | `test` | 64 | 8 | `relax.in` → `relax.out` |
  | `vc-relax.qsub` | `test` | 64 | 8 | idêntico ao relax com `vc-relax.in/.out` |
  | `cargas.qsub`, `pp_elf_3d.qsub` | — | 32/64 | 4 | fora da v1 |

- **Nomes que a detecção reconhece** (PRD §3): bandas = `scf*.out` + `bands*.in/out` + `*.gnu`; PDOS = `scf*.out`,
  `nscf*.out`, `projwfc*.out` e a subpasta `orbitals/` com `pdos_atm#*_wfc#*`. Por conteúdo, nomes diferentes
  também servem, mas seguir o padrão evita depender disso.
- **Nomes que não sobrescrevem:** `Path.mkdir(exist_ok=False)` + `open(path, "x")` (padrão de
  `config_template.create_config`); `next_free`/`write_new` na spec 24.
- **ASE e import tardio** (spec 14): `ase` só é importado dentro de funções; `tests/test_perf_detection.py:127-157`
  roda `python -X importtime -c "import qe_studio.ui.main_window"` e exige que `ase` não apareça (e orçamento de
  0,6 s). `pymatgen` e `jinja2` seguem a mesma regra.
- **Arquitetura** (`tests/test_architecture.py`): arquivos < 500 linhas; `core/` não importa `ui`; PyQt6 só em 3
  módulos de `core`; `QT_FREE` é lista manual.

## Requisitos

### R1: Dependências
1. `pyproject.toml`: `jinja2>=3.1` e `pymatgen` (versão mínima a fixar ao implementar) em `dependencies`;
   `uv.lock` regenerado; CI (`uv sync`) instala ambos nas duas versões do Python.
2. **Import tardio**: `jinja2` é importado só dentro de `core/calc_create/render.py` e `pymatgen` só dentro de
   `kpath.py`; o teste de import do `main_window` passa a exigir que nem `ase`, nem `pymatgen`, nem `jinja2`
   estejam em `sys.modules`/no `importtime`.
3. Falha de import do `pymatgen` (ambiente sem a biblioteca) → `KPathUnavailable` com mensagem clara; o tipo
   "bandas" continua funcionando com o caminho digitado à mão.

### R2: Templates (Jinja2)
1. Layout a **criar** (nada disso existe hoje), com as duas pastas-raiz do pedido (`qsub/` e `qe/`) e os arquivos
   organizados por tipo de cálculo; carregado com `importlib.resources.files("qe_studio.resources")` (padrão de
   `config_template.py`):
   ```
   src/qe_studio/resources/templates/
     qsub/_base.qsub.j2                (cabeçalho SGE/Intel comum; blocos `body`, `post`)
     qsub/scf.qsub.j2  relax.qsub.j2  vc-relax.qsub.j2  bandas.qsub.j2  pdos.qsub.j2
     qe/bandas/bands_pp.in.j2          (bands.x)
     qe/pdos/projwfc.in.j2             (projwfc.x)
   ```
   Os `.qsub.j2` estendem `_base.qsub.j2` (`{% extends %}`), então o bloco Intel/SGE comum existe uma vez só.
   **Scripts do cluster em `templates/qsub/` e inputs em `templates/qe/`** (as linhas 17–19 de `Ideias.md` se
   contradizem; ver decisões). As subpastas por tipo dentro de `qe/` (`bandas/`, `pdos/`) são a organização "por tipo
   de cálculo" pedida; os nomes de arquivo dos templates são desta spec e podem mudar na implementação sem alterar o
   resto (o registro de tipos, R3, é quem aponta para eles).
2. `core/calc_create/render.py:render(template: str, values: Mapping) -> str`: `jinja2.Environment` com
   `PackageLoader`/loader sobre os recursos, `StrictUndefined`, `autoescape=False`, `keep_trailing_newline=True`,
   `trim_blocks`/`lstrip_blocks`. Variável faltando → erro com o nome (nunca texto com lacunas).
3. O pw.x **não** tem template Jinja: os inputs `nscf.in`, `bands.in`, `relax.in`, `vc-relax.in` e o próprio
   `scf.in` são derivados do SCF do usuário com o `InputEditor` (R4). Jinja cobre o que o QE não deriva:
   `bands_pp.in`, `projwfc.in` e os scripts `.qsub`.
4. `src/qe_studio/resources/templates/**` entra no pacote (nada a configurar no hatch) e um teste confere que
   `files(...)` encontra cada template.

### R3: Tipos de cálculo (registro em Python)
1. `core/calc_create/types/` com um módulo por tipo (`scf.py`, `relax.py`, `vc_relax.py`, `bandas.py`, `pdos.py`) e
   `REGISTRY` em `types/__init__.py` (padrão de `core/calculations/__init__.py`): tipo novo = módulo + registro,
   sem tocar no resto.
2. `CalcType` declara: `id`, `label` (dropdown: "SCF", "Relax", "VC-Relax", "Bandas", "PDOS"), `folder_prefix`
   (`scf`, `relax`, `vc-relax`, `bandas`, `pdos`), `fields(scf: ScfInfo) -> list[FormField]` e
   `plan(scf: ScfInfo, values: Mapping) -> CalcPlan`.
3. `FormField(id, label, kind, default, required, group, tooltip, choices)`, com `kind` em
   `int|float|text|choice|bool|kpath|kmesh`. **Padrão preenchido a partir do SCF** quando existe (ex.: `prefix`,
   `nbnd`, `ecutwfc`); o que o SCF não dá usa o padrão do tipo. Campo vazio na janela → o padrão é usado
   (nada de texto livre para inputs ou scripts: só estes campos).
4. `CalcPlan(files: list[PlannedFile], notes: list[str])` e `PlannedFile(name, kind, text, tab_label)` com
   `kind` em `pw_input | qe_input | qsub | notes`. A ordem de `files` é a das abas da spec 26.
5. Arquivos por tipo (nomes finais na pasta nova):

   | tipo | arquivos |
   |---|---|
   | `scf` | `scf.in`, `scf.qsub` |
   | `relax` | `relax.in`, `relax.qsub` |
   | `vc-relax` | `vc-relax.in`, `vc-relax.qsub` |
   | `bandas` | `scf.in`, `bands.in`, `bands_pp.in`, `bandas.qsub` |
   | `pdos` | `scf.in`, `nscf.in`, `projwfc.in`, `pdos.qsub` |

   Mais `descricao.md` quando o usuário escreve notas (R7). O nome do `.qsub` é o do tipo (`scf.qsub`,
   `relax.qsub`, `vc-relax.qsub`, `bandas.qsub`, `pdos.qsub`); os parâmetros (nome do job, NP, nk) ficam
   **dentro** do script.

### R4: Extração do SCF e derivação dos inputs
1. `core/calc_create/scf_info.py:read_scf(path) -> ScfInfo` (worker): lê o input com `InputEditor` para o texto e
   `read_input` (ASE, import tardio) para a estrutura. **Obrigatório**: `calculation` igual a `scf` (ou ausente,
   padrão do pw.x); outro valor → `ScfError("O arquivo não é um SCF (calculation = 'relax')")`. Extrai: `prefix`
   (padrão `pwscf`), `outdir`, `pseudo_dir`, `ibrav`, `nat`, `ntyp`, `ecutwfc`, `ecutrho`, `nspin`,
   `occupations`, `smearing`/`degauss`, `nbnd` (se houver), `K_POINTS` (tipo e grade), espécies e a estrutura
   (`ase.Atoms`) para o caminho de bandas. Campos ausentes viram `None` (o tipo usa o padrão).
2. Derivações com o `InputEditor` (spec 24), sempre a partir do **texto** do SCF para não perder formatação:
   - `scf.in` da pasta nova: cópia do SCF (nome padronizado);
   - `nscf.in` (PDOS): `calculation='nscf'`, `occupations` (`tetrahedra`/`smearing`, campo do formulário, padrão
     o do SCF), `nbnd` (campo, padrão do SCF ou +20 %), `K_POINTS automatic` com a rede do campo `kmesh` (R5);
   - `bands.in` (bandas): `calculation='bands'`, `nbnd` (campo), `K_POINTS crystal_b` do caminho (R5), troca
     `occupations = 'tetrahedra*'` (incompatível com bandas) por `'smearing'`, com `smearing`/`degauss` do SCF ou
     `'gaussian'`/`0.01`, mantém o resto;
   - `relax.in`/`vc-relax.in`: `calculation='relax'|'vc-relax'`; acrescenta `&IONS` (e `&CELL` no vc-relax) com os
     campos do formulário (`ion_dynamics`, `cell_dynamics`, `press`, `forc_conv_thr`, `nstep`, padrões do tipo)
     **se o SCF não os trouxer**; `nstep`/`forc_conv_thr` vão para `&CONTROL`.
   - o que o formulário não pede (pseudopotenciais, `ecutwfc`, `ibrav`, posições) é preservado byte a byte.
3. **Prefix e outdir** vêm do SCF e valem em todos os arquivos da pasta (o `scf`, `nscf`, `bands`, `projwfc` e
   `bands_pp` têm de enxergar o mesmo `outdir`/`prefix`). `ScfInfo` expõe um aviso se `outdir` é absoluto.

### R5: K-points
1. **Bandas:** o usuário informa **pontos de simetria**. `core/calc_create/kpath.py:suggest_path(atoms) ->
   KPath` usa `pymatgen.symmetry.bandstructure.HighSymmKpath` (convenção `setyawan_curtarolo`, a padrão do
   pymatgen) sobre a estrutura do SCF (`pymatgen.io.ase.AseAtomsAdaptor`), em worker, devolvendo `KPath(points:
   list[KPoint(label, frac: (f1, f2, f3), npts)], breaks: set[int])`: `label` com Γ como `GAMMA`/`Γ`, `frac` em
   coordenadas fracionárias da célula **do input** (conferir que a célula padronizada do pymatgen coincide com a do
   input; se não coincidir, avisar e reconverter para a célula do input), `npts` = pontos até o próximo
   (padrão 20). O usuário pode editar rótulos, coordenadas, `npts`, e adicionar/remover/reordenar pontos.
2. `kpath.to_card(kpath) -> str` gera `K_POINTS crystal_b`:
   ```
   K_POINTS crystal_b
   N
   f1 f2 f3 npts   ! LABEL
   ```
   O peso de cada ponto é o número de pontos até o próximo; no **fim de um segmento** (salto no caminho, ex.:
   `X|U`) o peso é `1`; o último ponto leva `1`. O rótulo vai em comentário (`! Γ`), que o parser de bandas do
   Lain já lê (PRD §3: rótulos extraídos do card `crystal_b`).
3. **Demais tipos:** rede de k-points **manual**: campo `kmesh` (`n1 n2 n3` e deslocamentos `s1 s2 s3`),
   gerando `K_POINTS automatic`. Padrão: a rede do SCF, se `automatic`; senão 4 4 4 0 0 0. (Ver decisão 3 sobre
   `crystal_b`.)
4. `K_POINTS` e `nbnd` são os campos **obrigatórios** extras de bandas e PDOS; sem eles a janela não deixa criar.

### R6: Scripts `.qsub`
1. Campos comuns a todos os tipos (`group="Script"`): `job_name` (`#$ -N`; padrão `<prefix>` do SCF, até 15
   caracteres, sem espaços), `np` (`#$ -pe <pe> NP`; padrão 64), `nk` (`pw.x -nk`; padrão 4 em bandas, 8 nos
   demais), `qe_version` não é campo (vem do `calculos.qe_bin`, R6.3).
2. `nk` é o **número de pools** do `-nk`, não o número de k-points (ver decisão 2). Validação: `np % nk == 0`
   (senão aviso de que o QE rebaixa os pools), `nk >= 1`, `np >= 1`. Nunca bloqueia, só avisa.
3. **Config do cluster** (nova seção, `core/config.py`): `CalcConfig` em `AppConfig.calculos` com `qe_bin`
   (`/opt/espresso-7.1/bin`), `mpi_bin` (`/opt/intel/oneapi/mpi/latest/bin/mpiexec -bootstrap ssh`),
   `parallel_env` (`physica`), `env_lines` (as quatro linhas `export`/`. …vars.sh` da referência), `omp_threads`
   (1). Padrões = os dos scripts de referência (funciona de fábrica no cluster do usuário); documentada nas duas
   cópias do `config.example.yaml` (idênticas, `test_config.py`). O formulário **não** edita isso (ajuste de
   cluster, não de cálculo).
4. Passos por tipo (variáveis do `_base.qsub.j2`: `steps` como lista de comandos, nunca texto livre):
   - `scf`: `pw.x -i scf.in > scf.out`; `relax`/`vc-relax`: `pw.x -i relax.in > relax.out` (idem vc-relax);
   - `bandas`: `scf` → `bands` (`pw.x -i bands.in > bands.out`) → `bands.x -i bands_pp.in > bands_pp.out`
     (sem `mpiexec`, como na referência);
   - `pdos`: `scf` → `nscf` → `projwfc.x -i projwfc.in > projwfc.out` → `mkdir -p orbitals; mv *wfc* orbitals/
     2>/dev/null` (como a referência, para o PRD §3 reconhecer a pasta).
   O `projwfc.in` é um **arquivo** (não heredoc), com `prefix`/`outdir` do SCF, `DeltaE`, `Emin`, `Emax`,
   `degauss`, `ngauss`, `filpdos` (campos com padrões da referência: 0,01, -25, 25, 0,01, 0).
5. O `_base.qsub.j2` reproduz o cabeçalho da referência (`#!/usr/bin/env bash`, banners, `PWCOMMAND`, `#$ -N`,
   `#$ -pe`, `#$ -cwd`, `#$ -j y`, bloco Intel, `exit 0`); o autor/data de `PDOS.qsub` **não** vão para o template.

### R7: Criação da pasta (`core/calc_create/writer.py`)
1. `create_folder(parent: Path, type_: CalcType, suffix: str, plan: CalcPlan, notes: str) -> Created`:
   - pasta `<folder_prefix>_<suffix>` em `parent`; se existe, `<…>_1`, `_2`… (`next_free` + `mkdir(exist_ok=False)`
     em laço, seguro contra corrida): **nunca** reaproveita nem toca numa pasta existente;
   - escreve cada `PlannedFile` com `open(path, "x")` (dentro de uma pasta nova nunca há colisão; a regra
     vale mesmo assim);
   - `descricao.md` com `notes`, **só** quando o texto não é vazio (depois de `strip`);
   - se qualquer escrita falha, remove apenas os arquivos e a pasta **que ela mesma criou** e devolve o erro;
   - devolve `Created(folder, files, renamed_from)` (`renamed_from` guarda o nome pedido quando houve sufixo).
2. `validate_target(parent, suffix) -> list[str]`: `suffix` não vazio, só `[A-Za-z0-9._-]` (sem `/`), `parent`
   existe e é gravável; a janela usa para habilitar "Criar" e mostrar o nome final (`preview_name(parent, type_,
   suffix)` devolve o nome com `_n` que seria usado, sem criar nada).
3. A pasta só existe depois de `create_folder`; cancelar a janela não chama nada daqui.
4. Escrita em worker (`run_task`); não há leitura na GUI.

## Fora de escopo
- A janela (spec 26) e o envio ao cluster (spec 27).
- Tipos `dos` (dos.x), cargas e ELF 3D (`pp.x`, vários SCFs de fragmentos); entram depois como módulos de
  `types/` + templates.
- Submeter o job (`qsub`) ou monitorá-lo; validar o input com o `pw.x`.
- Editar texto livre dos inputs/scripts (decisão do pedido: só campos).
- Escolher outros caminhos de bandas (`hinuma`, `latimer_munro`) ou alterar o grid padrão do pymatgen.

## Decisões assumidas (confirmar na revisão)
1. `templates/qsub/` = scripts do cluster e `templates/qe/` = inputs (as linhas 17–19 de `Ideias.md` dizem que
   `qe/` guarda os dois; tomei a linha 19 como erro de digitação).
2. `nk` = pools do `pw.x -nk` (é o que está nos scripts de referência), não o número de k-points; o texto do
   pedido ("Numero de k-points") foi lido assim.
3. `K_POINTS crystal_b` **só para bandas** (um caminho). Os demais tipos têm rede manual como
   `K_POINTS automatic`: o pedido diz "rede de k-points manual ... em crystal_b", mas `crystal_b` descreve um
   caminho, não uma rede, e um NSCF para PDOS precisa de uma malha.
4. O NSCF herda `occupations`/`nbnd` do SCF, com campos editáveis; `bands.in` troca tetraedros por `smearing`.
5. `.qsub` nomeado pelo **tipo** (`bandas.qsub`); os parâmetros ficam dentro do script (o pedido diz "descrevam
   o tipo de cálculo e os parâmetros", e os exemplos têm só o tipo).
6. `pymatgen` e `jinja2` como dependências de runtime com import tardio; o tamanho de instalação do `pymatgen`
   (dezenas de dependências) é aceito.
7. Configuração do cluster em `config.yaml` (`calculos:`), com os padrões dos scripts de referência.
8. `descricao.md` só é criado se houver texto.
9. A cópia do SCF vai para `scf.in` na pasta nova, com os mesmos `prefix`/`outdir` (pastas autossuficientes).

## Notas de implementação
- Novos (todos em `core/calc_create/`, Qt-free, entram em `QT_FREE`): `__init__.py`, `render.py`, `scf_info.py`,
  `kpath.py`, `writer.py`, `types/{__init__,base,scf,relax,vc_relax,bandas,pdos}.py` (`base.py` com `CalcType`,
  `FormField`, `CalcPlan`). Recursos: `resources/templates/...` (R2).
- Alterados: `pyproject.toml`, `uv.lock`, `core/config.py` (`CalcConfig`, `AppConfig.calculos`),
  `config.example.yaml` e `src/qe_studio/resources/config.example.yaml` (idênticos), `tests/test_perf_detection.py`
  (teste de import), `tests/test_architecture.py` (`QT_FREE`).
- `kpath.py` roda em worker pela spec 26 (importar o `pymatgen` leva segundos); `suggest_path` não é chamado na
  GUI.
- Referência: `Documentation/Referencia_de_scripts_QSUB/` continua como material de consulta, não é empacotado.

## Critérios de aceite e testes
- [ ] Templates: os 5 `.qsub` renderizam com os padrões e reproduzem, linha a linha (ignorando nome do job, NP e
      `-nk`), o cabeçalho e os passos da referência correspondente; `_base` existe uma vez; `StrictUndefined`
      levanta com o nome da variável que falta.
- [ ] Recursos: `files("qe_studio.resources")` encontra todos os templates (teste de empacotamento).
- [ ] `read_scf`: nas fixtures de SCF (`qe731_*`) extrai `prefix`, `outdir`, `nat`, `ecutwfc`, `nspin`,
      `occupations`; `calculation = 'relax'` → `ScfError`; `al.scf.out`/arquivo que quebra o ASE não derruba
      (estrutura `None`, tipo "bandas" avisa e pede o caminho à mão).
- [ ] Derivação: `nscf.in`, `bands.in`, `relax.in`, `vc-relax.in` têm só as chaves pedidas alteradas (diff linha a
      linha contra o SCF); `prefix`/`outdir` idênticos em todos os arquivos; lint sem erros em todos.
- [ ] K-path: Al (fcc) sugere Γ, X, W, K, L; `to_card` gera `K_POINTS crystal_b` com N correto, peso `npts` e `1`
      no fim de cada segmento e no último ponto; o parser de bandas do Lain lê os rótulos do card gerado
      (`test_bands`-style); sem `pymatgen` → `KPathUnavailable`. Rede manual gera `K_POINTS automatic`.
- [ ] qsub: `np % nk != 0` → aviso (não erro); passos de cada tipo na ordem da seção R6.4; PDOS inclui
      `mkdir -p orbitals; mv *wfc* orbitals/`.
- [ ] `create_folder`: `bandas_Al`; segunda criação → `bandas_Al_1`, terceira `_2`; arquivos todos com `open("x")`; nada
      fora da pasta nova; falha no meio (arquivo bloqueado simulado) remove só o que criou; `descricao.md` só com
      texto; `validate_target` recusa sufixo vazio, com `/` e pai inexistente.
- [ ] Config: `CalcConfig` com padrões = referência; chave desconhecida recusada (`extra="forbid"`);
      `config.example.yaml` idêntico nas duas cópias.
- [ ] Round-trip de detecção: a pasta `bandas_*` e `pdos_*` gerada, **preenchida com as saídas das fixtures**
      (cópias), é reconhecida por `detect_folder` como Bandas e PDOS (nomes do PRD §3).
- [ ] Import: `import qe_studio.ui.main_window` não carrega `ase`, `pymatgen` nem `jinja2`; orçamento de
      importação inalterado.
- [ ] `test_architecture.py`: módulos novos < 500 linhas, sem PyQt6, `core/` sem `ui`.
