# Spec 40: Criar cálculo — Slab a partir do SCF do bulk (base dos cálculos de superfície)

| | |
|---|---|
| **Prioridade** | 40: a primeira das três de superfície (40 → 41 → 42). Abre o pacote `core/calc_create/surface/`, o campo de "outro SCF" e o relatório da geração que 41 e 42 reaproveitam. |
| **Status** | Implementada (13/10/2026); ver "Decisões na implementação" |
| **Depende de** | spec 25 (registro de tipos, `plan`), spec 26 (janela), spec 28 (nomes, modo Padrão/Avançado, pasta autossuficiente), spec 30 (aba de grupo sem arquivo), spec 39 (prévia editável no Avançado), spec 24 ("Gerar SCF convergido", que fecha o ciclo vc-relax → SCF) |
| **Usada por** | spec 41 (Supercélula), spec 42 (Molécula na superfície) |
| **Esforço** | G (R0: P; R1: M; R2: M; R3: M; R4: P; R5: M) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): porta geometria de cristal dos scripts sem pymatgen (orientação, vácuo, ligações cortadas, poliedros de borda), muda o contrato de `FormField`/`CalcType` usado pela janela e precisa reproduzir os scripts número a número. |

## Itens de origem (`Ideias.md`, 13/10/2026)

> A pasta @Documentation/Exemplo-SLAB/ é um conjunto de scripts que fiz em Python para criar inputs do quantum espresso, eles fazem:
>
> 1. Cria uma estrutura SLAB a partir do SCF do bulk.
>
> Quero adaptar esses scripts para criar os inputs de calculos de superficie (slab, supercelula, e molecula na superficie) do Lain.
>
> Já existe um botão e uma janela para criar calculos. Quero que adicione esses novos tipos de calculos no Lain.
>
> - Slab
>
> São 3 tipos de calculos diferentes, mas que dependem um dos outros. O cálculo da supercelula pode (não necessariamente) depender do cálculo do slab, e o cálculo da molécula na superficie depender do cálculo da supercelula.
>
> Nos scripts, para a criação da slab, tem a opção de usar o scf da molecula para obter o seu tamanho só pra calcular altura de vácuo. Adicione isso como algo opcional.
>
> Os scripts possuem varios parametros que podem ser ajustados para diferentes casos [...]. Adicione todos os parametros dos scripts como parametros configuraveis nas janelas de criação de calculos.

Interpretação: o tipo "Slab" é o **Estágio 1** dos scripts (`qe_slab_surface.generate_surface`): a célula do bulk com o vetor
fora do plano esticado para abrir vácuo, sem cortar planos de Miller arbitrários. "Dependem um dos outros" é a ordem de uso,
não um vínculo de arquivos: cada tipo parte do SCF que o usuário escolhe (o do vc-relax convergido sai de "Gerar SCF
convergido", spec 24). Esta spec também cria o que os três tipos usam: a geometria sem pymatgen, o campo de um segundo SCF
(a molécula, aqui opcional) e o relatório `geracao.md` (o `.md` que os scripts gravam ao lado de cada `.in`).

## Situação atual

- **Os scripts (Documentation/Exemplo-SLAB/, não versionada: `git status` mostra `??`).** `lib/qe_slab_common.py` (363
  linhas), `qe_slab_surface.py` (353), `qe_slab_supercell.py` (122), `qe_slab_candidates.py` (237), `qe_slab_adsorb.py`
  (791) e os wrappers `generate_*.py`, que guardam os parâmetros no topo. `generate_surface.py:24-30`: `KAOLINITE_REF`,
  `MOLECULE_REF`, `VACUUM_MIN = 10.5`, `ADS_DISTANCE = 2.0`, `BOND_SCALE = 1.15`, e o laço em `(0, 0, 1)` e `(0, 1, 0)`.
  Dependem de pymatgen (estrutura, supercélula, adsorção) e ASE (`ase.io.espresso`, `ase.data.covalent_radii`).
- **O Estágio 1, passo a passo** (`qe_slab_surface.py`): `make_surface` (`:210-259`) só conhece `(0,0,1)` (no plano
  `a, b`, empilhamento `c`) e `(0,1,0)` (no plano `a, c`, empilhamento `b`, com `t1_sign = -1`: o segundo vetor do plano é
  `-c`, o que inverte a normal e põe a borda de Al em cima); outro índice é `ValueError`. `heal_cut_hydroxyls` (`:45-86`): cada
  H procura o O mais próximo por imagem mínima (imagens −1…1); acima de 1,2 Å é `RuntimeError`; se a imagem cruza o eixo
  empilhado, o H vai para junto do seu O. `complete_edge_metals` (`:108-163`, só no (010)): para Al e Si (fixos no código), cada
  ligação metal–O (`<=` `bond_scale × (r_M + r_O)`) que cruza o eixo empilhado ganha um O novo no vértice que falta e um H a
  `_bulk_oh_length` (`:89-105`, média O–H do bulk) na direção M→O. `_orient_and_stretch` (`:178-207`): `f = (extensão +
  vácuo) / |s·n|`, linha fora do plano `f·s` (trocada de sinal se `n·(f·s) < 0`), rotação rígida `_ortho_frame` (`:168-175`)
  com `t0 → +x`, normal → `+z`, e as frações em `c` recentradas em 0,5 (`% 1.0`). `generate_surface` (`:264-353`): vácuo =
  `vacuum_min + extensão z da molécula + ads_distance` (a molécula é **obrigatória** no script), k-points por
  `rescale_kmesh` (`qe_slab_common.py:130-138`: cada eixo do plano herda a subdivisão do eixo do bulk de onde vem, o do vácuo
  vale 1), `assemble_namelists(..., calculation="vc-relax")` (`qe_slab_common.py:143-203`: `&ions` vazio, `&cell` do SCF +
  `cell_dofree = '2Dxy'`, `nbnd × 1`, prefixo `<prefix>-slab-<hkl>`), `fixed_indices` (`qe_slab_common.py:270-315`: no (001)
  todo Si + todo O ligado a Si (`<`); no (010) os átomos abaixo do plano médio; outro índice é `ValueError`; 0 ou todos fixos é
  `RuntimeError`), e grava `.in` (ASE, `ibrav = 0`, `CELL_PARAMETERS angstrom`, `ATOMIC_POSITIONS crystal`, `0 0 0` nos
  fixos), `.cif` e `.md`.
- **Reproduzido nesta sessão.** Rodei os oito wrappers numa cópia em scratchpad, num venv temporário com pymatgen
  2026.9.24, ase 3.29.0 e spglib 2.8.0. O Estágio 1 regenera **byte a byte** os dois `surface_pure/*/vc-relax-*.in` da pasta.
  (001): 34 átomos, `|a|,|b|,|c|` = 5,190 / 9,008 / 21,126 Å, `f` = 2,8539 × c, vácuo 15,10 Å (10,5 + molécula 2,60 + 2,0),
  14/34 fixos (4 Si, 10 O), k `6 4 1`. (010): 40 átomos (+3 O, +3 H), 5,190 / 7,403 / 26,425 Å, `f` = 2,9334 × b, H26–O18 e
  H31–O23 reconectados (índices 0-based), O+H em Al1 (2,038 e 1,867 Å) e Si5 (1,64 Å), 18/40 fixos pela metade de baixo, k `6 4 1`.
  O README dos scripts traz números de uma versão anterior do `scf-kaolinite.in` (f = 2,8602): valem os medidos.
- **O Lain lê qualquer estrutura sem ASE.** `core/calc_create/scf_info.py`: `ScfInfo.crystal` é um
  `core/qe/lattice.py:Crystal` (`:34`: `cell` em Å, `labels`, `frac`) feito por `crystal_from_editor` (`:196`), que porta o
  `latgen` do QE 7.1 (todo `ibrav`). Medido nos SCFs da pasta (maior intervalo vazio por eixo, entre centros): bulk
  `scf-kaolinite.in` 0,80 / 1,02 / 1,85 Å; `scf-kaolinite-slab-001.in` 0,72 / 1,04 / **15,07**; `-010.in` 0,84 / 1,79 / **15,25**;
  `scf-H3CHg.in` (`ibrav = 14`, caixa de 40 Bohr) 19,34 / 19,58 / 18,57. As flags `if_pos` não entram no `Crystal`; as linhas
  de `ATOMIC_POSITIONS` como escritas estão em `fragments.py:atom_rows` (`:93-94`, `lru_cache`).
- **"Criar cálculo" tem um SCF só.** `types/base.py`: `FieldKind` (`:47`) não tem tipo "arquivo"; `CalcType.fields` (`:269`)
  e `plan` (`:293`) recebem um `ScfInfo`. A etapa 1 (`ui/dialogs/calc_create/setup_page.py:117`) diz sempre "Input de SCF *".
  `REGISTRY` (`types/__init__.py:45`) tem 7 tipos, nenhum de superfície. Um grupo de campos que não é chave de arquivo vira aba
  própria antes das abas de arquivo (spec 30, "Átomos"). Os templates `qsub/relax.qsub.j2` e `qsub/vc-relax.qsub.j2` são
  iguais (um `pw.x` por `pw_runs`).
- **Trocar a célula de um input já existe, privado.** `core/qe/scf_from_relax.py:_final_cell` (`:168-194`) troca
  `CELL_PARAMETERS`, põe `ibrav = 0` e remove `_CELL_KEYS` (`:44`: `a b c cosab cosac cosbc`) e os `celldm(i)` (`:45`), salvo o
  `celldm(1)` de uma célula `alat`.
- **Dependências.** `pyproject.toml`: `ase`, sem pymatgen (removido pela spec 27-2) nem spglib. `tests/test_perf_detection.py:163-182`
  proíbe `ase` e `jinja2` no import de `main_window` e do registro de tipos. Medido: `import ase.data` custa 8 ms;
  `import ase.io.espresso` custa 0,25 s e traz o scipy.
- **Fixtures.** `tests/fixtures/kao_*` são inputs de relax (não SCF); `tests/fragment_helpers.py:slab_scf` (`:68-72`) faz um
  SCF do slab trocando o texto. Não há SCF de bulk de caulinita nem de molécula nas fixtures. Os SCFs da pasta têm
  `pseudo_dir` pessoais (`/home/alumni/…`, `/home/docens/…`).
- Tamanhos: `types/base.py` 328, `ui/dialogs/calc_create/form.py` 182, `setup_page.py` 277, `tabs_page.py` 345, `dialog.py` 316,
  `core/qe/scf_from_relax.py` 224, `core/calc_create/preview.py` 141 linhas. Nenhum perto do limite.

## Requisitos

### R0: Entradas de referência e goldens dos scripts

1. Nova pasta `tests/fixtures/kao_surface_inputs/` com cópias de `Documentation/Exemplo-SLAB/scfs/`: `scf-kaolinite.in`,
   `scf-H3CHg.in`, `scf-kaolinite-slab-001.in`, `scf-kaolinite-slab-010.in`, `scf-kaolinite-slab-001-2x1x1.in`. Única
   mudança: `pseudo_dir = '/home/seu_usuario/PSEUDO/'` (placeholder da spec 27-9). Linha nova na tabela de
   `tests/fixtures/README.md` ("inputs do usuário, não saídas: referência dos tipos de superfície, specs 40–42") e `git add`
   (`test_fixtures_untouched.py`).
2. `tests/surface_golden.json` (novo): capturado **uma vez**, fora do repositório, rodando os scripts (pymatgen 2026.9.24, ase 3.29.0,
   spglib 2.8.0 num venv temporário; os scripts leem os SCFs da fixture). Por caso: `cell` (3×3, Å), `labels`, `frac`,
   `fixed` (índices 0-based), `kmesh`, `koffset`, `prefix`, `calculation`, `nbnd` (ou null) e, para adsorção, `removed_h`.
   Casos desta spec: `slab_001` (eixo c, sem inverter, fixos por espécie Si + O, com molécula) e `slab_010` (eixo b, invertido,
   com reconexão e poliedros de Al e Si, fixos pela metade de baixo, com molécula). Specs 41 e 42 acrescentam os seus. O JSON
   guarda as versões usadas em `"source"`. O script de captura não entra no repositório (precisa de pymatgen).
3. `tests/surface_helpers.py` (novo): caminhos da fixture, `golden(case)`, `model_from_plan(text)` (lê o input gerado com o
   `InputEditor` e `crystal_from_editor`, flags incluídas) e `same_atoms(a, b, tol=1e-5)` (mesma ordem, distância cartesiana
   por imagem mínima ≤ `tol` Å).

### R1: Um segundo SCF como campo, rótulo do SCF por tipo e relatório

1. `types/base.py`: `FieldKind` ganha `"scf_file"`. O valor é um `ScfInfo` ou `None`; `_coerce` aceita só `ScfInfo` (outro valor
   é "Valor inválido em …"). Um campo `required` sem arquivo dá "Preencha <rótulo>", como hoje.
2. `core/calc_create/scf_info.py`: `read_other_scf(path) -> ScfInfo` (worker) = `looks_like_input` + `read_scf`; um arquivo que
   não parece input levanta `ScfInputError("<nome> não parece um input do Quantum ESPRESSO")`, o mesmo texto da etapa 1.
3. `ui/dialogs/calc_create/scf_field.py` (novo): `ScfFileField(QWidget)`: campo só leitura (variante `mono`), "Escolher…"
   (abre `setup_page.choose_scf`, a mesma função de módulo que os testes trocam) e, para campo opcional, "Limpar". A leitura vai
   num `TaskGroup` (`read_other_scf`), com "Lendo SCF…" na linha de mensagem; erro de leitura fica na linha (nível `error`) e o
   valor volta a `None`. Nenhuma chamada de disco na GUI (`FS_ALLOWED` não muda). `value()`, sinal `changed` ao fim da leitura
   e ao limpar, `shutdown()` (cancela a leitura). `FieldForm._widget` (`form.py:122`) cria o widget para o tipo; `values()` lê
   `value()`. `TabsPage.shutdown()` chama o `shutdown()` dos campos e `CalcCreateDialog.done` chama o da página (nunca por
   `destroyed`: regra do `CLAUDE.md`, spec 39).
4. `CalcType.scf_label: ClassVar[str] = "Input de SCF"`: a etapa 1 mostra `"<scf_label> *"` e troca o texto quando o tipo muda
   (os tipos de hoje continuam "Input de SCF *").
5. Relatório: `types/base.py` `FileKind` ganha `"report"`; `core/calc_create/surface/report.py` (novo) monta o texto e
   `report_file(lines) -> PlannedFile("geracao.md", "report", texto, "Relatório (geracao.md)", "report")`. Texto: título
   `# Relatório da geração`, uma linha `- **rótulo**: valor` por fato, números com vírgula decimal. Não é `InputFile` (sem campo de
   nome, sem a regra do `.in`); `writer._check_names` já recusa repetição; `core/calc_create/preview.py` (`:36-39`) ganha
   `"report": "Relatório"`. Na prévia, sem realce; no Avançado, editável como os outros (spec 39).
6. **Testes:** `tests/test_calc_scf_field.py` (novo): escolher um SCF válido (`choose_scf` trocado) preenche o valor e replaneja;
   um arquivo que não é input mostra a mensagem e deixa `None`; "Limpar" volta a `None`; fechar a janela no meio da leitura não
   chama de volta. `test_calc_create_dialog.py`: o rótulo da etapa 1 segue `scf_label`. `test_architecture.py` sem nova entrada
   em `FS_ALLOWED`.

### R2: Estrutura sem pymatgen (`core/calc_create/surface/`, Qt-free)

1. `surface/model.py` (novo): `Model(cell, labels, frac, flags)` (frozen; `cell` 3×3 em Å, linhas a1 a2 a3; `flags[i]` é a tupla `if_pos`
   como escrita ou `None`). `model_of(scf) -> Model` usa `scf.crystal` e lê as flags das linhas de `ATOMIC_POSITIONS`
   (palavras 5–7, inteiros); sem `crystal` levanta `SurfaceError(scf.structure_problem)`. `species_rows(text)` devolve as linhas
   de `ATOMIC_SPECIES` como escritas (`InputEditor.card_rows`).
2. `surface/elements.py` (novo): `element_of(label)` com a regra de `ase.io.espresso.label_to_symbol` (duas letras se forem um símbolo,
   senão uma; `Fe1`, `Fe_up` → Fe) sobre `ase.data.chemical_symbols`; `covalent_radius(label)` de `ase.data.covalent_radii`
   (a mesma tabela dos scripts). `ase.data` só dentro das funções (8 ms; nunca `ase.io.espresso`). Um rótulo sem elemento é
   `SurfaceError("Espécie sem elemento conhecido: <rótulo>")`.
3. `surface/geometry.py` (novo): `min_image(delta_frac, cell)` (imagens −1…1, como os scripts), `bonded(model, i, j, scale)`,
   `vacuum_gaps(cell, frac) -> tuple[float, float, float]` (por eixo: o maior intervalo vazio entre frações ordenadas, circular,
   vezes a distância interplanar `V / |a_j × a_k|`) e `MIN_SURFACE_GAP = 5.0` Å (abaixo disso não é vácuo de superfície).
4. `core/qe/cell_card.py` (novo, sai de `scf_from_relax`): `set_cell(editor, unit, rows, alat=None) -> str | None` troca
   `CELL_PARAMETERS`, põe `ibrav = 0`, remove `a b c cosab cosac cosbc` e os `celldm(i)` (fica só `celldm(1) = alat` quando
   `unit == "alat"`) e devolve a nota "ibrav = N trocado por 0: …" quando havia outro. `_final_cell` passa a chamá-lo, com o
   mesmo texto de hoje (`test_scf_from_relax.py` sem mudança).
5. `surface/write.py` (novo): `put_structure(editor, model, species) -> list[str]`: `set_cell(editor, "angstrom", …)` com 10 casas,
   `ATOMIC_POSITIONS crystal` com `label x y z` (10 casas) e as flags quando houver, `nat`, `ntyp`, e `ATOMIC_SPECIES` com as
   linhas dadas (só as espécies usadas, na ordem do SCF). Cards por átomo (`ATOMIC_FORCES`, `ATOMIC_VELOCITIES`) saem com nota
   "<card> removido: os átomos mudaram"; `CONSTRAINTS`, um `HUBBARD` com linha `V` ou `Hubbard_V` no `&SYSTEM` levantam
   `SurfaceError` (o tipo põe como erro). As linhas do SCF que não são estrutura ficam byte a byte (`InputEditor`).
6. `surface/molecule.py` (novo): `molecule_of(scf, anchor=None) -> Molecule(labels, coords, anchor, extent)`. As posições são
   desdobradas por imagem mínima em torno do âncora (uma molécula cortada pela borda da caixa fica inteira); âncora = o átomo
   dado (1-based) ou o de maior número atômico (empate: o primeiro), como `build_molecule` (`qe_slab_common.py:91-109`); eixo =
   âncora → primeiro átomo que não é H nem o âncora (o `heavy[0]` do script), senão âncora → centroide dos outros; 1 átomo: sem
   eixo. `coords` saem com o âncora na origem; com o eixo já perto de `+z` (componente z do unitário ≥ `ALIGNED = 0.98`, o limite
   do script) ficam como no SCF; senão são **rodadas** (Rodrigues, a rotação mínima) para o eixo apontar para `+z`, onde o script
   para com erro. No `scf-H3CHg.in` o eixo Hg→C está a 0,01° de `+z`: sem rotação, como no script. `extent` = extensão em z dessas
   coordenadas (2,60 Å no `scf-H3CHg.in`).
7. **Testes:** `tests/test_surface_geometry.py` (novo): `vacuum_gaps` dos SCFs da fixture (os valores medidos acima, ±0,01 Å),
   de um slab enrolado na borda (frações 0,95…0,05) e de 1 átomo; `element_of` de `Fe1`, `Fe_up`, `Hg`, `C2`; `put_structure`
   num SCF `ibrav = 2` (sai `ibrav = 0`, sem `celldm`) e num com `ATOMIC_FORCES` (nota); `molecule_of` do `scf-H3CHg.in`
   (âncora Hg, extensão 2,60 ± 0,01 Å, coordenadas iguais às do SCF menos o âncora) e da mesma molécula deitada (eixo em `+x`) e
   cortada pela borda da caixa (sai inteira, com o eixo em `+z`). `test_architecture.py`: os módulos
   novos em `QT_FREE`. `test_perf_detection.py`: importar os módulos de `surface/` e o registro não carrega `ase`.

### R3: Construção do slab (`surface/slab.py`, novo: porta de `make_surface`)

1. `SlabOptions(axis, flip, vacuum, heal, complete, metals, bond_scale)` e `make_slab(bulk: Model, options) -> SlabResult(model,
   f, axis_map, healed, added, cut_bonds)`. `axis` ∈ `"c"`, `"b"`, `"a"`: no plano `(a, b)`, `(a, c)` e `(b, c)`; `flip` troca o sinal do
   segundo vetor do plano (o `t1_sign = -1` do script). A célula sai com linhas `{t0, t1, f·s}` rodadas para `t0 → +x` e normal
   `+z`, e as frações no eixo do vácuo recentradas em 0,5 (`% 1.0`), como `_orient_and_stretch`. Os átomos mantêm a ordem do bulk
   e os adicionados vão ao fim, em pares O, H.
2. `vacuum` (Å) é o vácuo perpendicular acima da camada; `f = (extensão + vácuo) / |s·n|`, medido com as posições já
   reconectadas e completadas (como o script).
3. `heal` (porta de `heal_cut_hydroxyls`, generalizada): cada H acha o vizinho ligado mais próximo de **qualquer** espécie
   (`bond_scale`); se a imagem cruza o eixo empilhado, o H vai para junto dele. Um H sem vizinho ligado fica onde está e entra numa
   nota ("H 27 sem vizinho ligado: não reconectado"). No caso da caulinita todos os H ligam a O, então o resultado é o do script.
4. `complete` (porta de `complete_edge_metals`): para cada metal de `metals` (rótulos), cada ligação metal–O (`<=`) que cruza o
   eixo empilhado ganha O e H; o comprimento O–H é a média do bulk (`_bulk_oh_length`). Sem O ou H em `ATOMIC_SPECIES`, ou sem H
   no bulk, é `SurfaceError` ("Completar poliedros precisa de O e H no SCF" / "sem H no bulk para medir o O–H").
5. `cut_bonds`: as ligações X–O que cruzam o eixo empilhado, contadas **com ou sem** `complete`, para toda espécie X que não é
   O nem H (pelo elemento, mesmo critério `<=` de `complete`), como `{rótulo: número}`. É o que a nota de R5.5 lê; com
   `complete` ligado, as de rótulos que estão em `metals` são as completadas.
6. Bordas: célula de volume ≤ 0 depois da rotação é erro; nenhuma ligação cortada é um caso normal (nada muda além do vácuo).
7. **Testes:** `tests/test_surface_slab.py` (novo): `slab_001` e `slab_010` contra `surface_golden.json` (`same_atoms`, célula
   ±1e-6 Å, `f` ±1e-6), com as opções do script; `axis="a"` e `flip` em c dão célula destra (det > 0) e as linhas do plano com
   `z = 0`; `heal` num bulk sem H não muda nada; `complete` sem H no SCF é erro; `cut_bonds` é `{}` no (001) e
   `{"Al": 2, "Si": 1}` no (010), com `complete` ligado ou desligado.

### R4: Átomos fixos e k-points (compartilhados com 41 e 42)

1. `surface/fixing.py` (novo): `FIX_RULES = ("camada inferior", "espécies e vizinhos", "do SCF", "nenhum")` e
   `fixed_atoms(model, rule, *, fraction, species, neighbors, bond_scale, n_slab=None) -> FixResult(indices, notes)`.
   "camada inferior": projeção na normal `< mínimo + fraction × espessura` (`fraction = 0.5` é o plano médio do script);
   "espécies e vizinhos": os átomos de `species` mais os de `neighbors` ligados a um deles (`<`, como `fixed_indices`), com nota
   quando a média das `species` está acima do plano médio; "do SCF": as flags do modelo; "nenhum": nenhum. Só os primeiros
   `n_slab` contam (uma molécula anexada depois fica livre). Todos fixos é erro ("Todos os átomos ficariam fixos"); nenhum fixo
   com regra que não é "nenhum" é nota.
2. Escrita: um átomo fixo por regra recebe `0 0 0`; um livre, nada (como os scripts); "do SCF" escreve as flags como estavam.
3. `surface/kmesh.py` (novo): `rescale_mesh(mesh, axis_map, mults, vacuum_axis)`: cada eixo `max(1, round(k / n))` do eixo de origem,
   o do vácuo 1, deslocamentos mantidos (`rescale_kmesh` do script, generalizado para a 41).
4. **Testes:** `tests/test_surface_fixing.py` (novo): as duas regras do script dão os fixos do golden (14/34 e 18/40); "do SCF"
   num slab da fixture devolve as 14 flags; todos fixos é erro; `rescale_mesh((6,4,4), {0:0, 1:2}, …)` dá `6 4 1`.

### R5: Tipo "Slab"

1. `types/slab.py` (novo): `SlabType(VcRelaxType)`, `id = "slab"`, `label = "Slab"`, `folder_prefix = "Slab"`,
   `script_stem = "slab"`, `script_template = "qsub/vc-relax.qsub.j2"`, `scf_label = "SCF do bulk"`. Registrado depois de
   "Diferença de carga". Arquivos: o script, o input `vc-relax_<prefix do SCF>.in` (chave `vc-relax`, rótulo "Slab") e
   `geracao.md`.
2. Campos do grupo `"Superfície"` (aba própria, antes das de arquivo). Padrão: `molecule` "SCF da molécula (opcional)"
   (`scf_file`, dica: "Só para o vácuo: soma a altura da molécula e a distância de adsorção ao vácuo mínimo"), `axis` "Superfície
   (eixo empilhado)" (`choice`: "c (001)", "b (010)", "a (100)"; padrão "c (001)"), `vacuum_min` "Vácuo mínimo (Å)" (10.5) e
   `complete` "Completar poliedros de borda (O + H)" (desligado; dica: "Fecha cada ligação metal–O cortada com um O novo e o seu
   H: Al–OH, Si–OH"). Avançado: `ads_distance` "Distância de adsorção (Å)" (2.0), `flip` "Inverter a superfície" (desligado),
   `heal` "Reconectar H cortados" (ligado), `metals` "Metais da borda" ("Al Si"),
   `bond_scale` "Tolerância de ligação (× soma dos raios covalentes)" (1.15), `fix_rule` "Átomos fixos (if_pos 0 0 0)" (`choice`:
   "camada inferior", "espécies e vizinhos", "nenhum"; padrão "camada inferior"), `fix_fraction` "Fração fixa da espessura" (0.5),
   `fix_species` "Espécies fixas" ("Si"), `fix_neighbors` "Vizinhos fixos" ("O").
3. Campos da aba do input: os do VC-Relax (`nstep`, `forc_conv_thr`, `ion_dynamics`, `cell_dynamics`, `press`), `cell_dofree`
   (`choice` com a lista do `INPUT_PW` — `all ibrav a b c fixa fixb fixc x y z xy xz yz xyz shape volume 2Dxy 2Dshape
   epitaxial_ab epitaxial_ac epitaxial_bc`; padrão `2Dxy`) e `kmesh` com padrão **vazio** ("vazio = a do SCF reescalada: o eixo do
   vácuo vale 1"; o `kmesh_field` de hoje preencheria a malha do bulk, que muda com o eixo).
4. `plan`: vácuo = `vacuum_min` + `molecule_of(molécula).extent` + `ads_distance`; sem molécula, só `vacuum_min` (nota "Sem
   molécula: o vácuo é o mínimo"). Uma molécula sem estrutura legível é problema no campo `molecule`. Input = `work.editor()` (pasta autossuficiente) + `put_structure` + `VcRelaxType.edit` +
   `cell_dofree` + `prefix = '<prefix>-slab-<hkl>'` (`001`, `010`, `100`); `nbnd` como no SCF. k-points vazio: `rescale_mesh` da
   malha `automatic` do SCF; `K_POINTS gamma` fica `gamma` (nota); outro card é erro no campo ("Preencha a rede de k-points: o SCF
   não tem K_POINTS automatic"). Erros de `SurfaceError` vão para o campo que os causa (`work.problem`) ou para a lista.
5. Notas: o SCF já tem vácuo ≥ `MIN_SURFACE_GAP` no eixo escolhido ("O SCF já tem 15,1 Å de vácuo ao longo de c: parece uma
   superfície"); `cell_dofree` diferente de `all` numa célula de eixos não ortogonais ("o INPUT_PW avisa que algumas opções de
   cell_dofree não funcionam com eixos não ortogonais"); molécula que não parece isolada (algum `vacuum_gaps` < 5 Å). Ligações
   cortadas sem completar, de `SlabResult.cut_bonds`: com `complete` desligado e alguma ligação, "3 ligações metal–O cortadas na
   borda (Al 2, Si 1); marque 'Completar poliedros de borda (O + H)' para fechá-las com OH"; com `complete` ligado e ligações de
   rótulos fora de `metals`, "Ligações Fe–O cortadas não foram completadas: Fe não está em 'Metais da borda'". Nenhuma nota quando
   o corte não rompe ligação (o (001) da caulinita).
6. `geracao.md`: SCF de origem, superfície (eixo e hkl, invertida ou não), átomos (total e por espécie), `|a|, |b|, |c|`, fator
   `f`, vácuo pedido (com a soma) e medido, átomos fixos (n/N, por espécie, regra), k-points (e de onde vieram), H reconectados
   e O+H adicionados com números **1-based** ("H27–O19 (0,974 Å)").
7. **Testes:** `tests/test_calc_slab.py` (novo): o plano com as opções do golden reproduz `slab_001` e `slab_010` (estrutura,
   fixos, k-points, `prefix`, `calculation`, `cell_dofree = '2Dxy'`) lido do texto gerado; sem molécula o vácuo medido é 10,5 Å;
   `outdir = './tmp/'` e `jobs.pseudo_dir` aplicados; `K_POINTS gamma` mantido com nota; `CONSTRAINTS` dá erro; o input passa no
   `lint` sem erro; Padrão mostra só os quatro campos (`molecule`, `axis`, `vacuum_min`, `complete`); no (010) com `complete`
   desligado sai a nota "3 ligações metal–O cortadas na borda (Al 2, Si 1); …", ligado ela some, e o (001) não tem nota; com
   `metals` = "Al" e `complete` ligado, a nota diz que o Si ficou de fora. `test_calc_create_matrix.py` cobre o tipo novo com todo SCF das fixtures (os
   novos de R0 entram sozinhos pelo `rglob`). `test_calc_roundtrip.py`: uma linha para "Slab" (o input gerado é detectado como
   vc-relax).

## Fora de escopo

- Planos de Miller arbitrários (cortar `(hkl)` com busca de terminação, o `SlabGenerator`): os scripts só esticam um eixo da
  célula. Outra spec, se pedida.
- Gravar `.cif` de prévia (os scripts gravam): o Lain não escreve CIF hoje. Adiado.
- Correção de dipolo (`tefield`, `dipfield`, `edir`, `emaxpos`) e `assume_isolated`: os scripts não usam.
- Supercélula e molécula na superfície: specs 41 e 42.
- Rodar os scripts dentro do Lain ou depender de pymatgen: a porta é em `core/` com numpy e `ase.data`.

## Decisões assumidas (confirmar na revisão)

1. **Superfície = eixo empilhado** (a, b ou c da célula do SCF) + "Inverter", como os scripts; sem `(hkl)` arbitrário.
2. **Padrões genéricos, não da caulinita:** "camada inferior" a 0,5 (a regra do (010)) e sem inverter nem completar. Os dois casos
   da caulinita se reproduzem mudando os campos (é o que os goldens fazem). Decisão do usuário (13/10/2026): "Completar poliedros"
   fica no modo **Padrão** (desligado) e o plano avisa quando o corte rompe ligações metal–O que ninguém fechou, para o (010) não
   sair sem a protonação da borda por esquecimento.
3. **"Reconectar H" vale para H ligado a qualquer espécie** (o script só aceita O e para com erro no resto).
4. **Molécula como campo da etapa 2** (aba "Superfície", Padrão), não uma segunda linha na etapa 1: a etapa 1 e o contrato de
   `plan(scf, …)` ficam como estão; os campos só não podem depender da molécula na hora de serem criados.
5. **Sem molécula, vácuo = vácuo mínimo**: a distância de adsorção só soma com molécula.
6. **Nome do arquivo segue a spec 28** (`vc-relax_<prefix do SCF>.in`), e o `prefix` novo segue os scripts (`<p>-slab-001`): o nome
   não pode depender de campos (a caixa "Nome do arquivo" já vem preenchida).
7. **Relatório `geracao.md`** com números 1-based (os scripts usam índices 0-based do pymatgen; o QE e o VESTA contam de 1).
8. **Pastas e script:** prefixo de pasta `Slab`, script `slab.qsub` sobre o template do vc-relax.
9. `MIN_SURFACE_GAP = 5 Å`: o bulk de caulinita tem 1,85 Å e os slabs 15 Å.
10. **Molécula deitada é rodada** (o script para com erro quando o eixo âncora→C não está em `+z`); até 11,5° de `+z` ela fica
    como o usuário escreveu, o mesmo limite do script.

## Notas de implementação

- Novos: `core/calc_create/surface/{__init__,model,elements,geometry,molecule,slab,fixing,kmesh,write,report}.py`,
  `core/qe/cell_card.py`, `core/calc_create/types/slab.py`, `ui/dialogs/calc_create/scf_field.py`,
  `tests/fixtures/kao_surface_inputs/`, `tests/surface_golden.json`, `tests/surface_helpers.py`, `tests/test_calc_scf_field.py`,
  `tests/test_surface_geometry.py`, `tests/test_surface_slab.py`, `tests/test_surface_fixing.py`, `tests/test_calc_slab.py`.
- Alterados: `types/base.py` (`scf_file`, `report`, `scf_label`), `types/__init__.py` (registro), `scf_info.py`
  (`read_other_scf`), `scf_from_relax.py` (usa `set_cell`), `preview.py` (rótulo do relatório), `ui/dialogs/calc_create/form.py`,
  `tabs_page.py` e `dialog.py` (`shutdown`), `setup_page.py` (rótulo), `tests/fixtures/README.md`, `test_architecture.py`
  (`QT_FREE`), `test_perf_detection.py`.
- Ordem: R0 → R2 → R3/R4 → R1 → R5.
- Limites: nenhum arquivo perto de 500; `types/slab.py` deve ficar curto (a geometria mora em `surface/`).
- Documentação: `CLAUDE.md`, seção "'Criar cálculo' backend" (tipo Slab, pacote `surface/`, `scf_file`, `geracao.md`) e "Testing
  notes" (fixture e golden); `tests/fixtures/README.md`.

## Critérios de aceite e testes

- [x] Os tipos de hoje não mudam: `test_calc_*.py`, `test_scf_from_relax.py` e `test_calc_create_matrix.py` passam sem editar
      expectativas.
- [x] `test_surface_slab.py` e `test_calc_slab.py`: (001) e (010) iguais ao golden dos scripts (posições ≤ 1e-5 Å, fixos, k `6 4 1`).
- [x] Sem molécula, o vácuo medido é o vácuo mínimo; com molécula, 15,10 Å no (001).
- [x] "Completar poliedros de borda" aparece no Padrão; no (010) desligado, a nota das 3 ligações metal–O cortadas (Al 2, Si 1)
      aparece; no (001), não (`test_calc_slab.py`, `test_surface_slab.py`).
- [x] O campo "SCF da molécula" lê em worker, mostra erro de arquivo inválido e limpa (`test_calc_scf_field.py`); `FS_ALLOWED` igual.
- [x] `geracao.md` aparece em "Arquivos" e é gravado com o resto (`test_calc_slab.py`).
- [x] `ase` não carrega com `main_window` nem com o registro (`test_perf_detection.py`).
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.

## Decisões na implementação

1. **Golden capturado dos scripts, offline.** O venv usado na escrita da spec (pymatgen 2026.9.24, ase 3.29.0, spglib 2.8.0) ainda
   existia; os scripts rodaram sobre os SCFs de `tests/fixtures/kao_surface_inputs/` e o `.in` que gravam é **byte a byte** o de
   `surface_pure/*/` (só o `pseudo_dir` difere). Além dos campos da spec, o JSON guarda `f`, `vacuum`, `molecule_extent`, `axis_map`,
   `healed` e `added` (0-based). A porta bate com ele na precisão de máquina (`f` e célula ~1e-16, posições ~1e-15 Å); lidas do
   texto gerado (10 casas), ~1e-9 Å.
2. **Imagens −1…1 sobre as frações como escritas**, como os scripts: "a ligação cruza o eixo empilhado" é a imagem dela nesse eixo,
   então as frações nunca são reduzidas antes (`geometry.pair_images` percorre uma imagem por vez, desempate pela primeira na ordem
   de `itertools.product`).
3. **Rótulos dos átomos novos:** o O novo leva o rótulo do O parceiro (o vértice que faltava), o H novo o do primeiro H do bulk.
   "Completar" exige O e H entre as espécies (`ScfInfo.species`) e um H no bulk; os erros marcam o campo `complete`.
4. **`rescale_mesh`: os deslocamentos seguem o eixo de origem** (`axis_map`) e o do vácuo vai a 0 (o script os copiava na ordem do
   bulk; com `0 0 0`, o caso dos scripts, é o mesmo).
5. **`CalcType.writes_report`** (ClassVar, `False` nos tipos de hoje) diz que o tipo grava `geracao.md` depois dos inputs: a matriz
   (`test_calc_create_matrix.py`) espera a chave `report` só para esses tipos; as expectativas dos outros não mudaram. Os testes que
   listam o registro (`test_calc_types`, `test_calc_writer`, `test_calc_standard`, `test_qsub_lint`) ganharam a linha do Slab.
6. **Arquivos do tipo:** `types/slab.py` (o plano, 300 linhas), `types/slab_fields.py` (os campos e rótulos) e
   `types/surface_fields.py` (o que 41/42 reaproveitam: campo da molécula, tolerância de ligação, átomos fixos, leitura e checagem de
   rótulos digitados, `counts`).
7. **Rótulos digitados** ("Metais da borda", "Espécies fixas", "Vizinhos fixos") são rótulos de `ATOMIC_SPECIES`, separados por
   espaço, vírgula ou ponto e vírgula; um que o SCF não tem é problema no campo, mas só quando a opção que o lê está ligada. Um campo
   de texto vazio volta ao padrão, como em toda a janela ("Espécies fixas" vazio = "Si").
8. **`put_structure` recusa antes de editar** (`CONSTRAINTS`, Hubbard V, espécie sem linha em `ATOMIC_SPECIES`): numa falha o input
   da prévia é o SCF com as edições do vc-relax e o relatório diz "Estrutura não gerada: …"; os três arquivos sempre existem.
9. **`KMeshEditor`** ganhou o texto do campo vazio (`FormField.hint`): o "Vazio: mantém o K_POINTS do SCF" de hoje seria falso no
   Slab, que reescala a malha. A prévia do relatório usa `PlainHighlighter` (só o sublinhado, nunca há problemas: `edit_issues`
   devolve `[]` para `report`).
10. **O input herda do VC-Relax** `nstep = 50` e `press = 0.0` quando o SCF não os tem (os scripts não os escreviam; são os padrões
    do pw.x) e o `&IONS` / `&CELL` do SCF.
11. **`ScfFileField` mostra a dica do campo** numa linha sob ele; a leitura é `TaskGroup` sem `BusyTracker` (só a linha "Lendo
    SCF…"). `TabsPage.shutdown()` é chamado por `CalcCreateDialog.done` e também antes de descartar uma etapa 2 velha
    (`_build_tabs`).
12. `pyproject.toml`: `surface_helpers` entra em `known-local-folder` do isort, como os outros helpers de teste.

