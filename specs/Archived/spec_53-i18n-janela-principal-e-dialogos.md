# Spec 53: Inglês da janela principal, dos menus e dos diálogos gerais

| | |
|---|---|
| **Prioridade** | 53: a primeira área traduzida, a que o usuário vê assim que abre o Lain (menus, barras, árvore, grade, menu de contexto, ajuda, projetos, sobre). Fixa o jeito de traduzir (glossário, plurais, cenários do detector) que 54–59 repetem. |
| **Status** | Implementada (18/10/2026). Ajustes ao texto: **(a)** nenhum código de `src/` mudou: R1.4 (`workspace.py:283`, o comentário já existia) e R2 (os valores do filtro já eram `N_` e a UI já os mostrava por `_()`) só precisavam do catálogo. **(b)** São 181 mensagens traduzidas e **uma** corrigida na revisão das 135 que já existiam: `Defina paths.xcrysden_path…` dizia `XCrySDen` no inglês e o msgid usa `XCrysDen` (a grafia do usuário, `context_menu.py:46`); R1.5 pede o nome igual nos dois idiomas. `Ir para os ajustes` ficou `Go to the plot settings`, `Sair` ficou `Quit`. O `.mo` tem 742 traduzidas e 773 em português. **(c)** O detector ganhou um canal de **fatos**: um cenário que devolve uma lista a põe no JSON como `<cenário>#facts`, e o probe fecha os diálogos que cada cenário abriu. Além dos 11 cenários de R2, cinco só de fatos: `menus` (a ordem dos menus), `cli` (`--help`), `config` (`config.yaml` inválido), `restart` (o aviso do idioma) e `type_filter` (o que a grade lista com “saídas” marcado). `first_run` roda por último: o painel de boas-vindas fica ligado. **(d)** O selo `ERRO` (R3.4) é provado trocando `explorer.paint_badge` por um gravador no cenário `tree` (o texto que o delegate pinta, sem ler pixel e sem método novo no delegate). **(e)** `Data` (o “Date” da grade) é também o inglês de `Dados` (linha do Sobre): o detector o confundia com vazamento, e `tests/i18n_helpers.py` ganhou `HOMOGRAPHS` com o motivo. **(f)** O que ainda aparece em português nos cenários é só das áreas 54–59 (conferido). Medido: 4029 passed, 2 skipped na suíte da CI; `tests/i18n_probe.py` 363 linhas e `tests/test_i18n.py` 360 (sem dividir por área). |
| **Depende de** | spec 52 (`AREAS`/`DONE`, `check --area`, `.mo` parcial, `i18n_probe.py`, glossário) |
| **Usada por** | 60 |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a 52 abriu; o único arquivo apertado, `ui/main_window.py`, só perde linhas. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. Quero que crie uma série specs para concluir o processo de internacionalização […]

Área 53 da tabela de `AREAS` (spec 52 R2): `ui/*.py`, `ui/dialogs/*.py`, `ui/theme/`, os widgets de navegação
(`explorer`, `breadcrumb`, `bars`, `workspace`, `context_menu`, `toast`, `command_palette`, `nav_sections`,
`project_combo`, `file_card`, `filter_bar`, `file_grid`, `search_bar`), `core/*.py` e `i18n.py`.

## Situação atual

Contagem da 52 (`check --area 53`, medida em 18/10/2026): **315 mensagens na área, 181 sem tradução**, 134 traduzidas e
não revisadas. A marcação em `_()` já está feita (`i18n_static` sem achados); falta o inglês, e há quatro pontos que
não são só tradução:

- **R1 (menus e ações).** `ui/actions.py:28-33` define os seis títulos de menu por `_()` (`MENU_FILE = _("Arquivo")`,
  `MENU_NAVIGATE = _("Navegar")`, `MENU_PLOTS = _("Gráficos")`…) e `ACTIONS` (`:37` em diante) os textos. Dos 30 textos
  do arquivo, 12 estão sem tradução. Na janela de `en` da 52 só "File", "Cluster"(igual), "Plots", "Tools" e "Help"
  estão em inglês; "Navegar" não.
- **R2 (valores que são dados).** `core/filtering.py:17-21` guarda os valores do filtro em português como **dados**
  (`NO_BADGE = N_("sem tipo")`, `STATES`, `NO_STATE`, `VISUALS = (N_("inputs"), N_("saídas"), …)`) e a UI os mostra
  por `_(value)` (`ui/widgets/filter_bar.py:93`, `:167`, as duas chamadas dinâmicas da 52 R4.3). Os 7 estão sem
  tradução. Se o texto exibido mudar e o valor não, o filtro continua comparando o dado; nenhum teste prova isso em `en`.
- **R3 (atalho colado ao texto).** `ui/widgets/workspace.py:283` monta `_("Fechar") + "\tCtrl+W"`: a tecla fica fora da
  tradução (correto), mas é a única concatenação do tipo na área.
- **R4 (limites).** `ui/main_window.py` tem 449 de 450 linhas (`test_architecture.py`): qualquer linha a mais, por menor
  que seja, reprova a CI.
- **R5 (diálogo de atalhos).** `ui/dialogs/shortcuts.py` mostra os `shortcut_help()` de widgets de **várias** áreas
  (`ui/help_controller.py:53-55`: `explorer`, `files` e `TextViewer.shortcut_help`; o último é da 54). Enquanto a 54
  não fechar, esse diálogo é parcialmente inglês.

## Requisitos

### R1: Traduzir a área

1. Traduzir as 181 mensagens de `scripts/i18n.py check --area 53` e **revisar** as 134 já traduzidas contra o glossário
   da 52 (`locale/README.md`): termo fixo igual em todo lugar, `&` e `{campos}` preservados. Menus: "Arquivo" → "File",
   "Navegar" → "Navigate", "Cluster", "Gráficos" → "Plots", "Ferramentas" → "Tools", "Ajuda" → "Help".
2. Plurais por `ngettext` com as duas formas em inglês (`1 file`, `2 files`); conferir os `ngettext` da área
   (`grep -rn ngettext` nos arquivos da área) e que cada um tem `msgstr[0]` e `msgstr[1]`.
3. Os valores de R2 ficam em português como dados e ganham tradução do **texto exibido**: `sem tipo` → `no type`,
   `sem estado` → `no state`, `inputs` → `inputs`, `saídas` → `outputs`, `dados` → `data`, `imagens` → `images`,
   `outros` → `other`; `OK`, `INCOMPLETO`, `AVISO`, `SEM ERROS`, `ERRO` → `OK`, `INCOMPLETE`, `WARNING`, `NO ERRORS`,
   `ERROR`. A etiqueta "ERRO" da árvore (`ui/widgets/explorer.py:39`, `ERROR_BADGE`) é um literal à parte, marcado pela spec 52 R4.4:
   a sua tradução é `ERROR` e o teste de R3.4 a cobre pelo modelo da árvore, não pelo texto de widget (a etiqueta é pintada).
4. `ui/widgets/workspace.py:283`: manter `_("Fechar") + "\tCtrl+W"` (a tecla é só exibida) e dizer isso no comentário
   que já existe; sem mudança de comportamento. Se a tradução do atalho for necessária, vira `_("Fechar\tCtrl+W")`.
5. Termos de produto e de arquivos intactos nos dois idiomas: `config.yaml`, `Rsync`, `XCrySDen`, `.lain`.

### R2: Cenários do detector (spec 52 R5) para a área

1. Acrescentar a `SCENARIOS` de `tests/i18n_probe.py`: `shortcuts` (Ajuda → Atalhos), `about`, `palette` (paleta de
   comandos aberta), `context_menu` (o menu de contexto de um arquivo e o de uma pasta: o `QMenu` construído, sem
   `exec`), `open_with`, `rename`, `new_project`, `overwrite`, `first_run` (diálogo da primeira execução, sem
   `config.yaml`), `toast` (uma mensagem de erro e uma de aviso) e `tree` (cabeçalhos e botões da árvore, `tree_show_files`
   ligado).
2. Cada diálogo é aberto **sem `exec()`** (construído e mostrado; o probe o fecha), e o texto de cada um entra no JSON.
3. **Testes** (`tests/test_i18n.py`): `test_no_leaks_in_english[<cenário>]` para os 11 cenários novos; `test_en_menus`: os
   menus principais são `["File", "Navigate", "Cluster", "Plots", "Tools", "Help"]` com `en` e os de hoje com `pt_BR`.

### R3: Textos que não passam pela janela

1. `ui/app.py`: `parse_args(["--help"])` em `en` mostra os dois `help=` em inglês (`path to config.yaml`, `detailed
   log`) e em `pt_BR` os de hoje; o probe captura o `SystemExit` e a saída.
2. `core/config.py` (15 das 18 mensagens sem tradução): as mensagens de validação e os avisos do `config.yaml` saem em
   inglês com `en`; as do pydantic **ficam como o pydantic as escreve** (biblioteca, inglês). Teste: `load_config` com
   um `config.yaml` inválido em um subprocesso `en` devolve `ConfigError` com a mensagem nossa em inglês.
3. `Recarregar config.yaml` com `ui.language` diferente do idioma em uso mostra o aviso "O idioma muda ao reiniciar o
   Lain." / `The language changes when Lain restarts.` (já existe em `ui/language.py:restart_notice`; só falta o catálogo).
4. **Teste da etiqueta pintada:** em subprocesso `en`, o texto que o delegate da árvore desenha para uma pasta com `CRASH` é
   `ERROR` (o probe pergunta ao modelo/delegate o texto do selo, sem ler pixel).
5. **Teste do filtro:** em subprocesso `en`, o filtro por tipo "outputs" mostra os mesmos itens que o "saídas" de
   `pt_BR` sobre o mesmo `demo_project` (o dado comparado não muda com o idioma).

### R4: Fechar a área

1. `uv run python scripts/i18n.py update` (sem novas mensagens), `compile`, e `DONE |= {53}` em `tests/i18n_areas.py`.
2. `test_untranslated_only_in_pending_areas` passa com `DONE = {53}`.
3. Capturas de tela (`scripts/screenshot.py --language en`, `--nav`, `--plot`) conferidas à mão e **não** versionadas.

## Fora de escopo

- Traduzir os rótulos dos gráficos, a Criar cálculo, o sync e a visualização 3D: 55, 56–57, 58 e 59.
- Os textos dos visualizadores de texto, de input e do Resumo (inclusive suas dicas): 54.
- Mudar de lugar texto ou botão (o inglês segue o layout de hoje; um rótulo em inglês mais largo que o português que
  corte na barra é um defeito a registrar e a corrigir aqui só se a captura em `en` o mostrar).
- Outros idiomas.

## Decisões assumidas (confirmar na revisão)

1. O texto **exibido** das etiquetas de estado (`ERRO` → `ERROR`) é traduzido; o valor guardado continua o mesmo.
2. O filtro de R3.5 é provado em subprocesso porque o idioma não troca no processo (52 R3).
3. Um rótulo que ficou mais largo em inglês e foi cortado na captura é corrigido com o ajuste de largura mínima já usado
   na barra (`font scale`), não com texto mais curto.

## Notas de implementação

- Novos: nenhum arquivo de código; cenários em `tests/i18n_probe.py`, casos em `tests/test_i18n.py`.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `lain.mo`; `tests/i18n_areas.py` (`DONE`); `ui/widgets/workspace.py` só
  se R1.4 pedir. `ui/main_window.py` **não** cresce (449/450).
- Limites: `tests/test_i18n.py` e `tests/i18n_probe.py` nascem na 52; se algum passar de 500 linhas com os cenários,
  dividir por área em `tests/i18n_scenarios_<area>.py`.
- Documentação ao implementar: nenhuma (o `README.md` é da 60).

## Critérios de aceite e testes

- [ ] Goldens e a suíte de hoje passam sem regenerar (`test_figure_regression.py`).
- [ ] `check --area 53` vazio; `test_untranslated_only_in_pending_areas` passa com `DONE = {53}`.
- [ ] `test_en_menus` verde: os seis menus em `en` e em `pt_BR`.
- [ ] `test_no_leaks_in_english` para os 13 cenários (2 da 52 + 11 desta); `test_portuguese_unchanged` verde.
- [ ] Filtro por tipo igual nos dois idiomas (R3.5); `--help` e `config.yaml` inválido em `en` (R3.1, R3.2).
- [ ] Plurais da área com as duas formas (teste de R3 da 52 sobre o catálogo real).
- [ ] Passo manual de aceite: abrir o Lain com `QE_STUDIO_LANGUAGE=en` num projeto real e passar pelos menus, árvore,
      grade, menu de contexto e Ajuda; nenhum texto da área em português.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
