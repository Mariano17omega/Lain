# Spec 62: o botão "Árvore" da barra lateral mostra e oculta a árvore; a seção "Recentes" sai do painel

| | |
|---|---|
| **Prioridade** | 62: pequena e independente das demais da rodada; pode sair em qualquer ordem |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 1 (painéis que se ocultam mantendo a proporção: `LayoutController.set_panel_visible`), spec 16 R4 (seções "Favoritos" e "Recentes", `NavigationStore`), spec 49 (barra lateral de hoje) |
| **Usada por** | spec 65 (o modo remoto troca a página da árvore: o botão desta spec alterna a página que estiver valendo) |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que o botão "Grade" da barra lateral já abriu (spec 1) e só tira uma seção que a spec 16 criou |

## Itens de origem (`Ideias.md`, 25/10/2026)

> - Add no botão 'Tree' a função de mostrar e ocultar aba lateral com a arvore de pastas, igual ao botão 'Tree' que fica na barra superior.
> - Remover a sessão de 'Recents' da aba lateral de exibição da arvore de pastas.

Interpretação: o usuário usa a interface em inglês (`ui.language: en`). 'Tree' é o botão "Árvore" da **barra lateral** (o primeiro, à
esquerda) e o botão "Árvore" da **barra superior** (à direita, junto de "Grade" e "Gráficos"); 'Recents' é a seção "Recentes" acima da
árvore.

## Situação atual

- **R1 (botão "Árvore").**
  - Barra lateral: `ui/widgets/bars.py:117` cria `self.tree` (`ActivityButton`, checável, tooltip "Explorador de pastas"); `:152` o
    marca; `:155` liga `clicked` a `explorer_requested`. `ui/layout_controller.py:82` liga o sinal a `show_tree` (`:86`), que chama
    `set_left_mode("tree")` (`:89`): põe a página da árvore no painel esquerdo e **sempre mostra** o painel (`set_panel_visible("tree",
    True)`, `:93`). Clicar com a árvore à vista não faz nada; o botão só desmarca quando o painel mostra os ajustes do gráfico
    (`ActivityBar.set_left_mode`, `bars.py:172`).
  - Barra superior: `bars.py:229-247` cria os botões "Árvore", "Grade" e "Gráficos" (checáveis); `toggled` → `panel_toggled` →
    `LayoutController.set_panel_visible` (`layout_controller.py:81`, `:95`), que mostra ou oculta o painel esquerdo inteiro (qualquer
    página) e mantém o botão da barra superior em sincronia (`:102-104`).
  - O botão "Grade" da barra lateral já é um alternador igual ao da barra superior: `set_panel_visible` sincroniza os dois
    (`layout_controller.py:105-108`). Para "tree" não há esse trecho: ocultar a árvore pela barra superior deixa o "Árvore" da barra
    lateral marcado.
  - `show_tree` tem outro uso: o botão de voltar do painel de ajustes (`ui/main_window.py:242`, `params.back_requested`), que precisa
    continuar **mostrando** a árvore.
  - Testes de hoje: `tests/test_main_window.py:223` (`test_panel_toggles`) cobre a "Grade" e as páginas, não o clique no "Árvore" com a
    árvore à vista; `tests/test_focus.py:165` (Ctrl+1 traz a árvore de volta dos ajustes).
- **R2 ("Recentes").** `ui/widgets/explorer.py:216` cria `self.recents = NavSection(theme, _("Recentes"), "history", "text_muted")` e
  `:217` põe as duas seções no painel. `ui/navigation_controller.py:171` (`_sections`) liga "favorites" e "recents" (estado aberto em
  `explorer/sections/<nome>` do `QSettings`, `:58` e `:177`); `:188` preenche a seção. Os recentes continuam úteis fora do painel: a
  paleta Ctrl+K os lista (`ui/palette_controller.py:194`, `_recent_rows`) e o `navigation.json` da raiz os guarda (spec 48). Testes da
  seção: `tests/test_favorites_ui.py:126-174` e `tests/test_project_ui.py:101-109`; os do armazenamento ficam em `tests/test_navigation.py`.
  O `QSettings` desta máquina tem `explorer/sections/recents`.
- Tamanhos: `ui/widgets/bars.py` 373, `ui/layout_controller.py` 193, `ui/widgets/explorer.py` 408, `ui/navigation_controller.py` 224.
  `ui/main_window.py` (449/450) não é tocado.

## Requisitos

### R1: "Árvore" da barra lateral alterna a árvore

1. `ui/layout_controller.py`: novo `toggle_tree()`, ligado a `activity.explorer_requested` no lugar de `show_tree` (`:82`):
   - painel esquerdo oculto → mostra o painel na página da árvore;
   - painel à vista na página da árvore → oculta o painel (como o "Árvore" da barra superior);
   - painel à vista nos ajustes do gráfico → troca para a árvore e continua à vista (o botão estava desmarcado: o clique o marca).
2. `show_tree()` continua igual (sempre mostra): o voltar dos ajustes, Ctrl+1 (`focus_controller.focus_tree`) e "Revelar no explorador"
   não mudam.
3. `set_panel_visible("tree", visible)` sincroniza o "Árvore" da barra lateral sem emitir sinal (como faz com a "Grade"): marcado se e só
   se o painel está à vista **e** na página da árvore. O "Árvore" da barra superior continua marcado sempre que o painel está à vista,
   qualquer página (hoje é assim).
4. O estado sai em `layout/tree_visible` como hoje (`layout_controller.py:190`): nada novo no `QSettings`.
5. Tooltip do botão da barra lateral: "Mostrar/ocultar a árvore de pastas" (troca "Explorador de pastas"); o rótulo "Árvore" fica.
6. **Testes** (`tests/test_main_window.py`):
   - `test_sidebar_tree_button_hides_and_shows_the_tree`: clicar com a árvore à vista oculta o painel e desmarca os dois botões "Árvore";
     clicar de novo mostra a árvore e marca os dois (falha hoje: o primeiro clique não oculta).
   - `test_sidebar_tree_button_from_the_adjustments_shows_the_tree`: com os ajustes à vista, o clique mostra a árvore e não oculta nada.
   - `test_top_bar_tree_toggle_unchecks_the_sidebar_button`: ocultar pela barra superior desmarca o da barra lateral.
   - `test_panel_toggles` e `test_ctrl_1_brings_the_tree_back_from_the_adjustments` passam sem mudança.

### R2: sem a seção "Recentes" no painel da árvore

1. `ui/widgets/explorer.py`: sai `self.recents` (e o laço das duas seções vira só "Favoritos"); o painel mostra, de cima para baixo,
   cabeçalho, "Projeto", "Favoritos", filtro e árvore.
2. `ui/navigation_controller.py`: `_sections` só com "favorites"; `_refresh_sections` não preenche recentes. O armazenamento **não muda**:
   `touch_recent`, `prune_missing_recents`, o atraso de gravação (`SAVE_DELAY_MS`) e o `navigation.json` continuam, porque a paleta Ctrl+K
   lista os recentes.
3. Na partida, `NavigationController` remove a chave órfã `explorer/sections/recents` do `QSettings` (como `LayoutController.restore` faz
   com chaves antigas, `layout_controller.py:173-174`).
4. `ui/widgets/nav_sections.py`: docstring passa a falar só de "FAVORITOS" (a classe continua genérica).
5. i18n: a mensagem "Recentes" fica sem uso; `scripts/i18n.py update` a tira do `.po` e `compile` refaz o `.mo`.
6. **Testes:**
   - `tests/test_favorites_ui.py`: saem os testes que leem `window.explorer.recents`
     (`test_recents_are_the_last_visited_folders_newest_first`, `test_recents_come_back_after_a_restart_and_drop_the_missing`) e a linha
     de `recents` em `test_renaming_a_favorite_folder_moves_it`; ficam os que só olham o armazenamento (`test_recents_keep_the_last_ten`,
     `test_recents_are_written_after_a_pause`), e entra `test_the_explorer_has_no_recents_section` (`not hasattr(window.explorer,
     "recents")` e nenhum `NavSection` com o título "Recentes").
   - `tests/test_project_ui.py:109`: sai a linha dos recentes.
   - `tests/test_command_palette.py::test_favorites_and_recents_come_first_on_an_empty_query` passa sem mudança (os recentes seguem na
     paleta).
   - `test_the_orphan_sections_key_is_removed`: um `QSettings` com `explorer/sections/recents` não o tem depois da janela aberta.

## Fora de escopo

- Tirar os recentes da paleta Ctrl+K ou do `navigation.json`: o pedido é só a seção do painel (decisão 2).
- Atalho de teclado para mostrar/ocultar a árvore: não pedido.

## Decisões assumidas (confirmar na revisão)

1. **Nos ajustes, o clique mostra a árvore** (não oculta o painel): é o único caminho de um clique dos ajustes para a árvore pela barra
   lateral, e o botão aparece desmarcado nesse estado, então marcá-lo mostrando a árvore é o que se espera. Ocultar nesse estado continua
   possível pelo "Árvore" da barra superior.
2. **Recentes continuam guardados e na paleta.** Se a ideia era acabar com os recentes de vez, a alternativa é tirar também
   `_recent_rows` da paleta e o `touch_recent` (outra spec, pequena).

## Notas de implementação

- Alterados: `ui/layout_controller.py` (`toggle_tree`, sincronia do botão da barra lateral), `ui/widgets/bars.py` (tooltip),
  `ui/widgets/explorer.py` e `ui/navigation_controller.py` (sem recentes), `ui/widgets/nav_sections.py` (docstring), o catálogo
  `src/qe_studio/locale/en/LC_MESSAGES/lain.po` e o `.mo`.
- Limites: nenhum arquivo perto do limite; `ui/main_window.py` não muda.
- A spec 65 troca a página da árvore no modo remoto (`LayoutController.tree_page`); `toggle_tree` deve perguntar "a página da árvore está
  à vista?" por um único método (`_tree_shown()`), para a 65 só mudar esse ponto.
- Documentação ao implementar: nenhuma (o `README.md` não menciona "Recentes" nem o botão "Árvore": verificado com `grep`); `CLAUDE.md`
  não muda.

## Critérios de aceite e testes

- [ ] O "Árvore" da barra lateral oculta e mostra a árvore e fica em sincronia com o da barra superior
      (`test_sidebar_tree_button_hides_and_shows_the_tree`, `test_top_bar_tree_toggle_unchecks_the_sidebar_button`).
- [ ] Dos ajustes, um clique traz a árvore (`test_sidebar_tree_button_from_the_adjustments_shows_the_tree`); voltar dos ajustes e Ctrl+1
      como hoje (`test_panel_toggles`, `test_ctrl_1_brings_the_tree_back_from_the_adjustments`).
- [ ] O painel não tem "Recentes" (`test_the_explorer_has_no_recents_section`); a paleta ainda lista recentes
      (`test_favorites_and_recents_come_first_on_an_empty_query`); chave órfã removida (`test_the_orphan_sections_key_is_removed`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
