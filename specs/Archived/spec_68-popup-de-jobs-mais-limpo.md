# Spec 68: o popup "Fila do cluster" mais limpo: datas curtas, barras coloridas e a coluna "Núcleos"

| | |
|---|---|
| **Prioridade** | 68: ajuste visual pequeno, independente das demais; refina a tela da spec 64 R5 |
| **Status** | Implementada (25/10/2026). |
| **Depende de** | spec 64 (`ui/widgets/jobs_popup.py`, `core/cluster_jobs.py`: `Job`, `JobsSnapshot`, o popup e o `qstatus -a` lido) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a spec 64 abriu (popup, tokens de tema, catálogo), sem contrato novo além de uma propriedade |

## Itens de origem (ideias de 25/10/2026, na conversa)

> - Remova o ano das datas e os segundos do horario, para que a exibição fique mais limpa.
> - Deixe a separação, entre os jobs que estão em execução e os que estão na lista de espera, mais clara. Coloque uma cor mais nitida nas barras de 'Running' e 'Queued'.
> - Substitua a coluna 'Queue' pela coluna de 'slots'. Quero que troque a palavra 'slots' por 'cores'.

Interpretação: "Running", "Queued" e "Queue" são os textos que o usuário vê com `ui.language: en` ("Em execução ({n})", "Na fila ({n})" e
"Fila" no catálogo). "Barras" são as duas linhas de título das seções. A coluna de "slots" é a `#` do `qstatus` (`Job.slots`), a que
hoje só aparece no tooltip.

## Situação atual

- **R1 (datas).** `ui/widgets/jobs_popup.py:181` põe `job.date` na coluna "Envio / início" como o cluster a escreve:
  `10/15/2026 17:53:02` (`Job.date`, `core/cluster_jobs.py:42`, montado por `_job` `:84` de `"{day} {clock}"`).
- **R2 (barras).** `_section` (`:170-177`) escreve o título da seção em negrito com `text_secondary` e sem fundo; os filhos ficam sem recuo
  (`setIndentation(0)`, `:115`). As duas listas só se distinguem pelo texto.
- **R3 (coluna).** O cabeçalho é `[Nome, Dono, Envio / início, Fila]` (`:113`) e a quarta coluna é `job.queue` (`physica.q`, igual em quase toda
  linha; vazia na espera). `job.slots` só aparece no tooltip: `"job-ID {job_id} · {slots} slots"` (`:183`).
- Tamanhos: `ui/widgets/jobs_popup.py` 232 linhas, `core/cluster_jobs.py` 158. Os testes que guardam esse texto:
  `tests/test_jobs_ui.py:182-210`.

## Requisitos

### R1: datas sem o ano e sem os segundos

1. `Job.short_date` (propriedade, `core/cluster_jobs.py`): `10/15/2026 17:53:02` → `10/15 17:53`. A ordem continua a do cluster (mês/dia); `Job.date`
   não muda.
2. A coluna "Envio / início" mostra `short_date`; o tooltip da linha guarda a data inteira (R3.3).
3. **Testes** (`tests/test_cluster_jobs.py`): `short_date` dos dois exemplos e de `1/5/2026 9:03:07` (`1/5 9:03`); `date` intacto.

### R2: barras de "Em execução" e "Na fila" com cor

1. Quatro tokens nos dois temas (`ui/resources/themes/{dark,light}.yaml`): `job_running_bg`/`job_running_fg` (verde) e
   `job_queued_bg`/`job_queued_fg` (âmbar). `_section` pinta o título (`setBackground`/`setForeground`, negrito) com eles; a linha da seção já
   ocupa a largura toda (`setFirstColumnSpanned`), então a barra vai de ponta a ponta.
2. Os jobs ficam recuados dentro da barra (`setIndentation(scaled(14))`, refeito em `_on_scale_changed`). O realce dos jobs do usuário
   (negrito, `accent_text`) não muda.
3. **Testes:** `tests/test_theme_contrast.py::test_job_bars_pass_aa_on_the_popup` (texto sobre o fundo composto sobre `popover`, AA 4,5, nos dois
   temas); `tests/test_jobs_ui.py::test_the_two_sections_are_bars_of_their_own_colour` (fundo e texto vêm dos tokens, diferentes entre as duas,
   negrito, recuo).

### R3: a coluna "Núcleos" no lugar de "Fila"

1. O cabeçalho vira `[Nome, Dono, Envio / início, Núcleos]` e a quarta coluna é `str(job.slots)`, alinhada à direita (cabeçalho e linhas). Texto
   fonte `_("Núcleos")`, inglês "Cores" (o msgid `"Cores"` em português é "colors", como em `Cores por`).
2. A palavra "slots" sai da interface do popup. `core/qsub_lint.py` ("-pe … número de slots") não muda: é o termo do SGE em outro assunto.
3. O tooltip da linha guarda o que a tabela deixa de mostrar: `job-ID 23538 · physica.q · 10/15/2026 17:53:02` (sem a fila na espera).
4. **Testes** (`tests/test_jobs_ui.py::test_the_popup_shows_both_sections_and_the_columns`): cabeçalhos, a linha de um job em execução e a de um
   na fila (`10/15 18:05`, `32`) e os dois tooltips.

## Fora de escopo

- Converter as datas para `dia/mês` ou para o fuso local: ficam como o cluster as escreve (spec 64, "Fora de escopo").
- Ordenar ou filtrar a tabela; mostrar a fila (`running in`) em coluna: só no tooltip.
- Mudar o indicador "Executando: <nome>" ou o que é consultado.

## Decisões assumidas (confirmar na revisão)

1. **"Cores" é "Núcleos" no texto fonte**, para não colidir com "Cores" (colors) do catálogo; o usuário vê "Cores" em inglês.
2. **Verde para a execução e âmbar para a fila**, as cores de `success` e `warning` do app; no escuro o fundo é translúcido (0,30 e 0,32) sobre o
   `popover`, no claro é um tom pastel.
3. **A fila e a data completa ficam no tooltip**, para não perder a informação que a tabela deixa de mostrar.

## Notas de implementação

- Alterados: `core/cluster_jobs.py` (`Job.short_date`), `ui/widgets/jobs_popup.py` (cabeçalhos, linha, tooltip, `_section` com os tokens, recuo),
  `themes/dark.yaml` e `light.yaml` (4 tokens), `tests/test_jobs_ui.py`, `tests/test_cluster_jobs.py`, `tests/test_theme_contrast.py`,
  catálogo `lain.po`/`.mo` (`Núcleos`, `job-ID {job_id}`; saem `Fila` e `job-ID … slots`), `README.md` ("Cluster jobs").
- Limites: nenhum arquivo perto de 500 linhas.
- i18n: `scripts/i18n.py update`, tradução, `compile` e `check`.

## Critérios de aceite e testes

- [x] As datas do popup não têm ano nem segundos; o tooltip as guarda inteiras (`test_cluster_jobs.py`, `test_jobs_ui.py`).
- [x] "Running" e "Queued" são barras de cores diferentes, com contraste AA nos dois temas (`test_theme_contrast.py`, `test_jobs_ui.py`).
- [x] A coluna "Fila" deu lugar a "Núcleos"/"Cores" (`test_jobs_ui.py`).
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte `-m "not realdata and not perf"` verdes.
