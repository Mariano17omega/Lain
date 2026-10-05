# Spec 28: Padrões de unidade de simulação e modo Padrão/Avançado no "Criar cálculo"

| | |
|---|---|
| **Prioridade** | 28 (base das specs 29 e 30) |
| **Status** | Implementada. Desvios:<br>- **Chave estável por arquivo:** como o nome pode ser editado, `PlannedFile.key` (`script`, `scf`, `relax`, `bands`, `bands_pp`…) identifica o arquivo; `FormField.group` passou a nomear a chave, e a janela indexa abas e prévias por ela. Cada tipo declara `input_files(scf)` → `types/files.py:InputFile(key, name, label)`; o campo "Nome do arquivo" é `name:<key>`.<br>- **Marcas pelo plano:** `CalcPlan.problems` (id do campo → problema) junta os problemas dos campos e dos nomes; a janela marca a partir dele. Nome repetido marca os dois campos.<br>- **Malha do NSCF:** oculta no Padrão, exceto quando o SCF não tem `K_POINTS automatic` (aí o padrão seria 4×4×4 e não a do SCF; o campo aparece).<br>- **`ScfInfo.warnings` removido:** as notas de `pseudo_dir` precisam de `jobs`, então estão em `core/calc_create/unit.py:unit_notes` com as de caminho fora da pasta; a de `outdir` absoluto deixou de existir.<br>- **`edits.put_text`:** `put_string` compara sem caixa (bom para palavras-chave); `outdir`/`pseudo_dir` usam `put_text`, que compara como escrito.<br>- **Templates:** `scf`/`relax`/`vc-relax` continuam um por tipo (laço sobre `pw_runs`); o teste de referência da PDOS passa `nk = 8` (o da referência), já que `jobs.nk` é 4.<br>- **Testes:** `test_calc_types.py` planeja no Avançado; os critérios desta spec estão em `tests/test_calc_standard.py` e no fim de `test_calc_create_dialog.py`.<br>- Como as 27-x, a spec fica em `specs/` (não movida para `Archived/`). |
| **Depende de** | spec 25 (backend de "Criar cálculo"), spec 26 (janela), **spec 27-1** (`pdos.qsub` e `projwfc.in` corrigidos) e **spec 27-2** (caminho das bandas digitado, sem "Sugerir") |
| **Usada por** | spec 29 (carga), spec 30 (diferença de carga) |
| **Esforço** | G |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda o contrato de `CalcType`/`FormField`, os nomes fixos em Python e nos templates, a janela e boa parte dos testes de `test_calc_*`. Exige julgamento para não quebrar a detecção (PRD §3) nem as specs 13 e 25. |

## Itens de origem (ideias de 05/10/2026)

> # Definição de padrões de simulação
> - Cada pasta deve conter uma simulação completa e independente, sem usar caminhos absolutos ou relativos externos às pastas.
> - Cada pasta de simulação é chamada de unidade de simulação.
> - Cada unidade de simulação tem um script ".qsub" que executa o cálculo no cluster.
> - Cada unidade de simulação tem os inputs e outputs com extensões ".in" e ".out" respectivamente.
> - No geral os nomes das pastas são descritivos e seguem o padrão "<calculo>_<nome>" ou "<calculo>". Onde o <calculo> pode ser: "Bands", "Relax", "PDOS", "Charge", "Diff_Charge", "SCFS", etc. e o Nome é definido pelo usuário na criação.
> - Os nomes dos inputs seguem o padrão "<calculo>_<nome_do_input_ou_prefixo>.in" [...] onde <calculo> pode ser: "scf", "nscf", "relax", "vc-relax". Por enquanto esses são os únicos inputs que seguem esse padrão.
> - Os nomes dos inputs de pós-processamento são mais simples: "bands_pp.in" para o input de "bands.x", "projwfc.in" para o input de "projwfc.x", [...]
> - Os nomes dos arquivos de output seguem o mesmo padrão dos inputs, só muda a extensão que é '.out'.
> - Algumas outras pastas seguem o padrão um pouco diferente [...] "<numero>_Bands_<nome>" [...] Não são o padrão que o usuário deve seguir.
>
> # Padrões dos arquivos de simulação
> - Na janela de criação de unidade de simulação deve ter um botão "Avançado/Padrão" que muda os campos editáveis nos inputs criados.
> - "Avançado": todos os campos dos inputs devem ser editáveis pelo usuário.
> - "Padrão": parte dos campos dos inputs devem ser preenchidos automaticamente pelo programa seguindo os padrões de nomes de inputs e pastas [...] deixando editáveis apenas os campos que "fazem sentido" para o tipo de cálculo.
> - Bandas: o input do "calculation = 'bands'" tem o nome "bands.in" e a única coisa editável são os pontos "K_POINTS crystal_b" [...] `bands_pp.in`: `prefix = <prefix_do_scf>`, `outdir = './tmp/'`, `filband = './band'`. NP = 64 e NK = 4. O usuário só informa: nome da pasta, SCF base, pontos "K_POINTS crystal_b".
> - PDOS: `&PROJWFC prefix = <prefixo do scf>, outdir = './tmp/', DeltaE = 0.01, filpdos = <prefixo do scf>.dat, Emin = -25.0, Emax = 25.0, ngauss = 0, degauss = 0.000735`. NP = 64 e NK = 4. O usuário só informa: nome da pasta, SCF base, [...] "Emin" e "Emax".

As partes de carga (`pp.x`) estão nas specs 29 e 30; os "Projetos" na spec 31.

**Respostas do usuário (05/10/2026):** "Avançado" = os campos que a janela já tem (specs 25/26), mais os nomes de
arquivo; o `pseudo_dir` vem do `config.yaml`; a malha do NSCF da PDOS é a do SCF, oculta no Padrão (o
"K_POINTS crystal_b" do item da PDOS era engano: o NSCF precisa de malha); NP/NK ficam ocultos no Padrão e vêm do
`config.yaml`; prefixos `SCF`, `Relax`, `VC-Relax`, `Bands`, `PDOS` (e `Charge`, `Diff_Charge` nas specs 29/30);
"unidade de simulação" é só o nome de uma pasta de cálculo, sem tratamento especial na árvore ou na grade.

## Situação atual

- **Prefixos de pasta** em minúsculas e em português: `folder_prefix` = `scf`, `relax`, `vc-relax`, `bandas`,
  `pdos` (`core/calc_create/types/*.py`). `writer.folder_name` (`writer.py:48-49`) devolve sempre
  `f"{folder_prefix}_{suffix}"`, e `validate_suffix` (`:55-56`) recusa nome vazio ("Informe o nome da pasta"). A
  janela segue isso: rótulo "Nome da pasta *" (`ui/dialogs/calc_create/setup_page.py:117`), `problems()` (`:170-177`)
  e `TabsPage._show_files` sai cedo com sufixo vazio (`tabs_page.py:205-206`).
- **Nomes de arquivo fixos em dois lugares:**
  - Python: `INPUT = "scf.in"` (`types/scf.py:12`), `f"{calculation}.in"` (`types/relax.py:31-33`),
    `SCF = "scf.in"`, `BANDS = "bands.in"` (`types/bandas.py:15-16`), `"scf.in"`, `"nscf.in"`, `"projwfc.in"`
    (`types/pdos.py:13-15`). `script_name` = `f"{folder_prefix}.qsub"` (`types/base.py:187-189`).
  - Templates: `qsub/scf.qsub.j2`, `relax.qsub.j2`, `vc-relax.qsub.j2`, `bandas.qsub.j2`, `pdos.qsub.j2` escrevem
    `-i "scf.in" > "scf.out"` etc. Só os `stems` do bands.x são variáveis.
- **outdir e pseudo_dir** vêm do SCF como estão (`ScfInfo.outdir`/`pseudo_dir`). `scf_info._warnings`
  (`scf_info.py:84-97`) só avisa: `outdir` absoluto, `pseudo_dir` ausente, `pseudo_dir` relativo. A cópia do SCF
  (`scf.in` de bandas/PDOS) é o texto byte a byte (`bandas.py:83`, `pdos.py:99`).
- **NP e nk:** `np` padrão = `JobsConfig.cores` (64, `core/config.py:202`; `types/script.py:46,83`); `nk` padrão =
  `CalcType.default_nk` (8; `BandasType` 4) (`types/base.py:185`, `bandas.py:39`). Os campos `job_name`, `np`, `nk`
  ficam na aba do script (`types/script.py:31-58`).
- **Campos por tipo** (`input_fields`): SCF/Relax/VC-Relax têm `kmesh` (e `nstep`, `forc_conv_thr`,
  `ion_dynamics`; VC-Relax `cell_dynamics`, `press`); Bandas `nbnd` (obrigatório), `kpath` (obrigatório),
  `filband` (padrão `bands.dat`, com `_up`/`_dw` por canal: `channel_filband`); PDOS `nbnd` (obrigatório),
  `occupations`, `kmesh` (obrigatório), `delta_e` 0,01, `e_min` −25, `e_max` 25, `degauss` **0,01**, `ngauss` 0,
  `filpdos` `<prefix>.dat` (`types/pdos.py:38-64`).
- **Não existe noção de modo.** `FormField` (`types/base.py:37-46`) não tem atributo de visibilidade;
  `FieldForm` (`ui/dialogs/calc_create/form.py`) monta um widget por campo; as abas são construídas uma vez a partir
  do primeiro plano (`tabs_page.py:78-82`) e o diálogo só as reconstrói quando o tipo ou o SCF mudam
  (`dialog.py:117-138`).
- **Bug F1 de `specs/report-04-10-26.md`:** corrigido pela **spec 27-1** (anterior a esta): `qsub/pdos.qsub.j2` termina em
  `mkdir -p orbitals` + `mv *pdos_atm#* orbitals/ 2>/dev/null` (antes `mv *wfc*`, que movia `projwfc.in/out`), e o
  `projwfc.in` **omite** `ngauss`/`degauss` quando a ocupação do NSCF é por tetraedros. A detecção da PDOS aceita
  `pdos_tot` na pasta ou em `orbitals/` (`core/calculations/pdos/module.py:72-81`). Esta spec parte desse template.
- **Caminho das bandas:** a spec 27-2 removeu "Sugerir (pymatgen)"; o `kpath` é digitado pelo usuário (tabela vazia
  na primeira visita) e `pymatgen` deixou de ser dependência.

## Requisitos

### R1: Nomes do padrão (nos dois modos)
1. **Pasta:** `<Prefixo>_<nome>`, ou só `<Prefixo>` quando o nome fica vazio. Prefixos (`CalcType.folder_prefix`):

   | tipo (`id`) | rótulo | pasta | script |
   |---|---|---|---|
   | `scf` | SCF | `SCF` | `scf.qsub` |
   | `relax` | Relax | `Relax` | `relax.qsub` |
   | `vc-relax` | VC-Relax | `VC-Relax` | `vc-relax.qsub` |
   | `bandas` | Bandas | `Bands` | `bands.qsub` |
   | `pdos` | PDOS | `PDOS` | `pdos.qsub` |

   O nome do script passa a ser uma ClassVar `script_stem` (não mais derivado do prefixo da pasta). Os `id`s não
   mudam (QSettings e testes os usam). Nome já existente → `_1`, `_2`… como hoje (`unique_names.next_free_dir`):
   `Bands` → `Bands_1`.
2. `writer.validate_suffix` aceita o nome vazio; `folder_name(type_, "")` = `folder_prefix`. Continua recusando
   `/`, `.`, `..` e caracteres fora de `[A-Za-z0-9._-]`.
3. **Inputs** (`<prefix>` = o `prefix` do SCF base, `pwscf` sem prefix):

   | tipo | arquivos, na ordem das abas |
   |---|---|
   | SCF | `scf.qsub`, `scf_<prefix>.in` |
   | Relax | `relax.qsub`, `relax_<prefix>.in` |
   | VC-Relax | `vc-relax.qsub`, `vc-relax_<prefix>.in` |
   | Bandas | `bands.qsub`, `scf_<prefix>.in`, `bands.in`, `bands_pp.in` (spin: `bands_pp_up.in`, `bands_pp_dw.in`) |
   | PDOS | `pdos.qsub`, `scf_<prefix>.in`, `nscf_<prefix>.in`, `projwfc.in` |

   As saídas têm o mesmo nome com `.out` (o script as escreve: `pw.x -i scf_Al.in > scf_Al.out`).
4. Os templates `.qsub` recebem os nomes como variáveis (ex.: `pw_runs: [(in, out), …]`, `bands_x`, `projwfc`); nenhum
   nome de input fica escrito no `.j2`. `qsub/bandas.qsub.j2` passa a se chamar `qsub/bands.qsub.j2`.
5. Nenhum nome do padrão deixa de ser reconhecido pela detecção: `scf_<prefix>.out` casa `scf*.out`, `bands.in`
   casa `bands*.in`, `nscf_<prefix>.out` casa `nscf*.out` (PRD §3.1). O teste de ida e volta
   (`test_calc_roundtrip.py`) confirma com as saídas das fixtures copiadas com os nomes novos.

### R2: Unidade autossuficiente
1. **outdir:** todo input gerado (pw.x, bands.x, projwfc.x; a cópia do SCF inclusive) usa `outdir = './tmp/'`, nos
   dois modos. A cópia do SCF deixa de ser byte a byte: é o texto com `outdir` trocado pelo `InputEditor`
   (`edits.put_string`; o resto fica idêntico). Os avisos de `outdir` absoluto deixam de valer para a pasta gerada.
2. **pseudo_dir:** chave nova `jobs.pseudo_dir: str | None = None` em `JobsConfig` (o diretório dos
   pseudopotenciais **no cluster**, como `qe_bin`). Com valor, todo input pw.x gerado recebe esse `pseudo_dir`. Sem
   valor, o do SCF fica e a aba "Arquivos" mostra a nota "Defina jobs.pseudo_dir no config.yaml para fixar os
   pseudopotenciais". Documentada nas duas cópias de `config.example.yaml` (idênticas, `test_config.py`).
3. **nk:** chave nova `jobs.nk: int = 4` (`ge=1`) substitui `CalcType.default_nk` como padrão do campo `nk` de
   todos os tipos. `np` continua de `jobs.cores` (64).
4. Caminhos que a unidade não controla (ex.: `wfcdir`, `pseudo_dir` relativo com `..`) geram nota em "Arquivos"
   ("O SCF usa um caminho fora da pasta: …"); nunca bloqueiam.

### R3: Modo no backend
1. `FormField` ganha `standard: bool = False`: o campo aparece no modo Padrão. `Mode = Literal["padrao",
   "avancado"]`.
2. `CalcType.plan(scf, values, jobs, mode="padrao")`: no Padrão, cada campo com `standard=False` usa o seu padrão
   (os valores que o usuário editou no Avançado são ignorados, não apagados: voltar ao Avançado os mostra de novo).
   Um campo **obrigatório sem padrão** (ex.: `nbnd` sem `nbnd` no SCF e sem `X.out` ao lado) aparece nos dois modos.
   `fields(scf, jobs)` não muda de assinatura; a visibilidade é `field.standard or mode == "avancado" or
   (field.required and field.default is None)` em uma função do core (`visible_fields`), não na UI.
3. Campos do Padrão por tipo (os demais só no Avançado):

   | tipo | campos visíveis no Padrão | fixos no Padrão |
   |---|---|---|
   | SCF | nenhum (só a Etapa 1) | malha do SCF |
   | Relax / VC-Relax | nenhum | `nstep`, `forc_conv_thr`, `ion_dynamics` (e `cell_dynamics`, `press`) = padrões de hoje |
   | Bandas | caminho `crystal_b` (digitado; a spec 27-2 removeu a sugestão) | `nbnd` (regra da spec 25), `filband = './band'` (spin `./band_up`, `./band_dw`) |
   | PDOS | `Emin`, `Emax` | malha do NSCF = a do SCF; `nbnd` e `occupations` (regras de hoje); `DeltaE 0.01`, `filpdos '<prefix>.dat'`, `ngauss 0` e `degauss 0.000735` **só quando a ocupação do NSCF não é por tetraedros** (spec 27-1 R3: com tetraedros o par é omitido) |
   | todos | — | `job_name` (do prefix), `np` = `jobs.cores`, `nk` = `jobs.nk` |

4. O padrão de `degauss` do projwfc passa a ser `0.000735` Ry (≈ 0,01 eV) também no Avançado, e o de `filband`,
   `./band`. A regra da spec 27-1 R3 vale nos dois modos: `ngauss`/`degauss` só são escritos com `smearing` ou
   `fixed`.
5. `bands.in` no Padrão: cópia do SCF com `calculation = 'bands'`, `outdir`, `nbnd` e o card `K_POINTS crystal_b` do
   caminho; `occupations` de tetraedros vira `smearing` como hoje (`ensure_smearing`). Nada mais muda.

### R4: Avançado
1. Todos os campos de hoje (specs 25/26), com os padrões de R2/R3.
2. **Nome do arquivo:** cada aba de input ganha o campo "Nome do arquivo" (`kind="text"`, `standard=False`, padrão =
   o nome de R1.3). Validação no core: termina em `.in`, `[A-Za-z0-9._-]`, sem `/`, único na pasta, diferente do
   script; o `.out` acompanha o nome; o `.qsub` usa os nomes escolhidos. O nome do script não é editável.
3. Mudar o nome de um arquivo muda o rótulo da aba e a linha em "Arquivos" no próximo replanejamento.

### R5: Janela
1. Botão alternável **"Padrão / Avançado"** (dois `QToolButton` checáveis exclusivos, ou um segmentado) no topo da
   Etapa 2, à direita. Trocar de modo não reconstrói as abas: `FieldForm.set_mode(mode)` mostra/esconde linhas e a
   prévia replaneja (o mesmo `flush` das edições). Uma aba de arquivo sem campo visível mostra só a prévia (o lado do
   formulário some no `QSplitter`).
2. O modo é lembrado em QSettings `calc_create/mode`; padrão **Padrão** na primeira vez.
3. Etapa 1: "Nome da pasta" deixa de ser obrigatório (rótulo sem `*`, placeholder "opcional, ex.: Al, Fe_teste");
   a prévia do nome mostra `Bands_Al`, ou `Bands` sem nome (e `Bands_1` se já existir).
4. "Descartar o que foi preenchido?" continua valendo para edições em qualquer modo.
5. `ui/` não conhece tipos nem campos: a lista do que aparece vem de `visible_fields` do core.

### R6: `pdos.qsub` (feito na spec 27-1)
A correção do `mv` (`mv *pdos_atm#* orbitals/`, F1 do `report-04-10-26.md`) e a regra de `ngauss`/`degauss` com
tetraedros foram feitas na **spec 27-1**, antes desta. Aqui só se confere, no R1.4, que os nomes de entrada passam a
ser variáveis do template **sem** alterar essas linhas, e os testes de 27-1 (glob do `mv`, ida e volta) continuam
verdes com os nomes novos (`scf_<prefix>.in`, `nscf_<prefix>.in`).

## Fora de escopo
- Tipos de carga (`pp.x`): specs 29 e 30. Projetos: spec 31.
- Renomear pastas ou arquivos já existentes para o padrão, ou avisar quando uma pasta não o segue (pastas como
  `3_Bands_teste` continuam válidas: a detecção é por conteúdo).
- "Gerar SCF convergido" (spec 24) mantém `scf_convergido_<prefix>.in`.
- Editar `outdir` ou o texto livre dos inputs (o usuário escolheu "campos atuais" para o Avançado).
- Tratamento especial de "unidades de simulação" na árvore ou na grade (decisão do usuário: são pastas normais).

## Decisões assumidas (confirmar na revisão)
1. `outdir = './tmp/'` é fixo nos dois modos (é o que torna a pasta autossuficiente); não há campo para ele.
2. `degauss = 0.000735` e `filband = './band'` viram os padrões também no Avançado.
3. `job_name` segue o `prefix` do SCF (como hoje), não o nome da pasta.
4. `jobs.nk = 4` vale para todos os tipos (as referências de relax e PDOS usavam 8; o pedido fixa 4 para bandas e
   PDOS).
5. Com spin, `bands_pp_up.in`/`bands_pp_dw.in` e `filband` `./band_up`/`./band_dw`: a spec 13 pareia os canais
   pelo `spin_component` do input do bands.x, então os nomes curtos funcionam.
6. Relax e VC-Relax no Padrão não mostram campos: só nome e SCF base.
7. O modo é global (um QSettings), não por tipo.

## Notas de implementação
- Core: `types/base.py` (`FormField.standard`, `Mode`, `visible_fields`, `plan(..., mode)`, `script_stem`),
  `types/{scf,relax,vc_relax,bandas,pdos,script,fields}.py` (nomes, `standard=True` nos campos do Padrão, nome do
  arquivo), `writer.py` (`folder_name`, `validate_suffix`), `scf_info.py` (avisos de outdir), `edits.py` se preciso,
  `preview.py` (textos), `core/config.py` (`JobsConfig.pseudo_dir`, `nk`).
- Templates: `qsub/*.qsub.j2` com nomes como variáveis; `qsub/bandas.qsub.j2` → `qsub/bands.qsub.j2`; `pdos.qsub.j2`
  (R1.4; o `mv` já vem corrigido da 27-1).
- UI: `ui/dialogs/calc_create/{dialog,tabs_page,form,setup_page}.py` (cada um < 500 linhas; hoje 230, 223, 137, 259).
- Testes a ajustar: `test_calc_types.py`, `test_calc_templates.py`, `test_calc_writer.py`,
  `test_calc_create_preview.py`, `test_calc_create_dialog.py`, `test_calc_create_ui.py`, `test_calc_roundtrip.py`,
  `tests/calc_helpers.py`, `test_config.py`; `test_sync_push*` e `test_file_grid_menu.py` citam `bandas_` (conferir).
- `CLAUDE.md` ("Criar cálculo" backend/janela) e o status das specs 25/26 citam os nomes antigos: atualizar ao
  implementar.

## Critérios de aceite e testes
- [x] Nomes: cada tipo planeja exatamente os arquivos da tabela R1.3 (prefix `Al` → `scf_Al.in`); `.qsub` com
      `-i "scf_Al.in" > "scf_Al.out"`; nenhum template contém um nome de input literal.
- [x] Pasta: `Bands_Al`; nome vazio → `Bands`; segunda criação → `Bands_1`; `validate_suffix("")` sem erro e
      `validate_suffix("a/b")` com erro.
- [x] outdir `'./tmp/'` em todos os inputs gerados (lint sem erros); `pseudo_dir` = `jobs.pseudo_dir` quando
      definido, o do SCF + nota quando não; diff da cópia do SCF contra o original = só essas linhas.
- [x] Modo: no Padrão, `plan` ignora um valor editado de um campo não-padrão; `visible_fields` por tipo = tabela
      R3.3; `nbnd` obrigatório sem padrão aparece no Padrão; `nk` padrão = `jobs.nk`.
- [x] Bandas Padrão: `bands_pp.in` com `prefix`, `outdir = './tmp/'`, `filband = './band'`; spin → `_up`/`_dw`.
- [x] PDOS Padrão: `projwfc.in` com `DeltaE 0.01`, `Emin`/`Emax` do formulário, `ngauss 0`, `degauss 0.000735`,
      `filpdos '<prefix>.dat'`; malha do NSCF = a do SCF; com NSCF em tetraedros, sem `ngauss`/`degauss` (27-1).
- [x] Avançado: "Nome do arquivo" muda o nome planejado e o `.qsub`; nome repetido, sem `.in` ou com `/` → erro que
      bloqueia "Criar".
- [x] `pdos.qsub`: mantém o `mv *pdos_atm#* orbitals/` da 27-1 com os nomes de entrada variáveis; o glob não casa `projwfc.in`/`projwfc.out` nem `nscf_<prefix>.*`.
- [x] Ida e volta: pastas `Bands_*` e `PDOS_*` com as saídas das fixtures (nomes novos) detectadas como Bandas e PDOS.
- [x] Janela: o botão troca o modo sem reconstruir as abas e sem perder edições; o modo volta após reabrir
      (QSettings isolado do `main_window`); "Continuar" habilitado sem nome de pasta.
- [x] Config: `jobs.pseudo_dir` e `jobs.nk` aceitos, `nk < 1` recusado; as duas cópias de `config.example.yaml`
      idênticas.
- [x] `test_architecture.py`: arquivos < 500 linhas; `ui/` sem nomes de tipo.
