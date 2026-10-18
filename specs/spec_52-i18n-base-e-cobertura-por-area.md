# Spec 52: Internacionalização gradual: base, cobertura por área e detector de vazamento

| | |
|---|---|
| **Prioridade** | 52, primeira da série 52–60: as specs 53–59 traduzem uma área cada e usam o que esta entrega (o portão por área, o `.mo` parcial, o detector). Sem ela, o inglês só pode ser verificado no fim, que foi o que fez as duas tentativas de implementar a `spec_end` de uma vez travarem. |
| **Status** | Rascunho para revisão |
| **Depende de** | `spec_end` (R1 e R2 já no HEAD: `i18n.py`, `core/language.py`, `ui/language.py`, `scripts/i18n.py`; R3 já aplicado em `core/` e na `ui/`, sem commit ainda) |
| **Usada por** | 53, 54, 55, 56, 57, 58, 59, 60 |
| **Esforço** | M |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): define o contrato de teste (`AREAS`/`DONE`, `.mo` parcial, detector) que oito specs seguintes usam, e mexe em `scripts/i18n.py` e na rodada de testes. |

## Itens de origem (`Ideias.md`)

> Tentei implementar `specs/spec_end-internacionalizacao.md`, mas resultou em erros. Tive que interromper duas tentativas de implementação. Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. Quero que crie uma série specs para concluir o processo de internacionalização e solucionar quaisquer problemas que possam ter surgido nas tentativas de implementação anteriores, as quais foram interrompidas.

Interpretação: a `spec_end` continua sendo o desenho (gettext, português como idioma-fonte, `en` em `.po`); a série 52–60 a
divide em entregas que se verificam uma a uma. Esta spec é o "solucionar os problemas das tentativas": ela fecha o que
a árvore de trabalho deixou solto e dá às demais um jeito de provar que a sua área está pronta. As mensagens de erro
das tentativas **não foram vistas** (ver "Situação atual", R0).

## Situação atual

Medido em 18/10/2026 na árvore de trabalho (HEAD `bb3b5a6` + 99 arquivos modificados sem commit + `locale/` e
`tests/i18n_static.py` sem rastreio):

- **R0 (estado da árvore).** O HEAD tem a infraestrutura e o `core/` marcados (`6a61da0`, `bb3b5a6`). A árvore de
  trabalho (906 linhas a mais, 620 a menos, quase tudo em `ui/`) embrulha os textos da `ui/` em `_()` e traz o
  `locale/en/LC_MESSAGES/lain.po`. **Nela, a CI inteira passa:** `ruff check` e `ruff format --check` limpos, `pyright`
  0 erros, suíte `-m "not realdata and not perf"` 3979 passed, 2 skipped (5 min 20 s) e `uv run python
  tests/i18n_static.py` sem achados. O erro das tentativas **não se reproduz** no disco: o que sobrou delas é trabalho
  sem commit, sem teste que o proteja e sem inglês compilado (abaixo).
- **R1 (catálogo sem `.mo`).** `locale/en/LC_MESSAGES/lain.po` tem 1514 mensagens (34 plurais), **954 sem tradução**, 0
  *fuzzy*. Não existe `lain.mo`: `scripts/i18n.py:compile_catalog` recusa compilar enquanto `problems()` achar uma
  mensagem sem tradução, então nada foi compilado e `en` mostra português em tudo. Compilando as 560 traduzidas num
  diretório temporário e abrindo a janela com `en` (`scripts/screenshot.py --plot` sob `i18n.install("en")`), a janela
  sai **misturada** ("File", "Tools", "Help", "Generate Plot" em inglês; "Navegar", "Árvore", "Valência" em
  português): é o estado intermediário esperado numa tradução gradual, e hoje ninguém o mede.
- **R2 (nenhum teste de i18n).** `tests/i18n_static.py` (180 linhas) é um verificador com `check_tree()`, mas não há
  `tests/test_i18n.py` que o chame: nada impede que a `ui/` volte a ter texto fora de `_()`. `problems()` só vê vazio e
  *fuzzy*: nenhuma checagem de que a tradução mantém os `{campos}`, as tags e os `&` da fonte (nas 560 traduzidas,
  conferido à mão: 0 desencontros reais; 2 alarmes falsos, `${ sem } na linha` e `<pasta>/<nome>.xsf`).
  O verificador também **tem um ponto cego**: só vê literal com acento ou passado a um destino de texto
  (`SINKS`). `ui/widgets/explorer.py:39` faz `ERROR_BADGE = "ERRO"` (a etiqueta vermelha da spec 50, pintada por
  `paint_badge`, sem acento e fora de `SINKS`): em `en` a árvore mostraria "ERRO" ao lado de "ERROR" do `STATES`. Uma
  busca por palavras comuns do português (`erro`, `aviso`, `arquivo`, `pasta`, `nenhum`, `sem`, `não`…) nos literais
  não marcados acha esse e mais alguns que precisam de triagem (`nenhum` em `core/calc_create/surface/merge.py:145`
  e `core/calculations/bands/data.py:250`, `ERRO`/`SEM ERROS`/`AVISO` como chaves em `core/file_kinds.py:91-99`:
  não verificado quais são dado e quais são texto).
- **R3 (idioma só na partida).** `_()` é avaliado ao importar: 60 atribuições de módulo e 37 com um nível de recuo
  (atributos de classe, locais) usam `_(` (`grep -E '^(    )?[A-Za-z_]+ *(:[^=]*)?= *.*\b_\('`). Por isso
  `__main__.main` instala o idioma antes de importar a aplicação (conferido: depois de `install_startup_language` só
  `core.config`, `core.fontscale`, `core.language`, `i18n` e `ui.language` estão carregados), e **o idioma não troca
  dentro do mesmo processo**. A `spec_end` R4.2 ("com `LAIN_LANGUAGE=en` o fixture `main_window` monta a janela")
  não é possível como escrita. `scripts/screenshot.py` (236 linhas) importa a aplicação dentro de `main()`
  (`:149-153`) mas nunca instala idioma: toda captura sai em português e não existe `--language`.
- **R4 (armadilhas).**
  - `ui/palette_controller.py:221` faz `kind, _, value = key.partition(":")` em `execute`; o arquivo importa `_` (`:23`).
    Funciona porque `execute` não chama `_()`; um `_("...")` ali viraria `UnboundLocalError`.
  - Seis chamadas `_(variável)` que o `pybabel` não extrai e que só funcionam se o dado de origem foi marcado com
    `N_`: `ui/widgets/filter_bar.py:93` e `:167`, `ui/widgets/param_widgets.py:133` e `:137`,
    `ui/dialogs/calc_create/form.py:171`, `core/calculations/base.py:128` (`Method.label`). Nenhum teste as cobre.
  - `ui/main_window.py` tem 449 de 450 linhas.
- **R5 (detector de vazamento: sondagem).** Com o `.mo` temporário em `en`, os 172 textos visíveis da janela principal
  (menus, botões, dicas, abas) não incluíam nenhum texto **já traduzido** mostrado em português (0 vazamentos);
  os 31 textos acentuados que sobraram são mensagens ainda sem tradução. O vazamento só aparece quando uma mensagem
  traduzida chega à tela por um caminho que não passou por `_()`; a sondagem mostra que o detector é viável.
- **R6 (documentação).** `CLAUDE.md` ainda diz que os textos "são **Portuguese**" sem falar de `_()`; `README.md` não cita
  `ui.language`. O fluxo (`scripts/i18n.py update` → traduzir → `compile`) só está no docstring do script.

## Requisitos

### R0: Ponto de partida

1. A árvore de trabalho é o ponto de partida: **o usuário a commita antes de implementar** (a spec não faz commit). Quem
   implementa roda primeiro `uv run ruff check . && uv run ruff format --check . && uv run pyright` e a suíte, e confirma
   os números de "Situação atual" (3979 passed). Se algo falhar nesse momento, é o erro das tentativas: corrige-se
   aqui, com teste.
2. Cada spec seguinte (53–59) começa numa árvore limpa e termina com o `.po` e o `.mo` commitados juntos.

### R1: `.mo` parcial e `check` por área

1. `scripts/i18n.py compile` passa a escrever o `.mo` **com as mensagens traduzidas** (o `write_mo` do babel já omite as
   vazias e as *fuzzy*); recusa (nada escrito, saída 1) só mensagem *fuzzy* ou com desencontro de marcadores (R3).
   Imprime `en: <caminho do .mo> (N traduzidas, M em português)`.
2. `scripts/i18n.py check` imprime uma tabela `área → total / sem tradução` (as áreas de R2) e sai 1 se houver qualquer
   pendência; `check --area N` (N = número da spec da área) lista as mensagens pendentes da área, com o arquivo de cada
   uma. É a lista de trabalho de cada spec 53–59.
3. O `lain.mo` atual (as 560 traduzidas) é commitado: `uv run lain` com `en` mostra a janela mista de R1 até a spec 60.
4. **Testes** (`tests/test_i18n.py`, com `Catalog` sintético): compilar com uma mensagem vazia escreve o `.mo` sem ela;
   com *fuzzy* ou desencontro, não escreve e devolve o problema; `check --area` devolve só as mensagens da área.

### R2: Portão por área (`AREAS`, `DONE`)

1. `tests/i18n_areas.py` (importado como os outros `tests/*_helpers.py`): `AREAS: dict[str, int]` (prefixo de arquivo,
   relativo a `src/qe_studio`, → número da spec que o traduz; vale o **prefixo mais longo**; o que não casa é da 53) e
   `DONE: set[int] = set()` (cada spec 53–59 acrescenta o seu número ao terminar). A tabela inicial (conferida contra o
   `.po`: nenhuma mensagem fica sem dono; 55 mensagens são compartilhadas entre áreas):

   | Spec | Área (prefixos) | Mensagens (total / sem tradução) |
   |---|---|---|
   | 53 | o que não casa abaixo: `ui/*.py`, `ui/dialogs/*.py`, `ui/theme/`, `ui/widgets/{explorer,breadcrumb,bars,workspace,context_menu,toast,command_palette,nav_sections,project_combo,file_card,filter_bar,file_grid,search_bar}.py`, `core/*.py`, `i18n.py` | 315 / 181 |
   | 54 | `core/qe/`, `core/{text_preview,textfile,qsub_lint}.py`, `ui/widgets/{text_viewer,diff_view,input_view,summary_view,summary_widgets,markdown_view,code_view}.py` | 237 / 158 |
   | 55 | `core/calculations/`, `core/plotting/`, `core/{compounds,grid_store}.py`, `ui/{plot_button,plot_export,plot_settings,plot_workflow,generate_plot,grid_loader}.py`, `ui/dialogs/{atoms,grid_cells,grid_dialog}.py`, `ui/widgets/{atom_table,param_widgets,params_body,plot_params,plot_view}.py` | 379 / 232 |
   | 56 | `core/calc_create/*.py` (raiz), `core/calc_create/surface/`, `ui/dialogs/calc_create/`, `ui/widgets/kpath_editor.py`, `ui/{calc_create_controller,derive_controller}.py` | 187 / 129 |
   | 57 | `core/calc_create/types/` | 237 / 161 |
   | 58 | `core/sync/`, `ui/sync_coordinator.py`, `ui/dialogs/{sync_dialog,sync_pages}.py` | 104 / 59 |
   | 59 | `core/structure3d/`, `ui/widgets/structure3d/`, `ui/structure3d_controller.py` | 122 / 68 |

   (Contagem por mensagem com ao menos um local na área, medida com o `.po` de hoje; `check` a refaz.)
2. `test_untranslated_only_in_pending_areas`: monta o catálogo em memória (`scripts/i18n.update(extract(), "en")`) e
   falha se uma mensagem sem tradução tiver **algum** local numa área em `DONE`, ou se houver mensagem *fuzzy*. A
   mensagem usa o formato `área N: '<texto>' (<arquivo>)`, no máximo 20 linhas. Hoje passa (`DONE` vazio).
3. `test_po_follows_the_code`: depois de `update(extract())`, o `.po` não ganha nem perde mensagem (falha com "rode
   `scripts/i18n.py update`"). `test_mo_follows_po`: o `lain.mo` existe e tem exatamente as traduções não vazias do
   `.po` (falha com "rode `scripts/i18n.py compile`").
4. Quando a 60 termina, `AREAS`/`DONE` somem e o primeiro teste passa a exigir tudo traduzido.

### R3: Paridade de marcadores e plurais

1. `scripts/i18n.py:problems()` ganha: o conjunto de `{campo}` (regex sem espaços, com `!r` e formato:
   `\{[A-Za-z_][A-Za-z0-9_]*(?:![rsa])?(?::[^{}]*)?\}`), o das tags `<...>` e a contagem de `&` da tradução devem ser
   iguais aos da fonte; nos plurais, a forma 0 contra o `msgid` e a forma 1 contra o `msgid_plural`.
2. Plural: o cabeçalho do `.po` `en` tem `nplurals=2; plural=(n != 1)` e toda entrada com `msgid_plural` traduzida tem as
   duas formas preenchidas.
3. **Testes:** `test_i18n.py` com catálogo sintético (campo a menos, campo a mais, `{n!r}`, tag perdida, `&` perdido,
   plural com uma forma só: cada um é problema; a tradução correta, não) e o teste sobre o catálogo real (hoje passa: as
   duas exceções `${ sem } na linha` e `<pasta>/<nome>.xsf` não casam com a regex).

### R4: Armadilhas do `_()`

1. `test_i18n.py` chama `i18n_static.check_tree()` e exige zero achados (passa hoje).
2. `test_no_local_underscore`: para cada função (e módulo) de `src/qe_studio` que **chama** `_(...)`, nenhum nome `_` é
   ligado no mesmo escopo (atribuição, `for`, desempacotamento, `with … as`, parâmetro; compreensões e `lambda`
   têm escopo próprio e ficam de fora). Conserta `ui/palette_controller.py:221` (`kind, _sep, value = …`).
3. `test_dynamic_translations_are_declared`: as chamadas `_(não literal)` são exatamente as seis de "Situação atual",
   numa lista `DYNAMIC` do teste; uma nova exige acrescentá-la ali, e o comentário da lista diz que o dado de origem
   precisa de `N_`. Para cada uma, o teste de runtime correspondente é pedido na spec da área (53: `filter_bar`;
   55: `param_widgets` e `Method.label`; 56: `form.py`).

4. **Ponto cego do verificador.** `tests/i18n_static.py` ganha `PORTUGUESE_WORDS` (lista curta de palavras que não
   são identificadores nem siglas: `erro`, `erros`, `aviso`, `arquivo`, `pasta`, `nenhum`, `nenhuma`, `sem`, `não`,
   `abrir`, `fechar`, `salvar`, `cancelar`…; **sem** `dos`, que é a sigla de densidade de estados) e acha literal não marcado com uma
   delas, com a mesma lista de exceções. Os achados reais são consertados aqui (`ERROR_BADGE = N_("ERRO")` e o
   desenho da etiqueta por `_(ERROR_BADGE)`, em `ui/widgets/explorer.py`); o que é dado fica em `EXCEPTIONS` com o motivo.
   Teste: `test_static_finds_unaccented_portuguese` (a fonte antiga de `explorer.py:39`, em string, é achado; o novo, não).
   O probe de R5 só enxerga **texto de widget**: texto pintado (etiquetas da árvore e da grade, rótulos de figura,
   desenho 3D) é coberto por teste de modelo ou de dado na spec da área.

### R5: Detector de vazamento em subprocesso

1. `tests/i18n_probe.py` (script, não teste): `python tests/i18n_probe.py --language en --project DIR --scenario main
   --scenario plot`. Instala o idioma **antes** de importar a aplicação, monta a janela como `scripts/screenshot.py`
   (extraia `open_window(project, tmp, theme_name, scale)` de `main()` e importe-o por caminho; não duplique) e,
   por cenário, imprime um JSON `{cenário: [textos]}` com todo texto visível: `text()`, `toolTip()`, `windowTitle()`,
   `placeholderText()`, `title()` dos widgets, as abas (`tabText`, `tabToolTip`), as ações de todos os menus
   (recursivo) e os cabeçalhos de modelo (`columnCount()` falha em modelo de lista: `try/except TypeError`). Sem `&`
   (mnemônicos) na comparação. Com `QT_QPA_PLATFORM=offscreen`, `XDG_*` num diretório temporário e a exceção não tratada
   **derrubando** o subprocesso (o `excepthook` abriria um diálogo modal que trava: o script o troca por `sys.exit(1)`).
2. Cenários que esta spec entrega: `main` (janela com `demo_project`, `03_bands/bands.in` aberto, como `screenshot.py`)
   e `plot` (o gráfico de bandas gerado). Cada spec 53–59 acrescenta os seus (diálogo aberto etc.) num dicionário
   `SCENARIOS` do probe.
3. `tests/i18n_helpers.py:probe_texts(language, *scenarios)` roda o probe (`sys.executable`, 60 s) e devolve o dict;
   `leaks(texts, catalog)` devolve os textos iguais a um `msgid` do `en` **cuja tradução é não vazia e diferente**:
   vazamento = mensagem traduzida mostrada em português.
4. `test_no_leaks_in_english[main|plot]`: zero vazamentos. `test_portuguese_unchanged[main]`: com `pt_BR`, os textos da
   janela são os mesmos de antes da série (lista de menus "Arquivo/Navegar/Cluster/Plots/Ferramentas/Ajuda" e os rótulos
   da barra lateral, conferidos no probe).
5. `scripts/screenshot.py --language en|pt_BR` (padrão `pt_BR`): instala o idioma antes dos imports de `main()` e põe o
   idioma no nome do arquivo quando não é `pt_BR` (`main_dark_en.png`).

### R6: Glossário, fluxo e documentação

1. `src/qe_studio/locale/README.md`: o fluxo (`update` → traduzir → `compile`; `check --area N`), as regras de estilo
   (inglês dos EUA; menus e botões com inicial maiúscula só na primeira palavra, como a maioria das 560 já feitas ("Open data folder"; "Generate Plot" é a exceção a decidir);
   nomes de programas e arquivos do QE intactos: `pw.x`, `projwfc.x`, `scf.out`) e o **glossário** Português → English
   com os termos fixos da interface, semeado a partir das 560 traduções (`Abrir` → `Open`, `Aba` → `Tab`,
   `Aviso` → `Warning`, `Abrir local de origem` → `Show in file manager`) e fechado nos termos que as specs
   seguintes vão repetir: Pasta, Arquivo, Árvore, Grade, Grids, Projeto, Raiz, Cálculo, Criar cálculo, Entrada/Saída,
   Gerar, Plotar, Sincronizar, Enviar, Baixar, Selo. A decisão de cada termo está em "Decisões assumidas".
2. `CLAUDE.md`: a regra de idioma passa a ser: "User-facing strings are written in **Portuguese inside `_()`** (or `N_()` for a
   Portuguese token that is also data); English lives in `locale/en/LC_MESSAGES/lain.po` (workflow in
   `locale/README.md`). Code, comments and commits are English." e o fluxo de teste (`test_i18n.py`) em uma linha.
   Sem descrever a série (ela vive nas specs).
3. `pyproject.toml`: conferir que a roda inclui `locale/en/LC_MESSAGES/lain.mo` (`uv build --wheel` e listar o zip; hoje
   a roda inclui o `.po`).

## Fora de escopo

- Traduzir qualquer área: 53–59. Remover o portão e a documentação para o usuário (`README.md`): 60.
- Trocar o idioma sem reiniciar (decisão da `spec_end`).
- Mensagens de erro das tentativas: não foram preservadas; se o usuário as tiver, entram como defeito novo nesta
  spec (R0.1).
- Traduzir o que é gravado em arquivo de cálculo (`.qsub`, comentários dos inputs): 56 e 57 decidem.

## Decisões assumidas (confirmar na revisão)

1. **`.mo` parcial commitado desde já** (R1.3): quem usa `en` vê português e inglês misturados até a 60. A alternativa
   (só gerar o `.mo` na 60) deixa `uv run lain` em português até lá e tira o detector (R5) de cena; o idioma padrão
   (`auto` num sistema pt) não muda nada para o usuário.
2. **Portão por spec, não por arquivo solto** (R2): a granularidade é a área de cada spec; uma mensagem compartilhada
   entre duas áreas é exigida quando a **primeira** delas fecha.
3. **A sondagem em subprocesso** substitui o fixture em processo da `spec_end` R4.2 (R3 de "Situação atual"); a
   alternativa, recarregar `qe_studio.*` na mesma sessão, quebra a identidade das classes PyQt e foi descartada sem teste.
4. **Glossário proposto** (confirmar): Pasta → Folder, Arquivo → File, Árvore → Tree, Grade → Grid, Grids → Grids,
   Projeto → Project, Raiz → Root, Cálculo → Calculation, Criar cálculo → New calculation, Entrada/Saída → Input/Output,
   Gerar → Generate, Plotar → Plot, Sincronizar → Sync, Enviar → Push, Baixar → Pull, Selo → Badge. "Valência/Condução"
   → Valence/Conduction.
5. As mensagens traduzidas até aqui (560) **não foram revisadas**: cada spec de área revisa as da sua.

## Notas de implementação

- Novos: `tests/test_i18n.py`, `tests/i18n_areas.py`, `tests/i18n_probe.py`, `tests/i18n_helpers.py`,
  `src/qe_studio/locale/README.md`, `src/qe_studio/locale/en/LC_MESSAGES/lain.mo`.
- Alterados: `scripts/i18n.py` (164 linhas: `compile` parcial, `check --area`, paridade em `problems()`),
  `scripts/screenshot.py` (236: `open_window`, `--language`), `ui/palette_controller.py:221`, `CLAUDE.md`,
  `tests/i18n_static.py` (`PORTUGUESE_WORDS`), `ui/widgets/explorer.py:39` (`ERROR_BADGE`).
- Limites: nenhum arquivo perto de 500 linhas; `ui/main_window.py` (449/450) não é tocado.
- Documentação ao implementar: `CLAUDE.md` (regra de idioma). `README.md` e `config.example.yaml`: spec 60.

## Critérios de aceite e testes

- [ ] A suíte `-m "not realdata and not perf"` de hoje passa sem alterar goldens (`test_figure_regression.py`).
- [ ] `scripts/i18n.py compile` escreve `lain.mo` com as 560; `test_mo_follows_po` e `test_po_follows_the_code` passam.
- [ ] `scripts/i18n.py check` mostra a tabela por área e `check --area 53` lista as 181 pendentes da 53.
- [ ] `test_untranslated_only_in_pending_areas` passa com `DONE` vazio e **falha** com `DONE = {53}` (teste sobre
      catálogo sintético: uma mensagem pendente com local em `ui/app.py`).
- [ ] Paridade de marcadores: os seis casos sintéticos de R3.3 e o catálogo real.
- [ ] `test_static_finds_unaccented_portuguese`: `ERROR_BADGE = "ERRO"` é achado; `N_("ERRO")` não; zero achados na árvore.
- [ ] `test_no_local_underscore` falha com o código antigo de `palette_controller.py:221` (teste com a fonte antiga em
      string) e passa com o novo; `test_dynamic_translations_are_declared` lista as seis chamadas.
- [ ] `test_no_leaks_in_english[main|plot]` e `test_portuguese_unchanged[main]` verdes; um `_()` removido de um texto
      traduzido da janela (verificação manual, não commitada) faz o primeiro falhar.
- [ ] `scripts/screenshot.py --language en --plot` gera `main_dark_en.png` com "File", "Tools", "Help".
- [ ] `uv build --wheel`: o zip traz `qe_studio/locale/en/LC_MESSAGES/lain.mo`.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
