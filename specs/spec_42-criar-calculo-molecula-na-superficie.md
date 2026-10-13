# Spec 42: Criar cálculo — Molécula na superfície (monodentada ou bidentada)

| | |
|---|---|
| **Prioridade** | 42: a última das três de superfície; usa tudo o que a 40 abre e costuma partir do SCF da supercélula (41) relaxada. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 40 (`surface/` inteiro, campo `scf_file`, `molecule_of`, `fixed_atoms`, `put_structure`, `geracao.md`), spec 41 (ordem de uso: o SCF da supercélula relaxada), spec 30 (campo `atoms` e `AtomTable`), spec 21 (`AtomTable` também serve à janela de átomos da PDOS), spec 39 (matriz tipo × SCF, prévia editável) |
| **Usada por** | nenhuma |
| **Esforço** | G (R1: P; R2: M; R3: M; R4: P; R5: M) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): geometria de adsorção (sítio, desprotonação, erguimento, ponte), simetria com spglib (dependência nova), um hook novo na etapa 1 e dados de campo que dependem de outros campos na janela. |

## Itens de origem (`Ideias.md`, 13/10/2026)

> 3. Possiciona uma molecula na superficie da supercelula (usando o a supercelula relaxada)
>
> - Molécula na superficie
>
> [...] e o cálculo da molécula na superficie depender do cálculo da supercelula.
>
> Para o cálculo da molécula na superficie, considere que o usuario está usando um scf de uma superficie relaxada (slab ou supercelula), mas adicione uma validação para caso o usuario confunda e selecione o scf de um bulk.
>
> Os scripts possuem varios parametros que podem ser ajustados para diferentes casos, como bidentados, monodentados, Remove átomos H da superfície para adicionar a molécula, adicionar em um local especificando as coordenadas ou a partir de uma lista de canditados. Adicione todos os parametros dos scripts como parametros configuraveis nas janelas de criação de calculos.

Interpretação: o tipo é o **Estágio 3** dos scripts (`qe_slab_adsorb`), com a lista de candidatos do Estágio 2b
(`qe_slab_candidates`) dentro da janela. "Especificando as coordenadas" é o `site_atom=(x, y, z)` dos scripts: coordenadas
fracionárias que escolhem o átomo mais próximo dentro de uma tolerância, não um ponto livre. Decisões do usuário (13/10/2026):
**uma pasta por criação** (um sítio, ou um par no bidentado; outro sítio = criar de novo) e **spglib como dependência** para
agrupar os candidatos equivalentes.

## Situação atual

- **Os scripts** (`Documentation/Exemplo-SLAB/`, não versionada). `qe_slab_candidates.py`: `top_surface_indices` (`:68-82`:
  átomos a até `height_window` Å do mais alto em z; erro sem O), `find_candidates` (`:85-137`: `SpacegroupAnalyzer(symprec)`
  sobre a estrutura inteira, grupos restritos à janela, um representante por grupo, filtro `site_symbols`), `neighbor_summary`
  (`:50-65`: vizinhos ligados com distância), `frac_for_labels` (`:200-237`: rótulo `O42` → coordenadas; índice **0-based**).
  `qe_slab_adsorb.py`: `anchor_hydrogen` (`:99-142`: o átomo casado precisa ser O com exatamente 1 H ligado, senão
  `RuntimeError`), `adsorb` (`:205-328`: sítio ontop do `AdsorbateSiteFinder` acima do átomo, depois erguido em z até nenhum átomo
  do slab, nas imagens 3×3 do plano, ficar a menos de `distance` do âncora; folgas `< h_clearance` só reportadas),
  `adsorb_bidentate` (`:333-459`: ponto médio dos dois O pela imagem mínima no plano, mesmo erguimento; o "bridge" do
  `AdsorbateSiteFinder` só confere), `generate_adsorbed` (`:464-591`), `generate_adsorbed_bidentate` (`:594-743`),
  `generate_adsorbed_candidates` (`:746-791`, um input por candidato). `Slab.get_surface_sites()` só rotula o método e, medido
  pelo próprio usuário e nesta sessão, devolve vazio ou 2–4 sítios espúrios: a janela de altura é quem decide.
- **Namelists e espécies** (`qe_slab_common.py`): `assemble_namelists` ramo adsorvido (`:187-202`): `calculation = 'relax'`,
  `etot_conv_thr = 1e-04` e `forc_conv_thr = 1e-03` fixos no código (são os padrões do QE: `INPUT_PW.txt` local, `:315-334`),
  `&ions` vazio, sem `&cell`, `nbnd` removido, `occupations`/`smearing`/`degauss` da molécula, `mixing_beta` = o menor dos dois.
  `assemble_species` (`:206-218`): as da superfície e, da molécula, só as que faltam (o H fica com o pseudo da superfície).
  `geometry_checks` (`:329-363`): vácuo ≥ `vacuum_min`, C acima do Hg, algum O a até 3,5 Å do Hg e contato mais próximo ≥ 1,5 Å
  (todos `RuntimeError`). Prefixo `<slab>-<prefixo da molécula>-<rótulo>`; o `scf-H3CHg.in` tem `prefix='silicon'` (`:3`), então o
  script gera `kaolinite-slab-001-2x1x1-silicon-O42`.
- **Parâmetros dos wrappers** (`generate_001_adsorbed.py:22-42`, `generate_001_adsorbed-bidentados.py:33-60`,
  `generate_010_adsorbed.py:16-31`): `VACUUM_MIN` (10.5; 10.0 no bidentado), `ADS_DISTANCE` 2.0, `ASF_HEIGHT` 1.5,
  `HEIGHT_WINDOW` 1.5, `SYMPREC` 1e-3, `H_CLEARANCE` 1.9, `SITE_ATOM_TOL` 0.5, `BOND_SCALE` 1.15, `SITE_SYMBOLS` ("O",),
  `REMOVE_ANCHOR_H` (True no mono e no bidentado do (001), ausente/False no (010)), `LABELS`, `PAIRS`. O docstring do bidentado
  diz `REMOVE_ANCHOR_H=False`, mas o valor é `True`; vale o valor.
- **Reproduzido nesta sessão** (venv temporário com pymatgen 2026.9.24, ase 3.29.0, spglib 2.8.0) sobre
  `scf-kaolinite-slab-001-2x1x1.in` e `scf-H3CHg.in`: candidatos em P1, 24 átomos na janela de 1,5 Å, 3 grupos de O de
  multiplicidade 4 (0-based 40–43, 44–47, 48–51). Mono O42 e O49 (0-based): 72 átomos (67 + 5), H#58 e H#67 removidos, Hg–O
  2,00 Å, erguimento 0, vácuo 11,44 e 11,40 Å, 28/67 fixos, espécies + Hg + C, `smearing = 'gauss'`, `degauss = 0.01`,
  `mixing_beta = 0.3`. Bidentados O42–O45, O42–O49, O43–O45, O43–O49: 71 átomos (66 + 5), erguimentos de 1,08 a 1,44 Å, Hg–O
  2,00–2,03 Å. O (010) não roda: falta `scf-kaolinite-slab-010-2x1x1.in` relaxado.
- **spglib direto = pymatgen.** `spglib.get_symmetry_dataset((cell, frac, tipos), symprec=1e-3).equivalent_atoms` deu os mesmos
  grupos do `SpacegroupAnalyzer` no 2×1×1 (001), na supercélula (010) e no bulk (medido). O spglib não está no ambiente do Lain
  (`pyproject.toml`); o pymatgen saiu na spec 27-2.
- **O Lain hoje.** A etapa 1 só confere se o SCF é lido (`setup_page.py:176`, `_problems`); nada recusa um SCF por ser de outro
  tipo. O campo `atoms` (`types/base.py:151`, `form.py:97-120`) monta a `AtomTable` uma vez, com `FormField.data` fixado quando os
  campos são criados: nenhum campo depende de outro. `ui/widgets/atom_table.py:AtomRow` (`:35`) tem 5 colunas fixas (sem nota).
  `fragments.py:AtomRow` (`:44`) é o equivalente em `core`. `test_calc_create_matrix.py:93-104` exige que todo tipo chegue à etapa
  2 com todo SCF das fixtures. `atom_table.py` 172 linhas, `form.py` 182, `tabs_page.py` 345, `setup_page.py` 277.

## Requisitos

### R1: Validação do SCF na etapa 1 (o bulk por engano)

1. `CalcType.check_scf(scf) -> str | None` (padrão `None`). `SetupPage._problems` acrescenta o texto depois de lido o SCF; ele
   aparece na linha de mensagem do SCF (nível `error`) e na linha de motivo (spec 39), e "Continuar" fica desligado. Trocar de tipo
   reavalia.
2. `surface/geometry.py` (da spec 40): `surface_problem(scf, name) -> str | None`. Sem estrutura: o `structure_problem`. Vácuo ao longo de c
   `< MIN_SURFACE_GAP` e nenhum outro eixo com vácuo: "<nome> parece o SCF de um bulk: não há vácuo ao longo de c (maior intervalo
   vazio: 1,85 Å). Escolha o SCF de uma superfície relaxada (Slab ou Supercélula)." Vácuo só em a ou b: "O vácuo de <nome> está
   ao longo de <a|b>; o Lain espera a superfície com o vácuo ao longo de c, como o Slab gera."
3. O tipo da R5 usa `check_scf = surface_problem`.
4. **Testes:** `tests/test_surface_check.py` (novo): o bulk `scf-kaolinite.in` é recusado com o texto acima (1,85 Å); os SCFs de
   slab e supercélula da fixture passam; um slab com o vácuo em b dá a segunda mensagem. `test_calc_create_dialog.py`: com o tipo
   novo e o bulk, "Continuar" desligado e o motivo na página; trocando para "Slab", liga. `test_calc_create_matrix.py`: um par
   tipo × SCF que `check_scf` recusa passa a esperar o motivo na etapa 1, em vez da etapa 2.

### R2: Candidatos com spglib e a tabela que depende de campos

1. `pyproject.toml`: `spglib>=2.8` (a versão medida), importado só dentro de `surface/candidates.py`.
   `test_perf_detection.py` acrescenta `spglib` aos módulos proibidos no import de `main_window` e do registro.
2. `surface/candidates.py` (novo): `surface_frame(model) -> Frame` (normal `n` = unitário de `a1 × a2` com `n·a3 > 0`; frações em c
   desdobradas cortando no meio do maior intervalo vazio, para o slab ficar contíguo; alturas `h = cart · n`).
   `top_atoms(model, window)` = átomos com `h ≥ max(h) − window`. `candidates(model, species, window, symprec, bond_scale) ->
   tuple[Candidate, ...]`: os átomos da janela cuja espécie (rótulo ou elemento) está em `species`, cada um com `group` (letra
   A, B, C… na ordem do menor índice do grupo), `multiplicity` (membros do grupo na janela) e `neighbors` (`(rótulo, distância)`
   ligados, por distância). Grupos de `spglib.get_symmetry_dataset((cell, frac, tipos), symprec)`, com tipos por **rótulo** (como
   o QE trata espécies), sobre a estrutura inteira, como `find_candidates`. `functools.lru_cache` pelo texto do SCF e pelos
   parâmetros (o `plan` roda a cada edição). Nenhum candidato: lista vazia, e o tipo diz "Nenhum átomo de <espécies> a até <janela> Å
   do topo".
3. Coluna de nota: `fragments.AtomRow` e `ui/widgets/atom_table.AtomRow` ganham `note: str = ""`; `AtomTable` mostra a coluna
   "Sítio" só quando alguma linha tem nota (a janela de átomos da PDOS não muda). Nota de candidato: "A (4) · H 0,97 · Al 1,91 ·
   Al 1,92".
4. Dados que dependem de campos: `FormField.depends_on: tuple[str, ...] = ()` e `CalcType.field_data(field_id, scf, values) ->
   Any` (padrão: o `data` do campo). Depois de cada plano, `TabsPage` compara os valores dos campos de `depends_on` com os da última
   vez e, se mudaram, chama `field_data` e `FieldForm.set_data(field_id, data)`; para `atoms`, `AtomTable.set_rows(rows)` refaz as
   linhas e mantém marcados os átomos que continuam na lista (um `changed` só).
5. **Testes:** `tests/test_surface_candidates.py` (novo): no 2×1×1 (001) da fixture, 24 átomos na janela e os 3 grupos de O do
   golden (`candidates_001`, capturado como na spec 40 R0.2, índices convertidos para 1-based); a janela de 0,5 Å reduz a lista;
   espécies `O H` acrescentam os H; um slab enrolado na borda de c dá a mesma lista. `test_atom_table.py`: coluna "Sítio" só com
   nota; `set_rows` mantém as marcas que sobram. `test_calc_create_dialog.py`: mudar "Janela da superfície" no Avançado refaz a
   tabela.

### R3: Posicionamento (`surface/adsorb.py`, novo)

1. Sítio: `site_atoms(model, values) -> tuple[int, ...]` (1-based). Pela lista: os marcados na tabela; monodentado exige 1
   ("Monodentado: marque um átomo da lista (marcados: 3)"), bidentado exige 2 distintos ("Bidentado: marque dois átomos da
   lista"). Por coordenadas: cada "x y z" (frações) casa com o átomo mais próximo por imagem mínima; acima de `site_tol` é erro
   ("As coordenadas 0,23 0,67 0,58 estão a 0,8 Å do átomo mais próximo (O 43): nenhum átomo a até 0,5 Å"); o átomo precisa estar
   na janela e nas espécies ("O átomo 12 (Si) não está na superfície" / "não é de O"). Os dois átomos do bidentado precisam ser
   distintos.
2. Desprotonação (`remove_h`, porta de `anchor_hydrogen`): para cada átomo âncora, o único H ligado (`bond_scale`) sai antes de
   tudo (antes de posicionar e de contar `n_slab`); 0 ou 2+ H é erro ("O 43 tem 0 H ligados: desmarque 'Remover o H ligado ao átomo
   âncora'"); no bidentado, dois âncoras com o mesmo H é erro. Os índices dos H removidos vão ao relatório (1-based, numeração do
   SCF).
3. Altura do âncora (porta do erguimento): ponto de partida `P` = o átomo (mono) ou o ponto médio do átomo 1 com a imagem do 2 mais
   próxima no plano (bi); para os átomos do slab nas imagens 3×3 do plano a uma distância `r < d` de `P` no plano,
   `t = max(h_P + d [mono] ou h_P [bi], h_j + √(d² − r_j²))`; o âncora fica em `P + (t − h_P)·n`. É o mesmo número do script
   (o ontop do `AdsorbateSiteFinder` é `h_P + d` acima do átomo; snap medido 0,0 Å).
4. Molécula: `molecule_of(scf da molécula, anchor)` (spec 40), coordenadas giradas de `+z` para `n` (identidade quando `n = +z`) e
   transladadas para o âncora; os átomos entram depois dos do slab, na ordem do SCF da molécula; ficam livres (sem flags).
5. Verificações: contato do âncora com o slab `< 1,5 Å` é erro ("O âncora fica a 1,2 Å de O 12: aumente a distância de adsorção");
   folga do âncora aos H do slab ou do resto da molécula ao slab abaixo de `h_clearance` é nota ("Folga abaixo de 1,9 Å: âncora···H
   1,72 Å, molécula–superfície 3,73 Å; o relax ajusta"); vácuo acima da molécula ao longo de c abaixo de `vacuum_min` é nota. As
   verificações do script presas ao Hg/C (C acima do Hg, O a até 3,5 Å) saem: a orientação já é garantida e o sítio pode ser de
   outra espécie.
6. **Testes:** `tests/test_surface_adsorb.py` (novo): mono nos átomos 43 e 50 (O42 e O49 do script) e os quatro pares do script
   (convertidos para 1-based), com remoção de H, contra os goldens `ads_*` (`same_atoms`, 1e-5 Å; erguimentos 0 e 1,08–1,44 Å;
   72 e 71 átomos); coordenadas a 0,3 Å do átomo dão o mesmo resultado que a lista; a 0,8 Å é erro; desprotonar um O sem H é
   erro; distância de adsorção 1,2 Å é erro de contato.

### R4: Namelists e espécies (`surface/merge.py`, novo)

1. Espécies: as linhas de `ATOMIC_SPECIES` da superfície e, da molécula, as dos rótulos que faltam, na ordem dela. Rótulo nos
   dois com pseudo ou massa diferente: nota ("H: vale o pseudopotencial da superfície (H.pbe-kjpaw_psl.1.0.0.UPF)").
2. Namelists a partir do texto da superfície (`work.editor()`): `calculation = 'relax'`; todo `&CELL` removido; `&IONS` presente;
   `nbnd` removido (nota "nbnd removido: o pw.x calcula o padrão para o sistema com a molécula"); quando o SCF da molécula define
   `occupations`, ele e os `smearing`/`degauss` que a molécula tiver substituem os da superfície; `mixing_beta` = o menor dos dois
   quando os dois têm; `tot_charge` da superfície fica.
3. Notas de diferenças entre os dois SCFs, só informativas: `ecutwfc`/`ecutrho` maiores na molécula, `vdw_corr`, `input_dft`
   ou `nspin` diferentes (no caso do usuário: "vdw_corr: superfície 'grimme-d3', molécula 'grimme-d2'; vale o da superfície").
4. `prefix = '<prefixo da superfície>-<fórmula da molécula>-<rótulo>'`: fórmula na ordem dos átomos (`HgCH3`), rótulo `O43`
   ou `O43-O46` (1-based, crescente).
5. **Testes:** em `tests/test_calc_adsorption.py` (novo, R5): espécies `Al Si O H Hg C` (só os rótulos usados), `smearing = 'gauss'`,
   `degauss = 0.01`, `mixing_beta = 0.3`, sem `nbnd` nem `&CELL`, nota do `vdw_corr`, `prefix` com `HgCH3`.

### R5: Tipo "Molécula na superfície"

1. `types/adsorption.py` (novo): `AdsorptionType(RelaxType)`, `id = "adsorption"`, `label = "Molécula na superfície"`,
   `folder_prefix = "Adsorption"`, `script_stem = "adsorption"`, `script_template = "qsub/relax.qsub.j2"`,
   `scf_label = "SCF da superfície"`, `check_scf` da R1. Registrado depois de "Supercélula". Arquivos: script,
   `relax_<prefixo da superfície>.in` (chave `relax`, rótulo "Molécula na superfície") e `geracao.md`.
2. Aba `"Molécula"`. Padrão: `molecule` "SCF da molécula *" (`scf_file`, obrigatório). Avançado: `anchor` "Átomo âncora (nº na
   molécula)" (`int`, "vazio = o mais pesado"), `ads_distance` "Distância de adsorção (Å)" (2.0), `h_clearance` "Folga mínima (Å)"
   (1.9), `vacuum_min` "Vácuo mínimo (Å)" (10.5; só verifica).
3. Aba `"Sítio"`. Padrão: `mode` "Coordenação" (`choice`: "monodentado", "bidentado"), `site` "Átomo âncora na superfície"
   (`atoms`, a tabela de candidatos; dica: "Monodentado: marque um átomo. Bidentado: marque dois. Mesma letra = sítios
   equivalentes por simetria"; `depends_on = ("site_species", "height_window", "symprec", "bond_scale")`), `remove_h` "Remover o
   H ligado ao átomo âncora" (desligado). Avançado: `site_from` "Escolher o sítio por" ("lista de candidatos", "coordenadas"),
   `coords_1` / `coords_2` "Coordenadas do átomo 1 / 2 (crystal)" (`text`, "x y z"), `site_tol` "Tolerância das coordenadas (Å)"
   (0.5), `site_species` "Espécies candidatas" ("O"), `height_window` "Janela da superfície (Å)" (1.5; vale para a lista e para
   aceitar o átomo, como `ASF_HEIGHT = HEIGHT_WINDOW` nos scripts), `symprec` "Tolerância de simetria (Å)" (0.001), `bond_scale`
   (1.15).
4. Aba do input: `nstep`, `ion_dynamics`, `forc_conv_thr` (padrão 1e-3) e `etot_conv_thr` "Convergência da energia
   (etot_conv_thr)" (padrão 1e-4), os valores que o script fixa e o QE usa por padrão, **sem** herdar os do SCF; `kmesh` (o
   `kmesh_field` de hoje: a malha da superfície, a célula não muda); `fix_rule` (as quatro de `FIX_RULES`; padrão "do SCF" quando a
   superfície tem flags, senão "camada inferior") e os campos da regra, só sobre os átomos do slab.
5. `plan`: R3 → `fixed_atoms(..., n_slab)` → `put_structure` → R4 → `RelaxType.edit` + `etot_conv_thr`. Um erro de R3 vai ao
   campo que o causa (`site`, `coords_1`, `coords_2`, `remove_h`, `molecule`, `ads_distance`).
6. `geracao.md`: SCF da superfície e da molécula, coordenação, átomo(s) âncora (número, espécie, coordenadas, grupo), H removidos,
   átomos (slab + molécula, por espécie), posição do âncora e erguimento, distâncias âncora–sítio, folgas, vácuo acima da molécula,
   fixos (n/N do slab, regra), k-points.
7. **Testes:** `tests/test_calc_adsorption.py` (novo): o plano reproduz os goldens mono e bidentado (estrutura, 28 fixos do slab
   por "do SCF" e pela regra, k `3 4 1`, `calculation = 'relax'`, `etot_conv_thr = 1e-4`, `forc_conv_thr = 1e-3`); sem molécula,
   "Preencha SCF da molécula"; sem átomo marcado, o erro no campo `site`; o input passa no `lint`; Padrão mostra `molecule`, `mode`,
   `site` e `remove_h`. `test_calc_roundtrip.py` ganha a linha do tipo (detectado como relax). Marca `perf`: `plan` no 2×1×1 (68
   átomos) abaixo de 100 ms depois da primeira chamada (cache).

## Fora de escopo

- Várias pastas numa criação (os `LABELS`/`PAIRS` dos scripts): decisão do usuário, uma pasta por criação.
- Posição livre (hollow, bridge escolhido por coordenada, altura dada): os scripts só põem sobre um átomo ou entre dois.
- Tridentado ou mais átomos âncora; adsorção na face de baixo (dá para gerar o slab invertido na spec 40).
- Orientação da molécula escolhida pelo usuário (inclinação, giro em torno do eixo): o eixo âncora→resto vai na normal.
- O `.cif` e o relatório `candidatos-<hkl>.md` separado: a tabela da janela e o `geracao.md` fazem esse papel.

## Decisões assumidas (confirmar na revisão)

1. **Rótulos 1-based** (O43 = o "O42" dos scripts), como o QE, o VESTA e a tabela de átomos do Lain.
2. **Fórmula da molécula no prefixo** (`HgCH3`), não o `prefix` do SCF dela (o do usuário é `silicon`, sobra de outra conta).
3. **"Remover o H" desligado por padrão** (os scripts ligam no (001) e desligam no (010)); ligado num O sem H é erro com o motivo.
4. **Limites de convergência do script** (`etot` 1e-4, `forc` 1e-3) como padrão, não os do SCF da superfície.
5. **Uma janela só** para a lista e para aceitar o átomo (os scripts têm `ASF_HEIGHT` e `HEIGHT_WINDOW`, sempre iguais).
6. **Folga e vácuo baixos são notas** (o script reporta a folga e para no vácuo); contato `< 1,5 Å` continua erro.
7. **O SCF com vácuo fora de c é recusado** (o Slab do Lain e os scripts sempre põem o vácuo em c).
8. Pasta `Adsorption`, script `adsorption.qsub` sobre o template do relax.

## Notas de implementação

- Novos: `core/calc_create/surface/{candidates,adsorb,merge}.py`, `core/calc_create/types/adsorption.py`,
  `tests/test_surface_check.py`, `tests/test_surface_candidates.py`, `tests/test_surface_adsorb.py`,
  `tests/test_calc_adsorption.py`; casos `candidates_001` e `ads_*` em `tests/surface_golden.json`.
- Alterados: `pyproject.toml` e `uv.lock` (spglib), `types/base.py` (`check_scf`, `depends_on`, `field_data`),
  `types/__init__.py`, `surface/geometry.py` (`surface_problem`), `fragments.py` e `ui/widgets/atom_table.py` (`note`, `set_rows`),
  `ui/dialogs/calc_create/form.py` (`set_data`), `tabs_page.py` (dados dependentes), `setup_page.py` (`check_scf`),
  `test_calc_create_matrix.py`, `test_perf_detection.py`, `test_architecture.py` (`QT_FREE`), `test_calc_roundtrip.py`.
- Ordem: R2 (candidatos e tabela) → R3 → R4 → R1 → R5.
- Limites: `tabs_page.py` (345) ganha só o laço dos `depends_on`; se passar de ~400, o laço vai para um módulo próprio.
- Documentação: `CLAUDE.md`, "'Criar cálculo' backend" (tipo, spglib e a regra de import tardio) e "'Criar cálculo' window"
  (`check_scf`, `depends_on`, coluna "Sítio"); `README.md` (dependências); `specs/README.md`, decisão sobre o spglib.

## Critérios de aceite e testes

- [ ] Os tipos de hoje, Slab e Supercélula não mudam; a janela de átomos da PDOS não mostra coluna nova (`test_atom_table.py`,
      `test_atoms_dialog.py`).
- [ ] O SCF de um bulk é recusado na etapa 1 com o motivo na página (`test_surface_check.py`, `test_calc_create_dialog.py`).
- [ ] Lista de candidatos com os grupos do spglib, refeita quando muda a janela, as espécies, a simetria ou a ligação.
- [ ] Mono e bidentado iguais aos goldens dos scripts, com remoção de H (`test_surface_adsorb.py`, `test_calc_adsorption.py`).
- [ ] Por coordenadas, mesmo resultado que pela lista; fora da tolerância, erro no campo.
- [ ] `spglib` e `ase` não carregam com `main_window` nem com o registro (`test_perf_detection.py`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
