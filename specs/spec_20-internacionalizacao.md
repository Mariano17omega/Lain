# Spec 20: Internacionalização (português e inglês)

| | |
|---|---|
| **Prioridade** | 20 (por último: as specs anteriores ainda criam textos) |
| **Status** | Rascunho para revisão |
| **Depende de** | todas as anteriores (os textos precisam estar estáveis) |
| **Usada por** | nenhuma |
| **Esforço** | G |

## Itens de origem

> `report.md` §5, decisão 4: **Idioma**: preparar `tr()` para inglês e português.

Decisão do usuário (30/09/2026): criar uma spec própria. O português continua sendo o idioma padrão.

## Situação atual

- O CLAUDE.md define que todo texto visível ao usuário é em **português** (rótulos, diálogos,
  mensagens de erro e até valores de enum como `Method.CONTENT = "conteúdo"`,
  `core/calculations/base.py:38-42`). Código, comentários e commits são em inglês.
- Nenhuma infraestrutura de tradução: não há `tr(`, `QTranslator` nem `gettext` em `src/`.
- Textos visíveis estão espalhados em `ui/` **e** em `core/`, que não usa Qt (exceto o sync):
  - `core/calculations/*.py`: rótulos e seções do `ParamField`, `display_name`, rótulos dos papéis
    (`FileRole`), avisos, `LoadError`, resumos (`RenderInfo.summary`);
  - `core/qe/*.py`: avisos (ex.: `pw_output.py:62-66`), mensagens de `BandsFormatError` e
    `PdosFormatError`;
  - `core/config.py`: mensagens de validação e avisos;
  - `core/sync/*.py`: etapas e relatórios (`controller.py:70-91`), ações do plano
    (`planner.py:22-25`, `Action.NEW = "novo"`).
- Textos de enums são usados como dados em alguns lugares (ex.: `Method` aparece no mapeamento e
  em testes). Trocar o valor exige cuidado.
- Os `<kind>.plot` guardam valores de `choice` como identificadores (`"both"`, `"log"`, `"fermi"`), e
  não os rótulos. Eles não dependem do idioma.

## Requisitos

### R1: Infraestrutura (gettext)
1. `src/qe_studio/i18n.py`, sem Qt, importável por `core/` e por `ui/`:
   - `_(msg) -> str`, `ngettext(singular, plural, n) -> str`, `pgettext(contexto, msg) -> str`;
   - `N_(msg) -> msg` (marca sem traduzir, para constantes de módulo como `REFERENCES`, `GROUPINGS`,
     `SECTIONS`, que são traduzidas no uso);
   - `install(language)`: carrega o catálogo `.mo` com `gettext.translation("lain", localedir,
     languages=[…], fallback=True)`;
   - `current_language()`.
2. Idioma-fonte = **português** (as strings no código continuam em português, então nada muda para quem
   usa pt). Catálogo `en` em `src/qe_studio/locale/en/LC_MESSAGES/lain.po`, compilado para `.mo` no
   build. O `pt_BR` é o próprio texto-fonte (catálogo vazio).
3. Textos do próprio Qt (botões padrão "OK", "Cancel", diálogos de arquivo): `QTranslator` carregando o
   `qtbase_<lang>` de `QLibraryInfo.path(TranslationsPath)` em `ui/app.py`, para o Qt seguir o mesmo
   idioma.
4. Ferramentas no grupo dev: `babel` (`pybabel extract/update/compile`). Script
   `scripts/i18n.py extract|update|compile`. Os arquivos `.mo` compilados são versionados, para que
   `uv run lain` funcione sem um passo extra.

### R2: Escolha do idioma
1. `ui.language: Literal["auto", "pt_BR", "en"] = "auto"` em `core/config.py` e em
   `config.example.yaml`.
2. `auto`: `QLocale.system().name()`. `pt*` → `pt_BR`, qualquer outro → `en`.
3. O idioma é aplicado na inicialização, antes de criar qualquer widget (`ui/app.py`, logo depois de
   ler o config). Trocar o idioma exige reiniciar, e "Recarregar config.yaml" avisa: "O idioma muda ao
   reiniciar o Lain.".
4. Variável `LAIN_LANGUAGE` (ou `QE_STUDIO_LANGUAGE`, seguindo os nomes internos) tem precedência, útil
   para testes e capturas de tela.

### R3: Marcação dos textos
1. **Todo** texto visível passa por `_()`/`ngettext()`/`pgettext()`:
   - `ui/`: rótulos, tooltips, menus, diálogos, mensagens do rodapé e placeholders;
   - `core/`: `display_name` (as siglas dos badges, BANDS/PDOS/RELAX/SCF/CALC, não mudam), rótulos de
     papéis, `ParamField.label`/`section`/rótulos de `choices`/`tooltip`, avisos, `LoadError`, resumos,
     mensagens de config e do sync.
2. Plurais com `ngettext` (ex.: "N arquivo(s) baixado(s)" vira singular/plural de verdade nos dois
   idiomas).
3. Seções do painel: as **chaves** passam a ser identificadores estáveis (`"energy"`, `"x_axis"`,
   `"style"`…), e o título exibido vem de `_()`. Isso evita que `.plot`, QSettings
   (`params/sections/<kind>/<título>`, spec 8) e o código dependam do idioma.
4. Enums com valor em português (`Method`, `Action`, `SyncStatus`, se aplicável):
   - o **valor** continua o mesmo (dados persistidos e testes não mudam);
   - um `label` traduzido é exibido (`Method.CONTENT.label` → "conteúdo"/"content");
   - a UI nunca mostra `.value`.
5. Textos dentro de figuras (rótulos de eixos como "PDOS (estados/eV)", "Passo BFGS", legendas
   "Valência"/"Condução") também são traduzidos. As exportações seguem o idioma da interface no momento
   da exportação.
6. Números continuam com ponto decimal nos dois idiomas (convenção científica e do QE). Só os textos
   mudam.

### R4: Garantia de cobertura
1. Teste `tests/test_i18n.py`:
   - extrai as mensagens (`pybabel extract` via API) e falha se o `en/lain.po` tiver mensagem sem
     tradução ou *fuzzy*;
   - verificação estática: um script AST percorre `src/qe_studio` e falha em literais com letras
     acentuadas do português (`[áâãàéêíóôõúç]`), ou em literais passados a `setText`, `setToolTip`,
     `QMessageBox.*`, `addAction`, `QLabel(…)`, `ParamField(…)` e `LoadError(…)`, quando não estão
     dentro de `_()`/`N_()`. Uma lista de exceções explícita no próprio teste cobre logs (os logs ficam
     em inglês) e identificadores.
2. Teste de fumaça: com `LAIN_LANGUAGE=en`, o `main_window` fixture monta a janela, e os menus
   principais estão em inglês ("File", "Cluster", "Plots", "Tools", "Help"). Com `pt_BR`, como hoje.
3. `scripts/screenshot.py` ganha `--language en|pt_BR` para gerar capturas nos dois idiomas.

### R5: Documentação
1. CLAUDE.md: a regra "User-facing strings are Portuguese" passa a ser "User-facing strings are written
   in Portuguese **inside `_()`**; English translations live in `locale/en/LC_MESSAGES/lain.po`".
   Inclui o fluxo `scripts/i18n.py update` → traduzir → `compile`.
2. README: seção "Idioma" (`ui.language`).

## Fora de escopo
- Outros idiomas além de português e inglês (a infraestrutura permite, mas não haverá catálogo).
- Traduzir as specs, o PRD e os comentários.
- Trocar o idioma sem reiniciar.
- Localizar formatos numéricos (vírgula decimal).

## Decisões assumidas (confirmar na revisão)
1. **gettext em vez do `tr()` do Qt.** O relatório fala em "`tr()`", mas boa parte dos textos visíveis está
   em `core/` (`ParamField`, avisos, `LoadError`, sync), que não pode depender do Qt (CLAUDE.md). O
   gettext atende `core/` e `ui/` com uma única função `_()`, e o `QTranslator` cobre só os textos
   internos do Qt (R1.3). "Preparar `tr()`" foi lido como "preparar as funções de tradução".
2. O idioma-fonte continua o português (R1.2), para não reescrever todas as strings nem os testes que
   comparam textos em português.
3. Os logs ficam em inglês e não são traduzidos (R4.1).
4. As exportações de figura usam o idioma atual da interface (R3.5).
5. As seções do painel ganham identificadores estáveis (R3.3). As chaves de QSettings da spec 8
   (`params/sections/...`) migram para os identificadores.

## Notas de implementação
- Fazer em duas etapas dentro da spec:
  1. infraestrutura + `core/` (testável sem Qt);
  2. `ui/` arquivo por arquivo, com o teste estático do R4.1 ligado no fim, quando a suíte estiver verde.
- Os testes existentes que comparam textos em português continuam valendo (idioma padrão `pt_BR` no
  `conftest.py`: `LAIN_LANGUAGE=pt_BR`).
- Novos: `src/qe_studio/i18n.py`, `src/qe_studio/locale/en/LC_MESSAGES/lain.{po,mo}`,
  `scripts/i18n.py`, `tests/test_i18n.py`.
- Alterados: praticamente todos os módulos com texto visível. `pyproject.toml` (dev: `babel`; incluir
  `locale/` no pacote).

## Critérios de aceite e testes
- [ ] Com `ui.language: en`, menus, painel de ajustes, diálogos, rótulos de papéis, avisos e eixos das
      figuras aparecem em inglês. Com `pt_BR` (e `auto` num sistema pt), tudo igual a hoje.
- [ ] `tests/test_i18n.py`: catálogo `en` completo e sem *fuzzy*. O verificador estático não acha
      literal visível fora de `_()`.
- [ ] `ngettext`: "1 arquivo baixado" e "2 arquivos baixados" (pt); "1 file downloaded" e "2 files
      downloaded" (en).
- [ ] `Method.CONTENT.value == "conteúdo"` (dado inalterado), e a UI mostra `Method.CONTENT.label`.
- [ ] Um `.plot` salvo em pt carrega igual com a interface em en (valores de `choice` são
      identificadores).
- [ ] Os botões padrão do `QMessageBox` aparecem em inglês com `en` (o `QTranslator` qtbase foi
      carregado; o teste pula se a tradução do Qt não estiver instalada no sistema).
