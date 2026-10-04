# Spec 16: Navegação (caminho clicável, histórico, filtros, favoritos) e multi-seleção

| | |
|---|---|
| **Prioridade** | 16 |
| **Status** | Implementada. Desvios: a lógica sem widgets ficou em `core/navigation.py` (histórico, segmentos do breadcrumb), `core/nav_store.py` (favoritos e recentes) e `core/filtering.py` (nome e categorias), e a ligação em `ui/navigation_controller.py`, e não em `ui/navigation.py` (CLAUDE.md, spec 15 R5.3); o campo de filtro fica numa linha abaixo do cabeçalho do painel (a contagem "(k de n)" fica no cabeçalho); o duplo clique com vários itens abre só o clicado (o clique já troca a seleção), Enter abre todos; os botões laterais do mouse usam um filtro de eventos da aplicação limitado à janela (o Qt entrega o clique ao widget sob o cursor); o filtro de badge na grade pede a detecção das subpastas listadas (a grade não pinta badges, então nada mais a pediria), mas o filtro em si só lê o cache; categoria vazia esconde o tipo oposto (estado "INCOMPLETO" lista só arquivos, badge "RELAX" só pastas); o filtro da grade é limpo ao mudar de pasta e o da árvore ao navegar para algo que ele esconderia; a raiz não entra nos recentes; "Comparar" abre os dois inputs em ordem de caminho; "Remover dos favoritos" aparece quando todos os itens já são favoritos |
| **Depende de** | spec 5 (menu de contexto, `..`), spec 10 (Ctrl+F por foco), spec 11 ("Comparar" inputs), spec 14 (chave relativa da memória) |
| **Usada por** | spec 18 (a paleta de comandos lista favoritos e recentes) |
| **Esforço** | G |

## Itens de origem (`report.md` §3, "Navegação")

> - **Breadcrumb clicável** no lugar do `path_chip` elidido (`bars.py:151-154,190-195`) + **histórico** Alt+←/→. Hoje só há `..`.
> - **Filtro rápido** (Ctrl+F) no explorador e na grade, e filtro por badge (BANDS/PDOS/RELAX) e por estado (INCOMPLETO/ERRO). Projetos com centenas de pastas não têm busca; só ordenação por nome/tamanho/data.
> - **Favoritos/recentes**; **multi-seleção** na grade (pré-requisito de F9 e de "copiar vários"); **paleta de comandos** Ctrl+K.

Decisões do usuário (30/09/2026):
- A multi-seleção na grade **entra**, embora seja pré-requisito do F9 (comparar simulações), que foi
  adiado.
- A paleta de comandos fica na spec 18, junto com a ajuda e os atalhos.

## Situação atual

- **Caminho na TopBar:** `path_chip` (`ui/widgets/bars.py:151-154`) é um `QLabel#pathChip` com largura
  máxima de 420 px. `set_path` (l.190-195) mostra `~/…`, elide à esquerda em 380 px e põe o caminho
  completo no tooltip. Não é clicável.
- **Histórico:** não existe. Para subir há o `..` da grade, Backspace/Alt+↑ (`file_grid.py:230-233`) e
  `go_up` (l.345-348), nunca acima de `local_root`.
- **Seleção:**
  - grade: `QListView` com `SingleSelection` (`file_grid.py:220`), modos grade e lista, e ordenação
    Nome/Tamanho/Data (l.320-343);
  - árvore: `SingleSelection` (`explorer.py:136`);
  - pastas na árvore mostram badges (`explorer.py:60-62`, `ui/painting.py`);
  - arquivos mostram rótulos de estado (`status_label`, `ui/file_types.py:77-89`): `OK`, `INCOMPLETO`,
    `AVISO`, `SEM ERROS`, `ERRO`.
- **Filtro:** nenhum filtro do usuário. `FileFilterProxy.filterAcceptsRow` (`ui/widgets/fs_model.py:73-88`)
  só esconde dotfiles e os `ui.hidden_dirs`.
- **Menu de contexto:** `ItemActions.menu(path, can_rename)` (`ui/widgets/context_menu.py:51-62`), para
  um item. Grade e árvore emitem `item_menu_requested(Path, QPoint)`.
- **Navegação entre pastas:** `ExplorerPanel.select_path` → `folder_selected` →
  `MainWindow.on_folder_selected` → `FilePanel.set_folder` (`main_window.py:402-406`). A última pasta
  fica em QSettings (`explorer/last_folder`).

## Requisitos

### R1: Caminho clicável (breadcrumb)
1. O `path_chip` vira o widget `Breadcrumb` na mesma posição da TopBar. Um segmento por nível, do
   **nome do projeto** (raiz `local_root`) até a pasta atual, separados por `›`.
2. Clicar num segmento navega para aquela pasta pelo fluxo normal (`select_path`), e a árvore e a grade
   acompanham.
3. Sem espaço, os segmentos do meio colapsam num botão `…`, com um menu dos níveis ocultos. A raiz e a
   pasta atual ficam sempre visíveis.
4. Clique direito no breadcrumb: "Copiar caminho" (absoluto).
5. Fonte mono e tokens existentes (`text_secondary`, `accent` no hover). O tooltip mostra o caminho
   absoluto.

### R2: Histórico de navegação
1. Pilhas "voltar" e "avançar" de pastas visitadas (até 50, sem repetir a mesma pasta seguida).
2. Atalhos: Alt+← / Alt+→, botões laterais do mouse (`Qt.MouseButton.BackButton`/`ForwardButton`, por
   filtro de eventos na janela) e botões ◀ ▶ à esquerda do breadcrumb (desabilitados quando a pilha
   está vazia).
3. Navegar por histórico não empilha de novo. Navegar para uma pasta nova limpa o "avançar".
4. Uma pasta que sumiu (renomeada/apagada) é pulada com a mensagem no rodapé "Pasta não existe mais:
   <nome>".
5. Renomear (spec 5) atualiza os caminhos das pilhas.

### R3: Filtro rápido e filtros por tipo/estado
1. **Grade:** Ctrl+F com foco na grade mostra um campo de filtro no cabeçalho "ARQUIVOS". Ele filtra por
   nome a pasta exibida: subcadeia sem diferenciar maiúsculas, e `*`/`?` viram curinga. Esc limpa e
   esconde. O `..` nunca é filtrado. O cabeçalho mostra "ARQUIVOS (7 de 120)".
2. **Árvore:** Ctrl+F com foco na árvore mostra um campo no cabeçalho do explorador. Ele filtra por nome
   as pastas **já carregadas** pelo `QFileSystemModel` (com `recursiveFilteringEnabled`), mantendo os
   ancestrais de quem casa. Uma dica no campo avisa: "pastas já abertas".
3. **Filtros por categoria:** um botão "Filtrar ▾" ao lado do campo, com menu de seleção múltipla:
   - pastas (árvore e grade), pelo badge detectado: BANDS, PDOS, RELAX, SCF, CALC, "sem tipo";
   - arquivos (grade), pelo estado: OK, INCOMPLETO, AVISO, ERRO/SEM ERROS, "sem estado"; e pelo tipo
     visual (`file_visual`): inputs, saídas, dados, imagens, outros.
4. O filtro por badge usa só os resultados **já em cache** do `DetectionService` (não força detecção). Uma
   pasta ainda não detectada aparece com o estado "detectando…" e é reavaliada quando chega
   `detected`.
5. Os filtros ativos aparecem como chips removíveis abaixo do cabeçalho. O estado do filtro **não** é
   persistido (some ao fechar).
6. Implementação: `FileFilterProxy` ganha `set_name_filter` e `set_category_filter`, que chamam
   `invalidateFilter()`. Sem leitura de disco no `filterAcceptsRow` (só `peek` de cache).

### R4: Favoritos e recentes
1. **Favoritos:** item novo no menu de contexto de pastas, "Adicionar aos favoritos" / "Remover dos
   favoritos", depois de "Copiar". Uma seção "FAVORITOS" no topo do painel do explorador (colapsável,
   escondida se vazia) lista as pastas com ícone de estrela, e um clique navega.
2. **Recentes:** as últimas 10 pastas distintas visitadas (a partir do R2), numa seção "RECENTES"
   colapsável, abaixo dos favoritos.
3. Persistência em `$XDG_DATA_HOME/qe-studio/navigation.json`, por projeto (chave = `local_root`), com
   caminhos **relativos** à raiz (mesmo esquema do `FolderMemory` da spec 14). Nunca dentro das pastas
   das simulações.
4. Uma pasta inexistente aparece esmaecida, com tooltip "não encontrada", e sai dos recentes na próxima
   sessão. Nos favoritos, só sai se o usuário remover.
5. Renomear (spec 5) migra favoritos e recentes.

### R5: Multi-seleção na grade
1. A grade (modos grade e lista) passa a `ExtendedSelection`: Ctrl+clique, Shift+clique, Ctrl+A e
   seleção por arrasto no modo lista. O `..` nunca entra na seleção (é desmarcado se incluído).
2. A árvore continua com seleção única.
3. Rodapé: "N itens selecionados" quando N > 1.
4. Enter ou duplo clique com vários **arquivos** selecionados abre cada um no workspace (texto/imagem),
   até 10. Acima disso, pergunta "Abrir N arquivos?". Pastas na seleção são ignoradas nesse caso.
5. **Menu de contexto com N > 1** (spec 5 estendida):
   - título desabilitado "N itens";
   - "Abrir local de origem" → `ShowItems` com todas as URIs (selecionadas no gerenciador);
   - "Copiar" → `text/uri-list` e `x-special/gnome-copied-files` com todos os itens, e `text/plain` com
     um caminho por linha. Rodapé: "Copiados: N itens";
   - "Comparar" → só quando são **exatamente 2 inputs do QE** (critério da spec 11, R4.1), e abre a aba
     de diff;
   - "Abrir com", "Renomear", "Plotar" e "Resumo" ficam ocultos;
   - "Adicionar aos favoritos" só se todos forem pastas.
6. Clique direito sobre um item **fora** da seleção atual troca a seleção para esse item, como nos
   gerenciadores de arquivos.
7. O sinal `item_menu_requested` passa a levar `list[Path]`. A árvore emite listas de um item.

## Fora de escopo
- Multi-seleção na árvore.
- Comparar/sobrepor simulações (F9, adiado). A multi-seleção é só a base.
- Arrastar e soltar, colar, mover e excluir.
- Busca recursiva por conteúdo de arquivos.

## Decisões assumidas (confirmar na revisão)
1. O filtro da árvore só alcança pastas já carregadas (R3.2). Uma busca no projeto inteiro fica para a
   paleta de comandos (spec 18), que tem índice próprio.
2. Os filtros não são persistidos (R3.5).
3. Recentes = 10 pastas (R4.2). Favoritos sem limite.
4. Favoritos e recentes em JSON no diretório de dados (R4.3), e não em QSettings, para usar caminhos
   relativos ao projeto como o `FolderMemory`.
5. "Abrir com" fica oculto com vários itens (R5.5), em vez de abrir todos com o mesmo programa.

## Notas de implementação
- Novos: `ui/widgets/breadcrumb.py`, `ui/navigation.py` (histórico + favoritos/recentes, testável sem
  widgets), `tests/test_navigation.py`.
- Alterados:
  - `ui/widgets/bars.py` (breadcrumb e botões ◀ ▶);
  - `ui/widgets/explorer.py` (filtro, seções Favoritos/Recentes);
  - `ui/widgets/file_grid.py` (seleção, filtro, contagem);
  - `ui/widgets/fs_model.py` (filtros);
  - `ui/widgets/context_menu.py` (lista de caminhos, itens novos);
  - `ui/main_window.py` (ou `LayoutController` da spec 15);
  - `tests/test_file_grid_menu.py`;
  - estilos `navigation/*.qss`; tokens novos só se precisar (ex.: `chip_bg`), nos **dois** temas.
- O filtro de evento dos botões laterais do mouse fica na janela, para funcionar com o foco em qualquer
  painel.

## Critérios de aceite e testes
- [ ] O breadcrumb de `<raiz>/a/b/c` tem 4 segmentos. Clicar em "a" seleciona `a` na árvore e na grade.
      Numa janela estreita, aparece `…` com os segmentos ocultos.
- [ ] Histórico: navegar raiz → a → b, Alt+← duas vezes volta à raiz, Alt+→ vai para `a`, e navegar para
      `c` limpa o "avançar".
- [ ] Filtro da grade: "scf" numa pasta das fixtures mostra só os arquivos com "scf" no nome, mais o
      `..`. O cabeçalho conta "(k de n)". Esc restaura.
- [ ] Ctrl+F com foco no texto (spec 10) não abre o filtro, e vice-versa.
- [ ] Filtro por estado "INCOMPLETO" numa pasta com uma saída truncada (cópia) mostra só ela.
- [ ] Filtro por badge "RELAX" no `demo_project` mostra só `01_relax` (depois da detecção).
- [ ] Favoritos: adicionar, reiniciar a janela (`main_window` fixture novo) e ver a pasta em
      "FAVORITOS". O JSON tem caminho relativo.
- [ ] Multi-seleção: Ctrl+clique em 3 arquivos → rodapé "3 itens selecionados". O menu mostra
      `["3 itens", "Abrir local de origem", "Copiar"]`. Copiar põe 3 URIs na área de transferência.
- [ ] Com 2 inputs selecionados, "Comparar" aparece e abre `diff:<a>|<b>`. Com 1 input e 1 saída, não
      aparece.
- [ ] O `..` não entra na seleção com Ctrl+A.
