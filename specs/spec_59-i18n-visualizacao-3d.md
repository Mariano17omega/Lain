# Spec 59: Inglês da Visualização 3D (janela, painel, medidas, "Print" e vista lembrada)

| | |
|---|---|
| **Prioridade** | 59: a área com mais texto **pintado** (rótulos de átomos, eixos, medidas), que o detector de widgets da 52 não vê, e com identificadores em português guardados no `view3d.plot`. Independente de 53–58. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 52 (portão, probe, glossário); specs 43, 44, 46 e 47 (janela 3D, medidas, ajustes, vista lembrada) |
| **Usada por** | 60 |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): área pequena e já marcada; o cuidado é separar identificador de rótulo e testar o texto pintado pelo modelo. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 59 de `AREAS` (spec 52 R2): `core/structure3d/`, `ui/widgets/structure3d/`, `ui/structure3d_controller.py`.

## Situação atual

Contagem da 52 (`check --area 59`, 18/10/2026): **122 mensagens, 68 sem tradução**, 54 traduzidas e não revisadas
(`panel.py` 37, `measures.py` 18, `canvas.py` 15, `panel_atom.py` 15, `window.py` 11, `core/structure3d/options.py` 10, `source.py` 7).

- **R1 (identificadores em português no `view3d.plot`).** `core/structure3d/options.py:34-44` mapeia **id → rótulo**:
  `"vareta": _("Vareta")`, `"fio": _("Fio")`, `LABEL_MODES` (`"nenhum"`, `"simbolo"`, `"indice"`, `"ambos"`),
  `BACKGROUNDS` (`"escuro"`, `"claro"`), e `labels: str = "nenhum"` (`:67`, comentário: "a LABEL_MODES id: data, never
  translated"). Os ids são os valores gravados no `view3d.plot` (spec 47) e **não mudam**.
- **R2 (texto pintado).** O desenho é por `QPainter`: `ui/widgets/structure3d/overlay.py:69` (número do selo da medida),
  `:84` (`"xyz"[k]`), `:105` (rótulos dos átomos: símbolo ou número, vindos do dado) e `:122` (`a`, `b`, `c` dos vetores
  da célula). São letras e números, sem palavra em português; o texto que **tem** palavra é o das medidas
  (`ui/widgets/structure3d/measures.py:91`, a tabela) e o do painel, ambos por widgets.
- **R3 (texto das medidas).** `core/structure3d/measurements.py:33` `KIND_LABEL = {"distancia": _("Distância"),
  "angulo": _("Ângulo")}`; `:89` `to_tsv` copia a lista para a área de transferência com cabeçalho por
  `_("Medida\tÁtomos\tValor")` e a coluna do tipo por `KIND_LABEL`; `ui/widgets/structure3d/measures.py:300-302` chama
  `to_tsv` ao copiar. Em `en` o texto copiado muda de idioma; os valores numéricos e as unidades (`Å`, `°`) não.
- **R4 (armadilha do `_`).** Funções da área ligam o nome `_` por desempacotamento e os seus arquivos **ainda não importam** `_()`:
  `ui/widgets/structure3d/renderer.py:257`, `:262` e `:384`, `overlay.py:118` (`tips, _, _ = camera.project(...)`, na função
  que desenha `a`, `b`, `c`) e `bonds_paint.py:99-101`. Ao embrulhar um texto numa dessas funções, `_("...")` vira
  `UnboundLocalError` (a 52 R4.2 acha o padrão; hoje só `ui/palette_controller.py:221` o tem entre os arquivos que importam `_`).
- **R5 (arquivos).** O nome do PNG do "Print" não leva idioma (`core/structure3d/image_file.py:21-40`: `print_stem` e
  `plots/<stem>.png`, com `_2`, `_3`…).

## Requisitos

### R1: Traduzir a área

1. Traduzir as 68 mensagens de `scripts/i18n.py check --area 59` e revisar as 54 já traduzidas. Termos: `Vareta` →
   `Stick`, `Fio` → `Wire`, `Nenhum`/`Símbolo`/`Número`/`Ambos` → `None`/`Symbol`/
   `Number`/`Both`, `Escuro`/`Claro` → `Dark`/`Light`, `Distância`/`Ângulo` → `Distance`/`Angle`, `Rotação` →
   `Rotation`, `Apagar` → `Delete`, `Print` → `Print`, `Restaurar padrões` → `Restore defaults`.
2. Os ids de R1 (`vareta`, `fio`, `nenhum`, `simbolo`, `indice`, `ambos`, `escuro`, `claro`, `distancia`, `angulo`) ficam; nenhum
   passa por `_()` onde é comparado ou gravado.
3. Renomear os `_` locais de R4 (`_depth`, `_scale` ou `__`, conforme o caso) **antes** de embrulhar qualquer texto nessas
   funções; `test_no_local_underscore` (52 R4.2) é o guarda.
4. Plurais por `ngettext` com as duas formas.

### R2: O que é copiado e o que é gravado

1. `to_tsv` em `en` produz `Measure\tAtoms\tValue` e `Distance`/`Angle` na primeira coluna; os números e a ordem das linhas
   são os de `pt_BR`. Decisão 1: o TSV é texto para a pessoa colar numa planilha e segue a interface, ao contrário do CSV
   da exportação do gráfico (spec 55), que é arquivo guardado.
2. O `view3d.plot` gravado em `pt_BR` e relido em `en` **não muda** (mesmo JSON): teste em subprocesso com o probe
   (`--plot-file`, spec 55 R3.1) sobre os ajustes de cada id de R1 alterado.

### R3: Cenários e texto pintado

1. `tests/i18n_probe.py` ganha: `view3d_window` (a janela com a estrutura de um `scf.in`, barra, painel, cada seção aberta),
   `view3d_measures` (uma distância e um ângulo na tabela, com o menu de contexto da tabela construído sem `exec`),
   `view3d_atom_panel` (átomo selecionado) e `view3d_print` (o diálogo ou a mensagem do "Print").
2. `test_no_leaks_in_english[<cenário>]` para os quatro; `test_measure_texts_in_english`: `to_tsv` em `en` (R2.1) e as linhas
   de `row_text` (`O1 - O2`, `1.500 Å`) iguais nos dois idiomas.
3. Texto pintado: `test_overlay_text_has_no_words`: para a estrutura do cenário, o conjunto de strings que `overlay.py`
   passa a `drawText` (interceptado por um `QPainter` espião) só tem símbolos químicos, números e `a b c x y z`; uma palavra
   em português ali é vazamento.

### R4: Fechar a área

1. `update`, `compile`, `DONE |= {59}`; `test_untranslated_only_in_pending_areas` passa.
2. Passo manual: abrir a janela 3D em `en`, medir uma distância, copiar, colar numa planilha, usar "Print".

## Fora de escopo

- Traduzir os símbolos dos elementos, `a b c x y z` ou as unidades.
- Mudar o desenho ou a ordem do `view3d.plot`.
- O botão "Visualização 3D" no menu e no menu de contexto (área 53, se tiver texto) e o "Abrir com XCrySDen" (`core/xcrysden.py`: 53).

## Decisões assumidas (confirmar na revisão)

1. O TSV das medidas segue o idioma da interface (R2.1); o CSV dos gráficos (55) é fixo. A diferença é: um é copiado e colado
   na hora, o outro fica no disco e é lido por outros programas. Se o usuário preferir um critério só, os dois ficam fixos
   (cabeçalho do TSV como está hoje, em português) ou os dois seguem a interface.
2. `Vareta` → `Stick` e `Fio` → `Wire`: as formas da legenda (uma barra por ligação, só linha), não os nomes de outros
   programas; o usuário confirma.

## Notas de implementação

- Novos: nenhum arquivo de código.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`; `ui/widgets/structure3d/{renderer,overlay,bonds_paint}.py` só para
  renomear o `_` local (R1.3); `tests/i18n_areas.py`; `tests/i18n_probe.py`; `tests/test_i18n.py`.
- Limites: conferir com `wc -l` os arquivos de `ui/widgets/structure3d/` antes de editar (a spec não adiciona linhas além
  das renomeações).
- Documentação ao implementar: nenhuma.

## Critérios de aceite e testes

- [ ] Goldens e suíte de hoje passam sem regenerar; `view3d.plot` idêntico nos dois idiomas (R2.2).
- [ ] `check --area 59` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] `test_no_local_underscore` verde nos arquivos de R4; `test_measure_texts_in_english` e `test_overlay_text_has_no_words` verdes.
- [ ] `test_no_leaks_in_english` para os quatro cenários; plurais com as duas formas.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
