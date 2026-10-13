# Fluxo de geração de entradas de slab — caulinita (001)/(010), três estágios

Geração de entradas `pw.x` do Quantum ESPRESSO para modelos de slab de
caulinita, seguindo as escolhas de modelagem de Guo *et al.*, "Atomic-Scale
Insights into Methylmercury Complexation on Clay Mineral: A Density Functional
Study", *ACS Earth Space Chem.* 2025, 9, 2548–2557 (`Literatura/`).

O fluxo é dividido em **três estágios**, cada um com seu próprio módulo, sobre
um núcleo compartilhado:

| módulo | estágio | entrada de referência | saída |
|---|---|---|---|
| `qe_slab_common.py` | núcleo compartilhado (E/S, propagação de parâmetros, k-mesh, constrangimentos, verificações) | — | — |
| `qe_slab_surface.py` | **1 — superfície** pura, aumentando a altura da caixa | `scf-kaolinite.in` (bulk) + `scf-H3CHg.in` | `surface_pure/<hkl>/vc-relax-*.in` |
| `qe_slab_supercell.py` | **2 — supercélula** 2×1×1 da superfície relaxada | `scf-kaolinite-slab-<hkl>.in` | `surface_pure/<hkl>/supercell/vc-relax-*-2x1x1.in` |
| `qe_slab_candidates.py` | **2b — candidatos**: átomos de superfície não-equivalentes da supercélula relaxada | `scf-kaolinite-slab-<hkl>-2x1x1.in` | `candidatos-<hkl>.md` |
| `qe_slab_adsorb.py` | **3 — adsorção** de H3CHg na supercélula relaxada, um input por candidato O | `scf-kaolinite-slab-<hkl>-2x1x1.in` + `scf-H3CHg.in` | `surface_with_methylmercury/<hkl>/<label>/relax-*.in` |

Cada módulo de estágio faz `from qe_slab_common import ...`. Os wrappers finos
`generate_surface.py`, `generate_001_supercell.py`, `generate_010_supercell.py`,
`generate_001_candidates.py`, `generate_010_candidates.py`,
`generate_001_adsorbed.py` e `generate_010_adsorbed.py` são os pontos de
entrada.

## Por que três estágios

Corrige um método anterior que cortava um slab do bulk ainda não relaxado e
relaxava imediatamente a célula dobrada (2×1×1, 68 átomos):

1. **Estágio 1 — superfície.** A superfície pura é feita a partir da célula
   bulk `scf-kaolinite.in` *simplesmente aumentando a altura da caixa*: o
   vetor de rede fora do plano é multiplicado por um escalar para abrir vácuo
   ao longo da normal da superfície. Essa célula única é relaxada sozinha
   (`vc-relax`) — bem mais barato que relaxar a supercélula.
2. **Estágio 2 — supercélula.** Só *depois* que o Estágio 1 converge é que a
   superfície **relaxada** é replicada na supercélula 2×1×1 (teto
   computacional rígido) e relaxada de novo (`vc-relax`, `cell_dofree =
   '2Dxy'`, camada da base fixa — mesmo padrão do Estágio 1).
3. **Estágio 3 — adsorção.** Só *depois* que o Estágio 2 é relaxado é que o
   metilmercúrio é posicionado na supercélula **relaxada** — um input por átomo
   de O de superfície simetricamente não-equivalente (candidatos enumerados por
   `qe_slab_candidates.py`) — e cada complexo é otimizado (`relax`, célula
   fixa) para obter a geometria de adsorção.

O usuário conduz a ordem manualmente:

```bash
python3 generate_surface.py                     # Estágio 1 -> surface_pure/001,/010 (vc-relax)
#   ... relaxe cada vc-relax com pw.x até convergir, depois produza
#   scf-kaolinite-slab-001.in / scf-kaolinite-slab-010.in na raiz do repo
python3 generate_001_supercell.py               # Estágio 2 -> .../supercell/ (vc-relax)
python3 generate_010_supercell.py
#   ... relaxe cada supercélula, depois produza
#   scf-kaolinite-slab-001-2x1x1.in / -010-2x1x1.in na raiz do repo
python3 generate_001_candidates.py              # Estágio 2b -> candidatos-001.md (relatório, opcional)
python3 generate_010_candidates.py
python3 generate_001_adsorbed.py                # Estágio 3 -> surface_with_methylmercury/001/<label>/ (relax, um por candidato O)
python3 generate_010_adsorbed.py
```

Todo parâmetro físico/numérico é relido de entradas de referência validadas a
cada execução — nada físico é hardcoded — então regenerar depois de uma
reverificação de convergência é uma operação de um único comando. Bibliotecas:
pymatgen (estrutura, supercélula, adsorção) e ASE (`ase.io.espresso` para toda
leitura/escrita do QE, mais a tabela de raios covalentes para os
constrangimentos de camada e a coordenação de borda).

## Arquivos gerados

**Estágio 1 — superfície (`vc-relax`, uma célula bulk + vácuo):**

| sistema | entrada | átomos | fixos | célula \|a\|,\|b\|,\|c\| (Å) | fora do plano | k-mesh | vácuo (Å) |
|---|---|---|---|---|---|---|---|
| (001) | `surface_pure/001/vc-relax-kaolinite-slab-001.in` | 34 | 14 (4 Si + 10 O) | 5.184 × 8.998 × 21.128 | 2.8602 · **c** | 6 4 1 | 15.10 |
| (010) | `surface_pure/010/vc-relax-kaolinite-slab-010.in` | 40 | 18 (2 Al, 2 Si, 10 O, 4 H) | 5.184 × 7.387 × 26.420 | 2.9361 · **b** | 6 4 1 | 15.10 |

**Estágio 2 — supercélula 2×1×1 (`vc-relax`, a partir da referência já
relaxada, camada da base fixa):**

| sistema | entrada | átomos | fixos | célula \|a\|,\|b\|,\|c\| (Å) | k-mesh |
|---|---|---|---|---|---|
| (001) | `surface_pure/001/supercell/vc-relax-kaolinite-slab-001-2x1x1.in` | 68 | 28 (8 Si + 20 O) | 10.368 × 8.998 × 21.128 | 3 4 1 |
| (010) | `surface_pure/010/supercell/vc-relax-kaolinite-slab-010-2x1x1.in` | 80 | 36 (4 Al, 4 Si, 20 O, 8 H) | 10.368 × 7.387 × 26.4 | 3 4 1 |

**Estágio 3 — H3CHg adsorvido (`relax` de célula fixa, a partir da
supercélula 2×1×1 relaxada; um input por candidato O não-equivalente):**

| sistema | entradas | átomos | modo | k-mesh |
|---|---|---|---|---|
| (001) | `surface_with_methylmercury/001/<label>/relax-kaolinite-slab-001-2x1x1-H3CHg-<label>.in` — O40, O42, O44, O46, O48, O50 | 72 (67+5) | ontop de cada O candidato, hidroxila âncora desprotonada | 3 4 1 |
| (010) | `surface_with_methylmercury/010/<label>/relax-kaolinite-slab-010-2x1x1-H3CHg-<label>.in` | 85 (80+5) | ontop de cada O candidato | 3 4 1 |

(As dimensões/contagens do (010) nos Estágios 2/3 valem depois que
`scf-kaolinite-slab-010.in` carrega a geometria relaxada da nova superfície de
40 átomos; até lá refletem a superfície ainda não relaxada. |a| é sempre 2× o
valor da superfície.) Uma prévia `.cif` e um resumo `.md` acompanham cada `.in`.

## Estágio 1 — superfície (`qe_slab_surface.generate_surface`)

### 1. Leitura das referências (ASE `ase.io.espresso`)
`load_ref` (em `qe_slab_common`) lê as entradas: `read_fortran_namelist` →
`&control/&system/&electrons/&cell` como dicts tipados; `read_espresso_in` →
a estrutura bulk da caulinita como `Atoms`, convertida para pymatgen;
`get_atomic_species` → `ATOMIC_SPECIES` literalmente (massas + UPF);
`get_atomic_positions` → a geometria do H3CHg (só para a extensão em z da
molécula); `K_POINTS automatic` (`6 4 4 0 0 0`). De `scf-kaolinite.in`:
`ecutwfc = 70`/`ecutrho = 560`, `vdw_corr = 'grimme-d3'`,
`occupations = 'fixed'`, `nbnd = 90`, `conv_thr`, `mixing_beta`,
`pseudo_dir = '/home/alumni/mariano/PSEUDO/'`, prefix, k-mesh.

### 2. Aumento da altura da caixa — superfície sem SlabGenerator (`make_surface`)
A superfície é a célula bulk com o vetor bulk fora do plano esticado; nenhum
slab é cortado. Eixos no plano / de empilhamento lidos da célula bulk:

- **(001):** no plano {**a**, **b**}, empilhamento **c**. A fronteira da célula
  bulk já está no gap interlamelar — os átomos cobrem frac-**c** ≈
  −0.006…0.736 — então abrir vácuo ao longo de **c** reproduz o **clivamento
  basal natural de 0 ligações quebradas** (Al–OH em cima, siloxano embaixo, o
  modelo Kln(001) do artigo) sem nenhuma busca de terminação.
- **(010):** no plano {**a**, **c**}, empilhamento **b** (o eixo **y** do
  bulk). O segundo vetor no plano é tomado como **−c** (`t1_sign = −1`): isso
  **reverte a normal da superfície** de modo que a **borda octaédrica de Al
  fique exposta em +z** (topo, lado do vácuo/adsorbato) e a borda tetraédrica
  de Si fique para baixo — a orientação pedida ("octaedros para cima,
  tetraedros para baixo"). É uma reindexação **própria** (célula destrógira
  preservada, sem espelhar o cristal triclínico), verificada mantendo volume
  positivo e as linhas no plano com z = 0.

**Esticamento escalar (ideia.md §4).** A linha fora do plano é o vetor de
empilhamento bulk **multiplicado por um escalar real f** — nunca um incremento
vertical `(0,0,z)`. `f` é dimensionado para que o vácuo perpendicular acima da
camada seja igual ao orçamento reservado (15.10 Å):

| sistema | fora do plano | f | célula \|c\| (Å) |
|---|---|---|---|
| (001) | f · **c** | 2.8602 | 21.128 |
| (010) | f · **b** | 2.9361 | 26.420 |

**Orientação.** A célula é rotacionada rigidamente (`_ortho_frame`) para que a
normal seja exatamente Cartesiana **+z** (linhas no plano têm z = 0),
necessário para que `cell_dofree = '2Dxy'` signifique "no plano relaxa, vácuo
fixo".

### 2b. Cura das hidroxilas de borda (`heal_cut_hydroxyls`)
Abrir o vácuo esticando um vetor bulk rompe qualquer ligação O–H cuja imagem
mínima cruza a fronteira 0/1 do eixo de empilhamento, deixando o H perdido a
~2–3 Å do seu O. Para cada uma, o H é movido para junto do seu próprio O
parceiro ao longo do vetor O→H nativo do bulk (~0.97 Å) do lado do vácuo.
Nenhum átomo é adicionado ou removido. Para o **(001)** o clivamento basal não
rompe nenhuma ligação O–H (no-op); para o **(010)** cura `H26–O18` (0.974 Å) e
`H31–O23` (0.971 Å).

### 2c. Completação dos poliedros de borda (`complete_edge_metals`, só (010))
O corte de vácuo ao longo de **b** também rompe ligações **metal–O** cuja
imagem mínima cruza a fronteira 0/1, deixando um metal de borda sub-coordenado
(Al 4 em vez de 6; Si 3 em vez de 4). No bulk são três ligações: `Al1` perde
`O11` (2.04 Å) e `O20` (1.87 Å); `Si5` perde `O13` (1.64 Å). Após a inversão
`t1 = −c`, esses metais ficam expostos em **+z**. Para cada ligação metal–O
rompida (tanto Al quanto Si):

- um **novo O** é adicionado exatamente no vértice que faltava —
  `O_new = cart[M] + (frac[O] − frac[M] + img) · lattice` — a mesma matemática
  de vetor da cura, mas **criando um átomo novo** em vez de mover um existente,
  fechando o poliedro na direção real do bulk (que aponta para o vácuo);
- um **H** é adicionado a esse O, colinear com M–O apontando para fora (a
  ~comprimento O–H médio do bulk, medido em tempo de execução — nada
  hardcoded) → **Al–OH** (aluminol) / **Si–OH** (silanol) protonado.

Resultado: **34 → 40 átomos** (4 Al, 4 Si, **21 O**, **11 H**): +3 O e +3 H
(2 aluminois + 1 silanol). Os quatro Al ficam 6-coordenados e os quatro Si
4-coordenados; os O novos ficam a 1.87/2.04 Å do Al1 e 1.64 Å do Si5, a 0.97 Å
do seu H, no topo (+z, z ≈ +3.1…+4.6 Å). Nenhuma espécie nova é introduzida,
então `ATOMIC_SPECIES` é preservado e `nat` é derivado pelo escritor. A face O
inferior fica fixa (proxy do bulk); a borda superior (aluminol + silanol) relaxa.

### 3. Orçamento de vácuo — espaço da molécula reservado agora (ideia.md §3)
O teste de convergência de caixa do H3CHg fixou 10.5 Å de espaço livre mínimo. As
caixas puras já reservam o orçamento completo:

> vácuo = 10.50 (mínimo) + 2.60 (extensão em z da molécula, de `scf-H3CHg.in`) +
> 2.00 (distância de posicionamento) = **15.10 Å**

Ambas as superfícies têm gap perpendicular de 15.10 Å (a extensão do (010) é
medida acima do H do novo aluminol, o átomo mais externo).

### 4. Reescalonamento de k-points (regra, não cópia)
Cada eixo herda a subdivisão bulk (`6 4 4`) do eixo bulk do qual deriva; o eixo
de vácuo recebe 1: (001) **6 4 1**; (010) **6 4 1** (o eixo 1 no plano deriva
do **c** do bulk, k_c = 4 — a inversão de sinal não muda o `axis_map`).

### 5. Configuração do vc-relax
`calculation = 'vc-relax'`; `&ions` vazio; `&cell` (`cell_dynamics = 'bfgs'`)
mais **`cell_dofree = '2Dxy'`** (só a célula no plano relaxa; a altura de vácuo
não pode encolher); `nbnd = 90` (não escalado — célula única).

### 6. Dinâmica seletiva — constrangimentos de camada do artigo (`fixed_indices`)
Emitido como `if_pos = 0 0 0` via `FixAtoms` do ASE; nenhum índice à mão:

- **(001):** fixos = todo Si + todo O ligado a um Si (folha tetraédrica
  basal-O/Si/O-apical): **14 de 34**; a parte octaédrica Al–O–H relaxa.
- **(010):** fixos = átomos abaixo do plano médio do slab ao longo da normal:
  **18 de 40** (2 Al, 2 Si, 10 O, 4 H); as unidades de borda superior expostas
  (o aluminol Al–OH e o silanol Si–OH completados) relaxam.

## Estágio 2 — supercélula 2×1×1 (`qe_slab_supercell.generate_supercell`)

Roda depois que o Estágio 1 converge, e lê **só** `SLAB_REF[miller]`
(`scf-kaolinite-slab-<hkl>.in`): a superfície **já relaxada**. `scf-kaolinite.in`
(bulk) não é mais lido nesta etapa.

- **Geometria e todo parâmetro** vêm de `load_ref(SLAB_REF[miller], ...)`.
- **2×1×1** via `struct.make_supercell([2,1,1])` — dobra a linha 0 (sempre o
  vetor no plano derivado do **a** do bulk por construção do Estágio 1) →
  68 átomos (001) / 80 átomos (010, depois do refresh da referência).
- **K-mesh** reescala a própria malha da referência: (6/2, 4, 1) → **3 4 1**.
- **`calculation = 'vc-relax'`, `nbnd = 180`** (90 × 2); `&ions` vazio +
  `&cell` (`cell_dofree = '2Dxy'`) — mesmo padrão do Estágio 1: só a célula
  no plano relaxa, o vácuo reservado não pode encolher.
- **Dinâmica seletiva** (`fixed_indices`, mesma regra do Estágio 1)
  recalculada diretamente na estrutura já dobrada — não reutiliza os
  índices `if_pos` herdados da referência do Estágio 1 (não corresponderiam
  à supercélula): **(001)** 28/68 (8 Si + 20 O); **(010)** 36/80 (4 Al, 4
  Si, 20 O, 8 H) — exatamente o dobro das contagens do Estágio 1, já que a
  supercélula só duplica a linha 0 no plano.
- A referência do Estágio 1 já vem com a normal em +z (escrita sob `2Dxy`),
  então `read_espresso_in` devolve a célula com a normal ainda em +z — nenhuma
  reorientação é necessária.

## Estágio 2b — candidatos (`qe_slab_candidates`)

`find_candidates` enumera os átomos de superfície do topo da supercélula
relaxada (janela de altura de 1.5 Å ao longo de +z) e os agrupa por
equivalência simétrica (`SpacegroupAnalyzer`/spglib, `symprec = 1e-3` Å) —
dois átomos que só diferem pela translação da duplicação 2×1×1 caem no mesmo
grupo. `generate_00X_candidates.py` escreve o relatório `candidatos-<hkl>.md`
(label, coordenada fracionária, vizinhos ligados); o Estágio 3 consome a mesma
enumeração diretamente (fonte única, nada é parseado do `.md`).

A janela de altura substitui `Slab.get_surface_sites()` porque, **medido**
nestes slabs, o CN Voronoi ponderado dos átomos expostos *sobe* em vez de cair
vs. o bulk e a busca devolve vazio — limitação documentada do pymatgen (ver
docstring de `qe_slab_candidates.py`).

## Estágio 3 — H3CHg adsorvido (`qe_slab_adsorb.generate_adsorbed_candidates`)

Roda depois que o Estágio 2 é relaxado, e lê `SLAB_2X1X1_REF`
(`scf-kaolinite-slab-<hkl>-2x1x1.in`): a supercélula **já relaxada**. Todos os
cutoffs/pseudos/k-mesh/célula vêm dessa referência. Para **cada** candidato O
não-equivalente (Estágio 2b; filtro `SITE_SYMBOLS = ("O",)` — o Hg ancora em O,
base de Lewis, como no artigo) um par `.in`/`.cif`/`.md` é emitido em
`surface_with_methylmercury/<hkl>/<label>/` (subdiretório por sítio, para os
`outdir = './tmp'` do QE não colidirem).

- **Molécula.** `build_molecule` lê `scf-H3CHg.in` e orienta a molécula com o
  átomo âncora (Hg, o mais pesado) na origem e o eixo Hg→C ao longo de +z
  (ligação **Hg-down**, grupo metila para longe da superfície, como no artigo).
- **Slab pymatgen.** `slab_from_ref` embrulha a supercélula relaxada como um
  `pymatgen.core.surface.Slab` com a normal em +z (`reorient_lattice=False`).
  O bulk `scf-kaolinite.in` é passado como `oriented_unit_cell` (template de
  coordenação para `Slab.get_surface_sites()`) — nenhum parâmetro físico vem
  dele.
- **Desprotonação da hidroxila âncora (só (001), `remove_anchor_h`).** Antes
  de embrulhar o slab e contar `n_slab`, o único H ligado ao O âncora é
  removido (`anchor_hydrogen` → `Structure.remove_sites`), modelando
  superfície–O–H + CH3Hg⁺ → superfície–O–HgCH₃ + H⁺ (o Hg substitui o próton).
  Se o O âncora não tiver exatamente 1 H ligado o gerador aborta o sítio
  (`RuntimeError` — decisão do usuário). A célula permanece **neutra**:
  `tot_charge` vem da referência do slab (= 0), não da molécula, e remover um H
  neutro + anexar o fragmento CH3Hg neutro descreve o complexo neutro. Slab do
  (001): 68 → **67 átomos** (15 H). O (010) fica protonado (flag desligado).
- **Posicionamento (`pymatgen.analysis.adsorption`).**
  `Slab.get_surface_sites()` é tentada primeiro para identificar os átomos de
  superfície; como devolve vazio para este sistema (ver Estágio 2b), o
  fallback documentado é a mesma janela de altura do `AdsorbateSiteFinder`.
  `AdsorbateSiteFinder.find_adsorption_sites(distance=2.0, symm_reduce=0)`
  devolve um sítio **ontop exatamente acima de cada átomo de superfície**
  (snap medido: ~0.002 Å no plano); o ontop do átomo candidato é usado. O
  ponto é então **erguido ao longo de +z** até nenhum átomo do slab ficar a
  menos de 2.0 Å do Hg. No (001) desprotonado o H ereto do O âncora não existe
  mais, então o erguimento nesse sítio é nulo e o Hg parte de **~2.0 Å do O**;
  o mecanismo de erguimento segue ativo (protege contra qualquer outro átomo no
  caminho vertical). Folgas Hg···H / CH3···slab < 1.9 Å são só reportadas
  (`clearance_ok`), nunca contornadas trocando o sítio do usuário. A posição é
  um chute inicial que o `relax` refina.
- **Namelists.** `calculation = 'relax'` + `&ions` vazio, **sem**
  `cell_dynamics`/`cell_dofree` em `&cell` — célula fixa, herdada intacta da
  referência 2×1×1 (decisão do usuário; só adsorbato e átomos de superfície
  livres relaxam); `occupations/smearing/degauss` da referência da molécula
  (o adsorbato pode fechar o gap); `mixing_beta` = o menor das duas
  referências; `nbnd` descartado (padrão do QE).
- **Espécies.** As da supercélula literalmente + as da molécula ainda ausentes
  (**Hg, C**). O H fica unificado ao pseudopotencial da caulinita. Os UPF
  `Hg.pbe-spn-kjpaw_psl.1.0.0.UPF` e `C.pbe-n-kjpaw_psl.1.0.0.UPF` precisam
  estar presentes em `pseudo_dir`.
- **Constrangimentos.** `fixed_indices` com `n_slab` = só os átomos do slab
  (o adsorbato, anexado depois, fica livre) → a mesma camada inferior fixa da
  superfície pura.
- **K-mesh** carregado da referência 2×1×1 (**3 4 1**) — a célula não muda.

## Escrita das entradas (ASE `write_espresso_in`)
`crystal_coordinates=True`: `ibrav = 0`, `CELL_PARAMETERS angstrom`,
`ATOMIC_POSITIONS crystal`, `nat`/`ntyp` derivados da estrutura, massas via
`atoms.set_masses()`, UPF via `pseudopotentials`, `K_POINTS automatic`,
`if_pos` a partir de `FixAtoms`. Cosmético: o ASE escreve namelists em
maiúsculas e emite `&FCP`/`&RISM` vazios — o `pw.x` os ignora.

## Regras de propagação de parâmetros (`assemble_namelists`)

| item | E1 (superfície, de `scf-kaolinite.in`) | E2 (supercélula, de `-slab-<hkl>.in`) | E3 (adsorvido, de `-2x1x1.in`) |
|---|---|---|---|
| `calculation` | `'vc-relax'` | `'vc-relax'` | `'relax'` |
| `prefix` | `kaolinite-slab-<hkl>` | `…-2x1x1` | `…-2x1x1-H3CHg-<label>` |
| `pseudo_dir` | da caulinita | igual (da ref. relaxada) | igual (da ref. 2×1×1) |
| `nbnd` | 90 (×1) | 180 (×2) | descartado (padrão) |
| `&ions` / `&cell` | `&ions` + `&cell` (`2Dxy`) | `&ions` + `&cell` (`2Dxy`) | `&ions` só (célula fixa) |
| `occupations` | `'fixed'` (caulinita) | igual | `'smearing'`/`degauss` (molécula) |
| `ATOMIC_SPECIES` | caulinita (Al,Si,O,H) | igual | + Hg, C (molécula) |
| `K_POINTS` | 6 4 1 | 3 4 1 | 3 4 1 (da ref.) |
| `if_pos` | constrangimentos do artigo | mesma regra, recalculada na supercélula | mesma camada inferior do slab |

## Limitações / escolhas deliberadas

- **Dimensão lateral do (010) 7.39 Å < 10.5 Å**: a supercélula 2×1×1 é um teto
  rígido; o critério de 10.5 Å é honrado na direção do vácuo, mas as imagens
  laterais ficam a ~7.4 Å ao longo do eixo bulk-**c** no plano.
- **Contagem de átomos do (010) acima de 68**: completar os poliedros de borda
  com O + H (Al–OH + Si–OH) adiciona 6 átomos por célula → superfície de 40
  átomos, supercélula 2×1×1 de **80** (85 com o adsorbato). Isso ultrapassa a
  nota antiga de 68 átomos, uma consequência aceita da terminação de borda
  totalmente hidroxilada pedida.
- **Borda do (010) totalmente hidroxilada (Al–OH + Si–OH).** Os octaedros de Al
  (aluminol) e o tetraedro de Si de borda (`Si5`, silanol) são fechados e
  protonados; só a face O inferior fixa (proxy do bulk) fica não hidroxilada.
- **Slab puro (001) mantido protonado e inalterado** (Estágios 1–2 regeneram
  byte-a-byte idênticos à versão anterior). **Só o O âncora do complexo
  adsorvido (Estágio 3) é desprotonado** — o H da hidroxila desse O é removido
  antes da adsorção (só (001)); as demais hidroxilas ficam intactas.
- **Estágio 2 é `vc-relax`** (mesmo padrão do Estágio 1: célula no plano
  relaxa, vácuo/camada da base fixos); **Estágio 3 é `relax` de célula
  fixa** (herdada intacta da referência 2×1×1 — decisão do usuário: só
  adsorbato e átomos de superfície livres relaxam, a célula não muda).
- **Chute inicial ontop erguido**: com a hidroxila âncora do (001) desprotonada
  (H ereto removido), o Hg parte de **~2.0 Å do O** em todos os sítios do
  (001); o `relax` aproxima/inclina. O erguimento segue ativo para outros
  átomos eventualmente no caminho vertical.

## Validação realizada

Baseada em inspeção (conforme `CLAUDE.md`, sem rodar `pw.x`). Verificado por
script nas entradas emitidas:

- **(001) regenerado byte-a-byte idêntico** ao anterior (a lógica do (001) não
  foi tocada pela refatoração).
- **(010):** 40 átomos (4 Al, 4 Si, 21 O, 11 H); os **quatro Al 6-coordenados**
  e os **quatro Si 4-coordenados** (Al1 e Si5 completados); os O novos a
  1.87/2.04 Å do Al1, 1.64 Å do Si5 e 0.97 Å do seu H; a borda octaédrica +
  tetraédrica exposta em **+z**; `CELL_PARAMETERS` com volume positivo e linhas
  no plano em z = 0; `if_pos 0 0 0` só nos 18 átomos da metade inferior;
  k-mesh 6 4 1; gap de vácuo 15.10 Å.
- **Estágio 2:** 68 (001) / 80 (010) átomos, `calculation = 'vc-relax'`,
  k-mesh 3 4 1, `if_pos 0 0 0` na camada da base recalculada na supercélula
  — 28/68 (001, 8 Si + 20 O) e 36/80 (010, 4 Al, 4 Si, 20 O, 8 H), exatamente
  o dobro das contagens do Estágio 1.
- **Estágio 3 (001):** 6 entradas (O40–O50), **72 átomos cada** (67 slab + 5
  molécula), `calculation = 'relax'` (`&ions` vazio, sem `&cell` livre — célula
  fixa, herdada intacta da referência 2×1×1), `ntyp = 6` (+ Hg/C), composição
  8 Al, 8 Si, 36 O, **18 H** (15 do slab + 3 da molécula), k-mesh 3 4 1,
  **28 `if_pos 0 0 0`** (28/67, nenhum na molécula). **Desprotonação
  verificada**: a hidroxila do O âncora de cada entrada perde seu único H
  (H#57/58/60/62/66/64 → O#40/42/44/46/48/50, ligação O–H ~0.97 Å); no `.in`
  gerado o O âncora fica com **0 H ligado** e as outras 11 hidroxilas de
  superfície mantêm 1 H cada. Hg exatamente acima do O candidato (desvio no
  plano 0.002 Å), **Hg–O 2.00 Å em todos os sítios** (o H ereto que exigia
  erguimento não existe mais → erguimento 0), Hg-down, gap de vácuo
  11.51–11.55 Å ≥ 10.5, célula neutra (`tot_charge` da referência do slab = 0).
  `find_adsorption_sites(symm_reduce=0)` funcional; `get_surface_sites()`
  devolve vazio ou um subconjunto espúrio de 2 sítios (inutilizável, ver
  Estágio 2b) → a janela de altura é o conjunto autoritativo. (010) inalterado
  e pendente: requer `scf-kaolinite-slab-010-2x1x1.in` relaxado (o gerador
  avisa e sai; sem desprotonação — flag ligado só no (001)).
- Os quatro módulos importam sem erro e não há mais referência à antiga
  `qe_slab_lib.py` (removida, junto com o caminho de adsorção baseado no bulk:
  `make_slab`, `widen_slab`, `align_to_bulk_frame`, `generate`).
