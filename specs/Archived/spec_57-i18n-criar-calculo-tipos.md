# Spec 57: Inglês dos tipos do "Criar cálculo" (campos, dicas, validações e o `geracao.md`)

| | |
|---|---|
| **Prioridade** | 57: a maior área de texto técnico (237 mensagens, a maioria dicas que citam o `INPUT_*` do QE). Depois da 56, que traz a janela e os termos do formulário. Independente de 53–55, 58 e 59. |
| **Status** | Implementada (19/10/2026). Ajustes ao texto: **(a)** a área tinha 156 mensagens sem tradução e 81 traduzidas (a spec dizia 161/76, contado antes da 56); com as escolhas do `pp.x` (item c) ficou com 241. Revisão das traduzidas: a dica de `fix_rule` dizia `'nenhum'` em inglês (item d). **(b)** Cinco defeitos que só apareceriam com a área traduzida, corrigidos: o título das abas de grupo (`Superfície`, `Molécula`, `Sítio`, `Átomos`, `Supercélula`) era o token cru em `ui/dialogs/calc_create/tabs_page.py` (agora `_(group)`); a regra em `geracao.md` (`regra '{rule}'`), a coordenação (`monodentado (sítio pela …)`) e as regras citadas nas dicas dos átomos fixos iam sem `_()`; `invertida` não estava marcado. As novas chamadas dinâmicas estão em `DYNAMIC`. **(c)** As escolhas de `iflag`/`output_format` eram `f"{código} — {_(rótulo)}"`: o **dado** do combo mudaria com o idioma. Agora cada escolha é um texto inteiro marcado com `N_` (`"3 — grade 3D"`, igual ao de antes em pt), e a mensagem de `iflag × output_format` tira o rótulo traduzido por `label_of`. **(d)** A dica de `fix_rule` passou a `'{NONE}'` (antes `'nenhum'` literal) e a de `fix_fraction` diz `0.5` (tinha vírgula decimal, contra a regra do CLAUDE.md); fora isso o pt não muda. **(e)** R1.4: `check_positive` lê inteiro em inglês na mesma ordem (`The minimum vacuum must be greater than zero`), então nenhuma mensagem passou a `{campo}`. **(f)** R1.2: `CODE_TOKENS` ganhou namelist + variável (`&CONTROL nstep`), variáveis com sublinhado e uma lista curta de variáveis sem sublinhado (`QE_NAMES`: `nstep`, `nbnd`, `degauss`…); as traduções de 53–56 continuaram verdes. Novo `fragment_leaks` (um token curto da área dentro de uma frase em inglês) e verificação de letras acentuadas nos fatos em inglês. **(g)** Cenários em `tests/i18n_scenarios_57.py`: `calc_create_<tipo>` e `calc_create_validation_<tipo>` para os 10 tipos, mais `slab_files` (R2.2, Slab com a molécula). Entraram nos mesmos processos do probe (os 21 levam 4 s; o probe inteiro, ~10 s), sem fixture própria, e sem `demo_project`: o projeto do probe faz o papel dele. **(h)** O cabeçalho `Configuração do pw.x` do `.qsub` ficou em português (decisão 1). **(i)** Glossário de `locale/README.md`: termos das superfícies. **(j)** Passo manual (R4.2): conferido sem tela pelo probe (os dez tipos nos dois idiomas, e a Slab com `.in` e `.qsub` iguais byte a byte); abrir `QE_STUDIO_LANGUAGE=en uv run lain` fica para o usuário. Medido: 4122 passed, 2 skipped na suíte da CI (4083 na 56); `tests/test_i18n.py` 132 testes. |
| **Depende de** | spec 52 (portão, probe, glossário, `test_code_tokens_are_kept` da 54); spec 56 (termos do formulário, `report_text`); spec 54 R1.2 (vocabulário de física) |
| **Usada por** | 60 |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): as dicas descrevem parâmetros do QE e uma tradução que troca um nome de palavra-chave ou o sentido de uma regra produz um input errado sem erro visível. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 57 de `AREAS` (spec 52 R2): `core/calc_create/types/`: os 10 tipos de `REGISTRY` (`types/__init__.py:48`: SCF, Relax, vc-relax, Bandas,
PDOS, Carga, Diferença de carga, Slab, Supercélula, Molécula na superfície/`adsorption`), os `*_fields`, `fields`, `base`, `files` e `script`.

## Situação atual

Contagem da 52 (`check --area 57`, 18/10/2026): **237 mensagens, 161 sem tradução**, 76 traduzidas e não revisadas. O
diretório tem 3169 linhas em 18 arquivos (o maior, `base.py`, 351; `adsorption_fields.py`, 325; `adsorption.py`, 313).

- **R1 (dicas com nomes do QE).** 31 campos têm `tooltip=`. Muitas dicas começam por uma palavra-chave do QE e a explicam:
  `_("&CONTROL nstep: número máximo de passos da otimização")`, `_("&CONTROL forc_conv_thr, em Ry/Bohr")`,
  `_("&CELL press: pressão externa alvo, em kbar")`. Três literais são exceções explícitas do verificador estático
  (`tests/i18n_static.py`, `EXCEPTIONS`): `"&IONS ion_dynamics"` (`types/relax.py:71`), `"&CELL cell_dynamics"`
  (`types/vc_relax.py:39`), `"Pools (nk)"` (`types/script.py:56`): são dicas que só levam o nome do parâmetro.
- **R2 (relatório em arquivo).** `types/slab.py:97` e `types/supercell.py:151` (e `types/adsorption.py`) montam as linhas do
  `geracao.md` com rótulos por `_()` (`Facts = list[tuple[str, str]]`, `adsorption.py:77`) e as passam a `report_file`
  (`core/calc_create/surface/report.py:35`, spec 56). O conteúdo é gravado em disco (spec 56 R2).
- **R3 (valores de escolha).** `FormField.choices` guarda os **valores** (`types/base.py:64`) e a janela mostra `_(valor)`
  (spec 56 R2): cada valor do tipo precisa estar em `N_()` na origem. Nenhum teste varre os `FormField` dos tipos
  registrados.
- **R4 (inglês em arquivo de cálculo).** Os templates de input não têm texto em português (`resources/templates/qe/`,
  conferido por `grep` de acentos); o único é o cabeçalho de `resources/templates/qsub/_base.qsub.j2:3`
  (`########       Configuração do pw.x         ########`), gravado no `.qsub` que vai para o cluster. As mensagens de
  `core/qsub_lint.py` (área 54) leem o `.qsub` e não dependem desse comentário.
- **R5 (fragmentos).** `check_positive(work, chave, rótulo)` compõe a mensagem de validação a partir do rótulo
  (`types/slab.py:103-104`, `types/supercell.py:187`, `types/adsorption.py:167-170`, `types/adsorption_fields.py:288`:
  `BOND_SCALE: _("A tolerância de ligação")`). Mesmo ponto da 56 R3.

## Requisitos

### R1: Traduzir a área sem alterar o QE

1. Traduzir as 161 mensagens de `scripts/i18n.py check --area 57` e revisar as 76 já traduzidas. Termos: `Slab` →
   `Slab`; `Supercélula` → `Supercell`; `Molécula na superfície` → `Molecule on surface`; os nomes dos tipos
   (`SCF`, `Relax`, `vc-relax`, `Bandas`, `PDOS`, `Carga`, `Diferença de carga`) em inglês correspondente (`SCF`, `Relax`,
   `vc-relax`, `Bands`, `PDOS`, `Charge`, `Charge difference`).
2. Toda palavra-chave do QE, namelist (`&CONTROL`, `&IONS`), nome de arquivo e unidade (`Ry/Bohr`, `kbar`) fica **idêntica**
   na tradução. `test_code_tokens_are_kept` (spec 54 R1.3) roda sobre a área e é o guarda; uma tradução que o reprove é
   corrigida no `.po`, nunca o teste.
3. As dicas que só levam o nome do parâmetro (`&IONS ion_dynamics`, `&CELL cell_dynamics`, `Pools (nk)`) ficam como
   dados (continuam em `EXCEPTIONS`, cada uma com o motivo).
4. `check_positive` e funções parecidas: a mensagem final em inglês se lê inteira (`The adsorption distance must be
   positive`); onde a ordem exigir, uma mensagem com `{label}` (mesma regra da 56 R1.2).
5. Plurais por `ngettext`, duas formas.

### R2: O relatório e os arquivos gerados

1. Rótulos e frases das linhas do `geracao.md` (Slab, Supercélula, Molécula na superfície) em inglês, com os números e a
   ordem das linhas intactos.
2. **Testes (os de ponta a ponta que a 56 R2.2 adiou):** em subprocesso, a mesma Slab criada em `pt_BR` e em `en` (fixture
   `demo_project`, helpers de `tests/calc_helpers.py` e `surface_helpers`) gera:
   (a) dois `geracao.md` com o mesmo conjunto de números e a mesma ordem de linhas e rótulos no idioma de cada um;
   (b) os mesmos `pw.in`/`relax_*.in`, **byte a byte**; nenhuma mensagem traduzida em arquivo `.in`;
   (c) o mesmo `.qsub` (R2.3).
3. O cabeçalho `Configuração do pw.x` de `_base.qsub.j2:3` **fica em português** nos dois idiomas (é comentário num arquivo do
   cluster; ver decisão 1); o teste de (c) prova que o `.qsub` não muda com o idioma.
4. O texto do `geracao.md` gravado é igual ao da aba "Arquivos" (prévia), nos dois idiomas.

### R3: Valores de escolha e cenários

1. `test_choice_values_are_marked`: para cada tipo de `REGISTRY` de `calc_create`, todo valor de `FormField.choices`
   está no catálogo `en` (marcado com `N_()` na origem) e `test_combo_data_is_the_value` (spec 56) passa para todos.
2. `tests/i18n_probe.py` ganha `calc_create_<tipo>` para os 10 tipos (passo 1 em modo Avançado, com todas as abas do passo 2 e
   o tooltip de cada campo lido por `toolTip()`), e `calc_create_validation_<tipo>` com o campo obrigatório vazio e um valor
   inválido por tipo que tenha `check_positive`.
3. `test_no_leaks_in_english[<cenário>]` para os cenários novos.

### R4: Fechar a área

1. `update`, `compile`, `DONE |= {57}`; `test_untranslated_only_in_pending_areas` passa.
2. Passo manual: criar um cálculo de cada tipo em `en`, ler o `.in` gerado ao lado do de `pt_BR`: iguais.

## Fora de escopo

- Traduzir `_base.qsub.j2` e comentários de inputs (decisão 1).
- Mudar o que cada tipo gera, os padrões dos campos ou as regras de validação.
- A janela e o pacote `surface/`: 56.

## Decisões assumidas (confirmar na revisão)

1. **O que o Lain escreve em arquivos que vão ao cluster fica em português**: o cabeçalho do `.qsub` (R2.3) e qualquer
   comentário de input. O `geracao.md` é a exceção (56 R2): é uma nota para a pessoa, vista na prévia no mesmo idioma.
   Se o usuário preferir, o `.qsub` pode ganhar versão em inglês, mas isso exige duas cópias do template e a mesma
   regra no teste; ficou fora.
2. A tradução dos nomes dos tipos (R1.1) usa os nomes que o usuário já vê na lista; `Slab` e `PDOS` ficam como nomes de campo.
3. A Opus é recomendada pelo risco de uma dica alterar a palavra-chave do QE sem que um teste de comportamento apareça;
   `test_code_tokens_are_kept` reduz o risco, mas não o elimina para o texto em volta.

## Notas de implementação

- Novos: nenhum arquivo de código.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`; `tests/i18n_areas.py`; `tests/i18n_probe.py`;
  `tests/test_i18n.py` (R2.2, R3.1); `tests/i18n_static.py` (`EXCEPTIONS`: cada linha com o motivo, ou removida).
- Limites: `types/base.py` (351), `adsorption_fields.py` (325), `adsorption.py` (313): nenhum chega a 500; a spec não
  adiciona linhas além do que R1.4 pedir.
- Documentação ao implementar: nenhuma.

## Critérios de aceite e testes

- [ ] Goldens e suíte de hoje passam sem regenerar; os `.in` e `.qsub` gerados em `pt_BR` não mudam.
- [ ] `check --area 57` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] `test_code_tokens_are_kept` verde sobre a área; vermelho num catálogo sintético que troca `nstep` por `steps`.
- [ ] Slab em `pt_BR` e `en`: `.in` e `.qsub` idênticos, `geracao.md` com as mesmas linhas (R2.2).
- [ ] `test_choice_values_are_marked`, `test_combo_data_is_the_value` e `test_no_leaks_in_english` para os cenários de R3.2.
- [ ] Plurais da área com as duas formas.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
