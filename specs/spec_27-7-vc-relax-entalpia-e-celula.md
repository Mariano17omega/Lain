# Spec 27-7: vc-relax — entalpia, pressão, volume e célula por passo

| | |
|---|---|
| **Prioridade** | 27-7 |
| **Status** | Proposta |
| **Depende de** | spec 6 (gráficos de relaxamento), spec 12 (resumo, `parse_relax` em fluxo) |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): parser de uma saída com formato irregular (linhas ausentes no primeiro passo, unidades da célula), física correta do critério do BFGS (entalpia, pressão) e extensão de um módulo gráfico com figuras de referência a preservar. |

## Itens de origem (`specs/report-04-10-26.md`)

- **F4 (Médio):** vc-relax plota energia, não entalpia; sem pressão, volume nem parâmetros de célula por passo. Já era F4 do `specs/report.md` e segue aberto. A "Gerar SCF
  convergido" **não** é afetada (usa `geometry_converged`, que lê `bfgs converged`).

## Situação atual

- `core/qe/relax.py`: lê por passo só `! total energy` (`_ENERGY`), `Total force` (`_FORCE`), o passo BFGS, o número de ciclos SCF e os critérios (`_ENERGY_THR`, `_FORCE_THR`, `_CRITERIA`).
  `new unit-cell volume` e `Final enthalpy` (`:149`) só ligam a flag `vc_relax`. `RelaxStep` (`:46`): `index, bfgs_step, energy_ry, force_ry_bohr, scf_cycles`. `RelaxData` guarda `steps`,
  `energy_threshold` e `force_threshold` (prioridade: cabeçalho, critérios, input, padrão do QE). `parse_relax(lines)` recebe um fluxo (a spec 12 usa o mesmo fluxo em `summarize`).
- O BFGS do QE para vc-relax testa **entalpia** e **pressão** (`criteria: energy < … Ry, force < … Ry/Bohr, cell < … kbar`). Com `press ≠ 0`, |ΔE| de E_total não é o critério aplicado;
  com `press = 0`, H = E e a diferença some.
- **Única fixture vc-relax:** `tests/fixtures/kao_vc_relax/vc-relax.out` (QE 7.1; 5 passos BFGS + SCF final). Contagens (regex com espaços variáveis: o texto é `enthalpy           new  =
  -1107.4641235902 Ry`, então `enthalpy\s+new\s+=`): `enthalpy new` 4 (linhas 616, 790, 1055, 1258; a primeira sem linha `old`), `new unit-cell volume` 5 (`:621` do passo 1, com
  `(  334.32919 Ang^3 )` no fim), `total   stress … P=` 6 (5 passos + SCF final), `CELL_PARAMETERS` 5 + 1 final, `Final enthalpy` 1, `Final scf calculation` 1, `!` 6, `Total force` 6. Os outros
  relaxamentos (`si_relax`, `kao_slab_relax`, `kao_supercell_relax`) não têm nenhuma dessas linhas.
- `core/calculations/relax.py`: `RelaxParams` (`:61`) tem `panels = "both"` (`PANELS`: `both | energy | force`, `:44`), `scale = "log"`, `show_thresholds`, `xmin`, `xmax`, cores. `panels_shown`
  (`~:167`) decide os painéis; `render` (`~:187`) os empilha com `stacked_axes`; `_energy` (`~:219`) desenha barras de `data.energy_deltas` (|E_i − E_{i−1}|, x a partir de 1) e a linha de limiar
  (`_threshold`, `:211`, `ax.axhline(value, ls=DASHED)` com rótulo `etot_conv_thr = X Ry` ou `forc_conv_thr = X Ry/Bohr`, "(padrão do QE)" quando vem do padrão); `_force` (`~:237`) desenha linha com
  marcadores; `format_coordinates` (`~:156`) é o readout do cursor. Um painel novo estende `PANELS`, `EXPORT_STEMS`, `panels_shown` e `param_schema`.
- Testes de referência a manter: `test_relax.py` (inclui um teste de latência em `:279`), `test_figure_regression.py` (goldens de figuras sem vc-relax), `tests/test_perf_detection.py`
  (`parse_relax` em saída de 200 MB).

## Requisitos

### R1: Parser (`core/qe/relax.py`)
1. `RelaxStep` ganha, todos opcionais (`None` quando a linha não existe, p. ex. em `relax` comum): `enthalpy_ry`, `pressure_kbar`, `volume_ang3` e `cell: tuple[tuple[float, float, float], …] | None`
   (3×3, em Å). `RelaxData` ganha `pressure_threshold` (de `cell < X kbar` do cabeçalho de critérios; senão do input `press_conv_thr`; senão 0,5 kbar, o padrão do QE) e `target_pressure_kbar` (`press` do
   input, padrão 0).
2. Linhas lidas (regex tolerantes a espaços): `enthalpy\s+new\s+=\s+(valor)\s+Ry`; `new unit-cell volume\s+=\s+(a.u.³)\s+a\.u\.\^3\s+\(\s*(Å³)\s+Ang\^3\s*\)`; `P=\s*(valor)` da linha
   `total   stress`; o bloco `CELL_PARAMETERS (alat= X)` / `(angstrom)` / `(bohr)` com 3 linhas, convertido para Å (alat em bohr × 0,529177…).
3. **Atribuição ao passo:** cada valor vai para o `RelaxStep` do passo BFGS em que foi impresso (a pressão do SCF desse passo, a entalpia/volume/célula da geometria nova). O **primeiro** passo não
   tem `enthalpy new`: `enthalpy_ry` fica como `E + P_alvo·V` quando `press` e o volume inicial são conhecidos, senão `None` (e `|ΔH|` começa no segundo par). A conta é checada na fixture: onde o QE
   imprime `enthalpy new`, `E + press·V` calculado difere do impresso em < 1e-5 Ry.
4. Continua um passe sobre o fluxo (a spec 12 e o teste de 200 MB dependem disso); sem custo extra mensurável (substring antes de regex, como `Scanner`).
5. Testes: contagens da fixture (4 entalpias, 5 volumes, 6 pressões, 5 células + a final); relax comum e SCF não ganham nenhum campo novo (tudo `None`); a saída truncada no meio de um passo não levanta;
   unidades `alat`/`angstrom`/`bohr` de `CELL_PARAMETERS` dão a mesma célula em Å.

### R2: Gráfico do vc-relax (`core/calculations/relax.py`)
1. **Painel de energia em vc-relax:** passa a mostrar **|ΔH|** (entalpia) em vez de |ΔE|, com rótulo do eixo "|ΔH| (Ry)" e o mesmo limiar `etot_conv_thr` (é a entalpia que o BFGS compara a
   esse limiar). Em `relax`, nada muda (|ΔE|). Quando `enthalpy_ry` não existe em algum passo, os pares sem H caem para |ΔE| com a nota "entalpia indisponível neste passo".
2. `RelaxParams.panels` ganha **`all`**: acrescenta, abaixo dos dois painéis de hoje, **Pressão (kbar)** (linha com marcadores; limiar `press_conv_thr` em torno de `target_pressure_kbar`) e **Volume (Å³)**
   (linha). `both` (padrão) e `.plot` antigos continuam válidos e idênticos; `all` num relax sem dados cai em `both`.
3. `EXPORT_STEMS` e `param_schema` incluem o novo valor; o painel de ajustes mostra "Painéis: ambos | energia/entalpia | força | todos".
4. Readout (`RenderInfo.summary`): vc-relax acrescenta "V: 334,3 → 321,0 Å³ · P final = 0,12 kbar" quando há dados. `format_coordinates` informa o painel novo.
5. **Figuras de referência:** `test_figure_regression.py` e os testes de `test_relax.py` sem vc-relax passam sem mudança de artistas; a figura do vc-relax da fixture é nova (golden criado, sem
   reutilizar uma que já existisse).
6. Testes: vc-relax da fixture com `both` → rótulo "|ΔH|"; `all` → 4 painéis com limiar de pressão; `relax` comum com `all` → `both`; passo sem entalpia → nota e fallback; log/linear; cores.

### R3: Resumo
1. `core/qe/summary/` (spec 12) usa os novos campos do mesmo fluxo para acrescentar, em "Resultados" de um vc-relax, "Volume inicial/final", "Pressão final" e "Entalpia final" (as linhas `Final enthalpy`
   já existem). Sem os dados, as linhas não aparecem. `tests/test_summary_*.py` ganham os casos da fixture.

## Fora de escopo
- Gráfico dos parâmetros de rede (a, b, c, α, β, γ) por passo: o dado fica disponível (`cell`), a figura é decisão futura.
- Outro critério (tensor de tensões completo), `cell_dofree`, `cell_factor` ou `calculation = 'md'`.
- Fixtures vc-relax novas: a spec usa a única existente; saídas reais de `press ≠ 0` do usuário entram depois em `tests/fixtures/qe<ver>_<sistema>/` (regra do `CLAUDE.md`).
- "Gerar SCF convergido" (não é afetado).

## Decisões assumidas (confirmar na revisão)
1. Em vc-relax o painel de energia **muda de |ΔE| para |ΔH|** sem opção para voltar: com `press = 0` os dois coincidem, com `press ≠ 0` só |ΔH| é o critério do QE.
2. `all` é um valor novo de `panels` (não muda o padrão), para não alterar figuras e `.plot` existentes.
3. A entalpia do primeiro passo é derivada de `E + P·V` quando o QE não a imprime; se `press` ou o volume faltam, o par fica sem H.
4. O limiar de pressão padrão é 0,5 kbar quando nem o cabeçalho nem o input o dão (padrão do QE).

## Notas de implementação
- Alterados: `core/qe/relax.py`, `core/calculations/relax.py`, `core/qe/summary/{scan,build}.py`, `tests/test_relax.py`, `tests/test_summary_*.py`, `tests/test_figure_regression.py` (+ golden novo).
- `core/qe/relax.py` e `core/calculations/relax.py` hoje têm bastante espaço sob 500 linhas; se `relax.py` do módulo passar de ~400, o painel novo vai para `relax_panels.py`.
- `CLAUDE.md`: seção de gráficos (relax/vc-relax: entalpia, `panels = all`) e `specs/Archived/spec_6-…` fica como histórico.

## Critérios de aceite e testes
- [ ] Parser: 4 entalpias, 5 volumes, 6 pressões, 5+1 células e `Final enthalpy` na fixture; nada novo em `relax`/SCF; um passe pelo fluxo.
- [ ] `E + press·V` reproduz a entalpia impressa (< 1e-5 Ry) onde ela existe.
- [ ] vc-relax: painel "|ΔH| (Ry)" com limiar `etot_conv_thr`; `all` com pressão e volume; `both`/relax como antes (goldens intactos).
- [ ] Resumo do vc-relax com volume e pressão finais.
- [ ] `test_perf_detection.py` (relax de 200 MB) dentro do orçamento; `ruff`, `pyright`, `test_architecture.py` verdes.
