# Spec 55: Inglês dos gráficos, do painel de ajustes, dos Grids e da seleção de átomos

| | |
|---|---|
| **Prioridade** | 55: a maior área (379 mensagens) e a única com texto **dentro das figuras** e em arquivos exportados; vem depois de 53 e 54 porque reusa o glossário e o vocabulário de física deles. Independente de 56–59. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 52 (portão, probe, glossário); spec 54 R1.2 (vocabulário de física); spec 32 (CSV da exportação), spec 49 (botão "Gerar") |
| **Usada por** | 60 |
| **Esforço** | G (R1: M; R2 a R4: P cada) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): o contrato dos módulos não muda; os goldens (`test_figure_regression.py`, `tests/*_golden.json`) guardam o português, e o risco é só não tocar neles. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 55 de `AREAS` (spec 52 R2): `core/calculations/` (bandas, PDOS, Bandas com DOS, relax/vc-relax, SCF, Grid),
`core/plotting/`, `core/{compounds,grid_store}.py`, `ui/{plot_button,plot_export,plot_settings,plot_workflow,generate_plot,
grid_loader}.py`, `ui/dialogs/{atoms,grid_cells,grid_dialog}.py` e `ui/widgets/{atom_table,param_widgets,params_body,
plot_params,plot_view}.py`.

## Situação atual

Contagem da 52 (`check --area 55`, 18/10/2026): **379 mensagens, 232 sem tradução**, 147 traduzidas e não revisadas
(`core/calculations/` 272 mensagens, 172 sem tradução: bandas 73/49, PDOS 37/23, Bandas com DOS 16/4, Grid 9/5, o resto
em `params.py`, `base.py`, `relax*.py`, `scf.py`, `info.py`).

- **R1 (texto dentro da figura).** São `_()` de módulo ou de função: `Valência`/`Condução`
  (`core/calculations/bands/render.py:103-104` e `:225-226`), `Passo BFGS` (`relax.py:325`), `PDOS (estados/eV)`
  (`pdos/render.py:184`). Os rótulos de energia (`Y_LABELS`, `bands/params.py:42`) são fórmulas de matemática
  (`$E - E_F$ (eV)`) e `Spin ↑`/`Spin ↓` (`bands/render.py:262-263`) valem nos dois idiomas. `bands/render.py:25`
  define `ON_PATH = _("(no caminho)")` na importação. As figuras seguem o idioma **da interface** (decisão da `spec_end`);
  o estilo vem dos parâmetros, não do tema do app (CLAUDE.md), e isso não muda.
- **R2 (texto em arquivo exportado).** O CSV da exportação (spec 32) leva a unidade da DOS no cabeçalho:
  `core/calculations/pdos/table.py:12` `DOS_UNIT = _("estados/eV")`, usada em `:35`. Com `en`, o cabeçalho do CSV mudaria
  (`states/eV`), e um script do usuário que lê as colunas de um CSV antigo deixaria de achá-las. O **nome** do arquivo
  exportado não depende do idioma: `export_stem` devolve o `kind` ou `EXPORT_STEMS` (`core/calculations/base.py:380`,
  `relax.py:67`) e o prefixo vem do caminho (`core/plotting/export.py:71-84`).
- **R3 (identificadores no `.plot`).** `ParamField.choices` é `tuple[tuple[object, str], ...]` com `(valor, rótulo)`
  (`core/calculations/params.py:64`): o valor é o dado, o rótulo passa por `_()`. As seções têm `SectionDef(id, title)` com
  o `title` em `N_()` (`params.py:20-32`). Dado e rótulo já estão separados; o teste que prova isso com a interface em
  `en` não existe. Há duas chamadas dinâmicas desta área para a 52 R4.3: `ui/widgets/param_widgets.py:133` e `:137`
  (`_(title)`), e `Method.label` em `core/calculations/base.py:128` (`return _(self.value)`; o **valor**,
  `Method.CONTENT = "conteúdo"`, é o dado persistido).
- **R4 (concatenação).** `core/calculations/bands/data.py:225` faz
  `_("Não foi possível ler os autovalores:\n") + "\n".join(errors)` (os `errors` vêm de outro `_()`); em inglês o
  resultado é correto, mas a frase não é um bloco só.
- **R5 (o que a sondagem não vê).** Texto de figura e de CSV não é texto de widget: o probe da 52 não os enxerga.

## Requisitos

### R1: Traduzir a área

1. Traduzir as 232 mensagens de `scripts/i18n.py check --area 55` e revisar as 147 já traduzidas (glossário da 52,
   vocabulário da 54). Ordem sugerida: `core/calculations/params.py` e `base.py` (rótulos comuns) → `bands/` →
   `pdos/` e `bands_dos/` → `relax*`/`scf` → `grid/` → widgets e diálogos.
2. Rótulos de figura em inglês: `Valência` → `Valence`, `Condução` → `Conduction`, `Passo BFGS` → `BFGS step`,
   `PDOS (estados/eV)` → `PDOS (states/eV)`. A fórmula e a unidade (`eV`, `Ry`, `Å`) ficam.
3. `bands/data.py:225`: trocar a concatenação por uma mensagem só, `_("Não foi possível ler os autovalores:\n{errors}")`
   com `.format(errors="\n".join(errors))`.
4. Plurais por `ngettext`, duas formas.

### R2: O CSV não muda com o idioma

1. `DOS_UNIT` deixa de ser `_()`: fica o literal de hoje (`"estados/eV"`) como **dado**, num comentário que diz por quê.
   Nenhuma coluna de CSV passa por `_()`: o teste varre `PlotTable` dos módulos registrados.
2. **Testes:** em subprocesso, o CSV da PDOS (fixture `al_pdos_flat`) e o da banda (`al_bands`) são idênticos byte a byte
   com `pt_BR` e `en`; os nomes dos arquivos exportados também (`projeto-bulk-bandas-bands`, `plan_export`).

### R3: Os `.plot` e os valores não dependem do idioma

1. Em subprocesso `en`, um `<kind>.plot` gravado com `pt_BR` (fixture: um por módulo registrado, com todos os `choice`
   alterados) é carregado, regravado por `plot_settings.flush_now()` e fica **idêntico**: o JSON não muda. O teste usa o
   probe (`--plot-file`) e compara com a execução em `pt_BR`.
2. `test_choice_values_are_not_labels`: para cada módulo, cada valor de `choices` está fora do conjunto dos rótulos
   traduzidos em `en` (um valor em português que coincidisse com um rótulo mostraria que o dado foi traduzido).
3. `Method.label` em `en` devolve `name`, `content`, `inferred`, `manual` e o `.value` continua `nome`, `conteúdo`,
   `inferido`, `manual`; a UI nunca mostra `.value` (teste sobre o cenário `files_roles`).

### R4: Cenários e figuras no detector

1. `tests/i18n_probe.py` ganha: `params_<kind>` para `bands`, `pdos`, `bands_dos`, `relax`, `scf` (painel de ajustes
   aberto, todas as seções abertas); `figures` (o probe renderiza os cinco módulos com os parâmetros padrão e imprime o
   texto de todo `matplotlib.text.Text` da figura: eixos, legenda, título, anotações, texto de "sem dados"); `atoms_dialog`,
   `grid_dialog`, `export` (a pergunta de sobrescrever, `plan_export`) e `files_roles` (a tabela dos papéis dos arquivos).
2. `test_no_leaks_in_english[<cenário>]` para todos; `test_figure_text_in_english`: nenhum texto de figura é um `msgid`
   traduzido em português, e os rótulos de R1.2 aparecem em inglês.
3. Em `pt_BR`, `test_figure_regression.py` e os `*_golden.json` passam **sem regenerar**.

### R5: Fechar a área

1. `update`, `compile`, `DONE |= {55}` em `tests/i18n_areas.py`; `test_untranslated_only_in_pending_areas` passa.
2. Passo manual de aceite: gerar e exportar bandas, PDOS, relax e SCF em `en` num projeto real e abrir PNG e CSV.

## Fora de escopo

- Traduzir ou renomear colunas de CSV (R2: decisão de manter).
- Qualquer mudança de layout de figura por causa de texto mais longo (se uma legenda em inglês cortar, é defeito a abrir).
- A janela 3D (59), o Criar cálculo (56, 57) e o sync (58).
- Formato de número com vírgula.

## Decisões assumidas (confirmar na revisão)

1. **CSV com cabeçalho fixo** (R2): são dados que outras ferramentas leem; o texto que o usuário vê no gráfico muda, o
   arquivo não. A alternativa (cabeçalho no idioma da interface, como as figuras) é uma linha de código e fica descartada
   por quebrar leitores de CSV antigos.
2. **Figuras e PNG/PDF exportados seguem o idioma da interface no momento da exportação** (decisão da `spec_end`).
3. `Valência`/`Condução` → `Valence`/`Conduction` (e não `Occupied`/`Empty`): é o que o rótulo diz hoje (banda de valência).

## Notas de implementação

- Novos: nenhum arquivo de código; o probe ganha `--plot-file` e a lista de cenários.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`; `core/calculations/pdos/table.py:12` (R2.1);
  `core/calculations/bands/data.py:225` (R1.3); `tests/i18n_areas.py`; `tests/test_i18n.py`.
- Limites: conferir com `wc -l` os arquivos de `core/calculations/` antes de editar; esta spec não adiciona linhas de código
  além de R1.3 e R2.1.
- Documentação ao implementar: nenhuma (README: 60).

## Critérios de aceite e testes

- [ ] Goldens e `test_figure_regression.py` passam sem regenerar; `test_choice_values_are_not_labels` verde.
- [ ] `check --area 55` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] CSV e nome de exportação idênticos em `pt_BR` e `en` (R2.2); `.plot` idêntico nos dois idiomas (R3.1).
- [ ] `test_figure_text_in_english` e `test_no_leaks_in_english` para os cenários de R4.1.
- [ ] `Method.label` em `en`; `.value` intacto (R3.3).
- [ ] Plurais da área com as duas formas.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
