# Spec 19: Tema "Sistema", escala de fonte e acessibilidade

| | |
|---|---|
| **Prioridade** | 19 |
| **Status** | Implementada. Desvios: o Tab não usa `setTabOrder` uma vez só, e sim `MainWindow.focusNextPrevChild`, que refaz a ordem antes de cada Tab (`ui/focus_controller.py`), porque o Qt põe no fim da cadeia todo widget criado depois (cada migalha do caminho, aba, chip) e `setTabOrder` ignora widgets sem foco e move um por vez; Ctrl+1..4 são ações do menu "Navegar" (`focus.tree/grid/workspace/params`); o ícone do botão Tema mostra o **modo atual** (antes mostrava o do destino) e `ThemeManager.toggle()` cicla os 3 modos, `set_theme` virou `set_mode`; além de `text_dim`, falhavam em AA e foram ajustados `success` e `warning` do tema claro (para os valores de `hl_success`/`hl_warning`), `hl_error`, `syn_comment`, `syn_card_option` e `gutter_fg` (claro), `syn_comment`, `gutter_fg` e o alfa de `search_current_bg` (escuro, 0,65 → 0,50, para o texto passar sobre o realce); `text_meta` (`#8a9aa1` escuro, `#5b6b80` claro) passa também sobre `card_hover` e `accent_soft`, onde a grade o pinta; a escala também multiplica as alturas e larguras que contêm texto (tokens QSS `row_h`, `bar_h`, `status_h`, `activity_w` e `ui/theme/scale.py:scaled`), o card da grade deriva do `QFontMetrics` e o delegate foi para `ui/widgets/file_card.py` (limite de 500 linhas); a largura dos painéis e dos diálogos não escala (a 1,6 os rótulos do painel de ajustes ficam cortados até arrastar o divisor); o anel de foco dos botões é a borda que eles já reservavam, recolorida em `controls/focus.qss`, e as views (árvore, grade) o desenham no delegate, sem moldura própria (uma borda de foco deslocaria o conteúdo); `contrast_ratio` e `composite` moram em `core/colors.py`; `scripts/screenshot.py` ganhou `--scale` |
| **Depende de** | nenhuma (convém depois das specs 10–18, que criam tokens novos) |
| **Usada por** | nenhuma |
| **Esforço** | M |

## Itens de origem (`report.md` §3, "Tema e acessibilidade")

> - Tema **"Sistema"** (`QStyleHints.colorScheme`, PyQt6 ≥ 6.7 já cobre) além de escuro/claro; `ui.font_scale` no config.
> - Checar contraste de `text_dim` sobre `card` (10 px mono nos metadados da grade) com `contrast_ratio` que já existe em `plotting/style.py`; ordem de Tab e foco visível.

## Situação atual

- **Temas** (`ui/theme/manager.py`):
  - `THEMES = ("dark", "light")` (l.22);
  - `set_theme`/`toggle` (l.130-142) recarregam os tokens, aplicam o QSS e emitem `theme_changed`;
  - o config aceita só `ui.theme: Literal["dark", "light"]` (`core/config.py:171`);
  - na inicialização, `ui/app.py:79-80` usa o QSettings `ui/theme` e, sem ele, o config. O toggle grava
    no QSettings (`main_window.py:571-574`).
  - Não há opção "Sistema" nem uso de `QStyleHints.colorScheme`. O ambiente atual tem PyQt6/Qt 6.11,
    que tem `colorScheme()` e o sinal `colorSchemeChanged`.
- **Tamanhos de fonte:**
  - fixos em px no QSS (`base/app.qss:4` usa `font-size: 12px`; os demais arquivos usam de 9 a 14 px) e
    em `ui/painting.py:13-25` (`setPixelSize`), com cerca de 25 ocorrências;
  - não há escala.
- **Contraste** (WCAG 2, calculado com `core/plotting/style.py:contrast_ratio`):
  | Tema | Par | Razão | AA texto normal (4,5) |
  |---|---|---|---|
  | escuro | `text_muted` / `card` | 5,39 | ok |
  | escuro | `text_dim` / `card` | **3,09** | falha |
  | escuro | `text_dim` / `window` | **3,50** | falha |
  | claro | `text_muted` / `card` | 4,76 | ok |
  | claro | `text_dim` / `card` | **2,56** | falha |
  | claro | `text_dim` / `window` | **2,45** | falha |

  O `text_dim` é usado em texto, não só em elementos desabilitados:
  - metadados da grade e da árvore: `file_grid.py:101,161-166`, `explorer.py:87`;
  - `file_grid.qss:12`, `panels.qss:20`, `tabs.qss:40`, `app.qss:50`;
  - *placeholder* (`manager.py:161`).
- **Foco:** só os campos de entrada têm anel de foco (`controls/inputs.qss:14`). Botões, árvore, grade,
  abas e a barra de atividades não mostram foco visível. A ordem de Tab nunca foi definida
  (`setTabOrder` não aparece no código).

## Requisitos

### R1: Tema "Sistema"
1. `ui.theme: Literal["dark", "light", "system"]`, com padrão `dark` (mantém o comportamento atual).
   `THEMES` continua listando só os temas concretos. `"system"` é um **modo**.
2. `ThemeManager` ganha `mode` (`dark`/`light`/`system`) além de `name` (o tema concreto aplicado). Em
   `system`:
   - `name = "dark"` se `QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark`, `"light"`
     se `Light`, e `"dark"` se `Unknown`;
   - conecta `styleHints().colorSchemeChanged` a um **método ligado** (regra do CLAUDE.md), que reaplica o
     tema quando o sistema muda;
   - `theme_changed` continua emitindo o **tema concreto**, então os widgets pintados à mão não mudam.
3. O botão "Tema" da barra de atividades alterna entre os 3 modos: Escuro → Claro → Sistema → Escuro.
   Ícones: `dark_mode`, `light_mode` e `contrast` (ou `brightness_auto`). Tooltip: "Tema: Sistema
   (escuro agora)". O Ctrl+T faz o mesmo.
4. QSettings `ui/theme` guarda o **modo**. Valores antigos (`dark`/`light`) continuam válidos.
5. A figura não muda: o fundo do gráfico segue `plot.background` (spec 2), e não o tema.

### R2: Escala de fonte
1. `ui.font_scale: float = 1.0`, de 0,8 a 1,6 (validado no pydantic), documentado em
   `config.example.yaml`.
2. `build_stylesheet` aplica a escala a todo `font-size: Npx` do QSS montado (regex sobre o texto final,
   arredondando para inteiro, mínimo 8 px). Paddings e tamanhos de controles **não** mudam, só as
   fontes.
3. `ui/painting.py`: `mono_font`/`ui_font` multiplicam o `pixel_size` pela escala (lida do
   `ThemeManager`). Os delegates que calculam alturas de linha a partir da fonte (grade, árvore) usam
   `QFontMetrics` e não constantes. Corrigir onde houver altura fixa que corte o texto em 1,6.
4. A escala vale na inicialização. Mudar o config e usar "Recarregar config.yaml" reaplica o QSS.

### R3: Contraste mínimo dos tokens
1. Novo teste `tests/test_theme_contrast.py`, para os **dois** temas:
   - texto de leitura (`text`, `text_secondary`, `text_muted`) ≥ 4,5 sobre `window`, `panel`, `card`,
     `panel_alt`, `popover` e `input`;
   - `text_dim`, quando usado em texto informativo (metadados da grade e da árvore, contagens, "pasta
     acima"), ≥ 4,5 sobre `card` e `panel`;
   - texto de estado (`success`, `warning`, `error`, `accent_text`) ≥ 4,5 sobre `card` e `panel`;
   - anel de foco (`focus_ring`, R4) ≥ 3,0 sobre os mesmos fundos (WCAG 1.4.11, componentes).

   O teste usa `contrast_ratio`, movido de `core/plotting/style.py` para `core/colors.py` e reexportado
   no local antigo. Cores `rgba(...)` são compostas sobre o fundo antes de medir.
2. Correção: separar os usos.
   - `text_dim` continua só para elementos **desabilitados** e *placeholder*, onde o WCAG não exige
     contraste.
   - Os metadados da grade e da árvore passam a usar um token novo, `text_meta`, nos dois temas, com
     valor que passe em 4,5 (ex.: perto do `text_muted` atual, ajustado ao design system).
3. Tokens de realce criados pelas specs 10 e 11 (`hl_*`, `syn_*`, `diff_*`, `search_*`) entram no mesmo
   teste: texto ≥ 4,5 sobre `workspace`.

### R4: Foco visível e ordem de Tab
1. Token `focus_ring` nos dois temas (padrão: `accent`) e regras `:focus` no QSS para `QPushButton`,
   `QToolButton`, a barra de atividades (`ActivityButton`), `QTreeView`, `QListView`, `QTabBar::tab`,
   os chips (specs 11 e 16) e os campos que ainda não têm. Contorno de 1-2 px ou borda, sem mudar o
   layout (usar `outline`/borda já reservada).
2. Os delegates pintados à mão (cards da grade, linhas da árvore) desenham o anel de foco no item
   atual quando a view tem foco (`State_HasFocus`).
3. Ordem de Tab definida com `setTabOrder` no `MainWindow` (ou no `LayoutController`, spec 15):
   barra de atividades → TopBar (Gerar Gráfico, Plotar SCF, alternâncias) → árvore → grade → workspace
   (abas → conteúdo) → painel de ajustes → rodapé. Painéis ocultos saem da cadeia.
4. Atalhos para focar áreas: Ctrl+1 árvore, Ctrl+2 grade, Ctrl+3 workspace e Ctrl+4 painel de ajustes.
   Aparecem no diálogo de atalhos (spec 18).
5. Nomes acessíveis (`setAccessibleName`) nos botões só de ícone (barra do gráfico, barra de atividades,
   botões de painel). O texto é o mesmo do tooltip.

## Fora de escopo
- Temas extras (alto contraste, daltônico).
- Paleta das figuras e daltonismo (parte do F7, adiado).
- Leitor de tela completo (rótulos para os gráficos matplotlib).
- Escala de fonte por painel.

## Decisões assumidas (confirmar na revisão)
1. O padrão continua `dark` (R1.1). `system` é opcional.
2. O botão Tema cicla entre os 3 modos (R1.3), em vez de ganhar um menu.
3. A escala de fonte afeta só as fontes (R2.2), e não espaçamentos.
4. Os novos valores de `text_meta` são escolhidos para passar em 4,5, mantendo o tom do design system.
   O design final pode ser revisado no `Documentation/design system (UX)/`.
5. Ctrl+1..4 focam as áreas (R4.4).

## Notas de implementação
- Alterados:
  - `ui/theme/manager.py`, `ui/app.py`, `ui/main_window.py`;
  - `ui/widgets/bars.py` (botão Tema), `ui/painting.py`;
  - `ui/widgets/file_grid.py`, `ui/widgets/explorer.py` (`text_meta`, anel de foco);
  - `ui/resources/themes/{dark,light}.yaml` (`text_meta`, `focus_ring`);
  - `ui/resources/styles/**/*.qss`;
  - `core/config.py`, `config.example.yaml`, `core/plotting/style.py` (reexporta).
- Novos: `core/colors.py`, `tests/test_theme_contrast.py`.
- Teste do modo Sistema: patch de `QStyleHints.colorScheme` e emissão manual de `colorSchemeChanged`
  (o `offscreen` não muda o esquema sozinho).
- Rodar `uv run python scripts/screenshot.py --plot` antes e depois e anexar os PNGs à revisão
  (mudanças de cor).

## Critérios de aceite e testes
- [x] `ui.theme: system` com o esquema do sistema `Dark` aplica `dark`. Ao emitir `colorSchemeChanged`
      com `Light`, aplica `light`, e `theme_changed` emite `"light"`.
- [x] O botão Tema cicla os 3 modos, e o QSettings guarda o modo.
- [x] `ui.font_scale: 1.25`: o QSS montado tem `font-size: 15px` onde antes havia `12px`. `mono_font(11)`
      tem `pixelSize` 14. A grade em 1,6 não corta o nome do arquivo (altura do item ≥ altura do texto).
- [x] `tests/test_theme_contrast.py` passa nos dois temas, incluindo os tokens das specs 10 e 11.
- [x] Nenhum uso de `text_dim` para texto informativo (`grep` nos delegates: metadados usam `text_meta`).
- [x] Tab a partir da barra de atividades percorre as áreas na ordem do R4.3. Ctrl+2 dá foco à grade, e
      o item atual mostra o anel.
- [x] Botões só de ícone têm `accessibleName` não vazio.
