# Spec 41: Criar cálculo — Supercélula de uma superfície (ou de um bulk)

| | |
|---|---|
| **Prioridade** | 41: depois da 40, de quem usa o pacote `surface/` e o relatório; antes da 42, cujo SCF de entrada costuma ser o desta. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 40 (`surface/model`, `fixing`, `kmesh`, `write`, `report`, `geometry.vacuum_gaps`, `scf_label`), spec 28 (nomes, modos), spec 24 ("Gerar SCF convergido" do vc-relax do slab) |
| **Usada por** | spec 42 (o SCF da supercélula relaxada é a entrada típica) |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a spec 40 abre (mesmo pacote, mesmas regras de fixos e k-points); a única geometria nova é a réplica diagonal. |

## Itens de origem (`Ideias.md`, 13/10/2026)

> 2. Cria uma Supercelula a partir do scf feito da estrutura do SLAB relaxada.
>
> - Supercelula
>
> O cálculo da supercelula pode (não necessariamente) depender do cálculo do slab [...]
>
> Adicione todos os parametros dos scripts como parametros configuraveis nas janelas de criação de calculos.

Interpretação: o tipo "Supercélula" é o **Estágio 2** dos scripts (`qe_slab_supercell.generate_supercell`). "Pode (não
necessariamente) depender do slab": o SCF de entrada pode ser o de uma superfície relaxada (o caso dos scripts) ou o de um bulk;
o tipo aceita os dois e só muda os padrões (`cell_dofree`) conforme encontra vácuo.

## Situação atual

- **O Estágio 2** (`Documentation/Exemplo-SLAB/lib/qe_slab_supercell.py:33-122`): lê só o SCF da superfície relaxada; descarta
  as flags `if_pos` herdadas (`:64-65`) e chama `make_supercell([supercell_mult, 1, 1])` (`:66`: só o eixo 0 é replicado; a ordem
  sai por átomo, cada átomo seguido das suas réplicas, como mostra o golden); k-points por `rescale_kmesh(ref.kmesh, {0:0, 1:1},
  {0: mult, 1: 1})` (`:70`, o eixo do vácuo sempre 1); `prefix = <prefix>-2x1x1` (`:72`, fixo no texto mesmo com outro `mult`);
  `assemble_namelists(..., "vc-relax", nbnd_mult=mult)` (`:82-83`: `nbnd × mult`, `&cell` com `cell_dofree = '2Dxy'`); verifica
  vácuo ≥ `vacuum_min` (`:85`, `RuntimeError` abaixo); refaz os fixos com `fixed_indices` na estrutura replicada (`:86`).
  Parâmetros do wrapper (`generate_001_supercell.py:23-28`): `SLAB_REF`, `VACUUM_MIN = 10.5`, `SUPERCELL_MULT = 2`,
  `BOND_SCALE = 1.15`.
- **Reproduzido nesta sessão** (venv temporário com pymatgen, como na spec 40): (001) a partir de `scf-kaolinite-slab-001.in`:
  68 átomos, 10,379 / 9,008 / 21,126 Å, vácuo 15,07 Å, 28/68 fixos (8 Si, 20 O), k `3 4 1`. (010) a partir de
  `scf-kaolinite-slab-010.in`: 80 átomos, 10,379 / 7,403 / 26,425 Å, vácuo 15,25 Å, 36/80 fixos (4 Al, 4 Si, 20 O, 8 H), k `3 4 1`.
  Os SCFs de slab da pasta já trazem `0 0 0` em 14 (001) e 18 (010) átomos: replicá-las dá os mesmos 28 e 36 que a regra refaz.
- **O Lain hoje:** nenhum tipo replica a célula (`types/__init__.py:45`); `VcRelaxType` (`types/vc_relax.py`) tem os campos de
  `&CELL` mas não `cell_dofree`; a spec 40 cria `cell_dofree`, `FIX_RULES` (com "do SCF"), `rescale_mesh` e `put_structure`.
- `plan` roda na GUI a cada edição (`types/base.py:293`, "the window calls it on every edit"): a regra "espécies e vizinhos"
  compara pares de átomos, então o tamanho da supercélula pesa ali.

## Requisitos

### R1: Réplica (`surface/supercell.py`, novo)

1. `make_supercell(model, n: tuple[int, int, int]) -> Model`: célula com as linhas `n_i × a_i`; para cada átomo, na ordem do SCF,
   as réplicas `(i, j, k)` com `i` mais lento que `j` e `k`, frações `(frac + (i, j, k)) / n` sem reenrolar; flags copiadas para
   cada réplica.
2. Limites: cada `n_i` de 1 a `MAX_REPEAT = 8`, e no máximo `MAX_ATOMS = 2000` átomos (erro no campo: "Supercélula grande demais
   para o Lain: <N> átomos (máximo 2000)").
3. **Testes:** `tests/test_surface_supercell.py` (novo): `(2, 1, 1)` dos SCFs de slab da fixture contra os goldens
   `supercell_001` e `supercell_010` (acrescentados ao `surface_golden.json` pela captura descrita na spec 40 R0.2) com
   `same_atoms`; `(1, 1, 1)` devolve o mesmo modelo; flags replicadas.

### R2: Tipo "Supercélula"

1. `types/supercell.py` (novo): `SupercellType(VcRelaxType)`, `id = "supercell"`, `label = "Supercélula"`,
   `folder_prefix = "Supercell"`, `script_stem = "supercell"`, `script_template = "qsub/vc-relax.qsub.j2"`,
   `scf_label = "SCF da superfície (ou do bulk)"`. Registrado depois de "Slab". Arquivos: script, `vc-relax_<prefix do SCF>.in`
   (chave `vc-relax`, rótulo "Supercélula") e `geracao.md` (spec 40 R1.5).
2. Campos do grupo `"Supercélula"` (aba própria). Padrão: `n1`, `n2`, `n3` "Repetições ao longo de a / b / c" (`int`; padrão 2, 1,
   1, o `SUPERCELL_MULT` do script). Avançado: `fix_rule` (as quatro de `FIX_RULES`; padrão "do SCF" quando o SCF tem alguma
   flag, senão "camada inferior"), `fix_fraction`, `fix_species`, `fix_neighbors`, `bond_scale` (os mesmos rótulos e padrões da
   spec 40) e `vacuum_min` "Vácuo mínimo (Å)" (10.5; só verifica).
3. Campos da aba do input: os do VC-Relax, `cell_dofree` (padrão `2Dxy` quando o SCF tem vácuo ≥ `MIN_SURFACE_GAP` ao longo de c,
   senão `all`) e `kmesh` vazio por padrão ("vazio = a do SCF dividida pelas repetições").
4. `plan`: `make_supercell` → `fixed_atoms` (a regra na estrutura replicada; "do SCF" usa as flags replicadas) →
   `work.editor()` + `put_structure` + `VcRelaxType.edit` + `cell_dofree` + `prefix = '<prefix>-<n1>x<n2>x<n3>'` + `nbnd ×
   n1·n2·n3` quando o SCF tem `nbnd`. k-points vazio: `rescale_mesh` da malha `automatic` com as repetições (`6 4 1` com `2 1 1`
   → `3 4 1`); `gamma` fica (nota); outro card é erro no campo, como na spec 40.
5. Notas: vácuo ao longo de c abaixo de `vacuum_min` ("Vácuo de 9,8 Å ao longo de c, abaixo do mínimo de 10,5 Å"; o script para
   com erro); `n3 > 1` com vácuo ao longo de c ("repetir ao longo do vácuo empilha slabs"); SCF sem vácuo ("SCF sem vácuo:
   supercélula de bulk, cell_dofree = 'all'").
6. `geracao.md`: SCF de origem, repetições, átomos (total e por espécie), `|a|, |b|, |c|`, vácuo medido, fixos (n/N, por espécie,
   regra), k-points (de onde vieram), `nbnd` (antes → depois).
7. **Testes:** `tests/test_calc_supercell.py` (novo): o plano a partir de `scf-kaolinite-slab-001.in` e `-010.in` reproduz os
   goldens (estrutura, 28/68 e 36/80 fixos tanto por "do SCF" quanto pela regra do script, k `3 4 1`, `cell_dofree = '2Dxy'`);
   a partir do bulk `scf-kaolinite.in` com `2 2 1`: `cell_dofree = 'all'`, k `3 2 4`, nota de bulk; `nbnd` dobrado num SCF com
   `nbnd = 90`; 9 repetições e 2001 átomos são erros no campo; Padrão mostra só `n1`, `n2`, `n3`. `test_calc_create_matrix.py`
   cobre o tipo; `test_calc_roundtrip.py` ganha a linha "Supercélula".

## Fora de escopo

- Supercélula não diagonal (matriz 3×3, como `make_supercell` do pymatgen aceita): os scripts só usam `[n, 1, 1]`.
- Escolher a regra de fixos por átomo numa tabela: o Avançado já deixa editar o input (spec 39).
- `.cif` de prévia (spec 40, fora de escopo).

## Decisões assumidas (confirmar na revisão)

1. **Repetições nos três eixos** (o script só replica `a`); `n3` existe para a supercélula de bulk que a ideia permite.
2. **"do SCF" é o padrão** quando o SCF tem flags: replica a escolha que o usuário já fez no slab; nos SCFs da pasta dá o mesmo
   que a regra do script.
3. **Prefixo com as repetições** (`<p>-2x1x1`, como o script, mas seguindo os campos); o nome do arquivo segue a spec 28.
4. **Vácuo abaixo do mínimo é nota**, não erro (o script para).
5. **Limites** `MAX_REPEAT = 8` e `MAX_ATOMS = 2000`: o `plan` roda na GUI a cada edição.
6. Pasta `Supercell`, script `supercell.qsub` sobre o template do vc-relax.

## Notas de implementação

- Novos: `core/calc_create/surface/supercell.py`, `core/calc_create/types/supercell.py`, `tests/test_surface_supercell.py`,
  `tests/test_calc_supercell.py`; casos `supercell_001` e `supercell_010` em `tests/surface_golden.json`.
- Alterados: `types/__init__.py` (registro), `test_architecture.py` (`QT_FREE`), `test_calc_roundtrip.py`.
- Limites: nenhum arquivo perto de 500.
- Documentação: `CLAUDE.md`, seção "'Criar cálculo' backend" (tipo Supercélula).

## Critérios de aceite e testes

- [ ] Os tipos de hoje e o Slab não mudam (`test_calc_*.py`, `test_calc_slab.py`).
- [ ] (001) e (010) iguais aos goldens dos scripts: 68 e 80 átomos, 28 e 36 fixos, k `3 4 1` (`test_calc_supercell.py`).
- [ ] Supercélula de bulk com `cell_dofree = 'all'` e k dividido em todos os eixos.
- [ ] `nbnd` multiplicado pelas repetições; limites dão erro no campo, sem travar a janela.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
