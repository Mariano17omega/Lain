# Spec 5: Grade de arquivos e menu de contexto

| | |
|---|---|
| **Prioridade** | 5 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 4 (rótulos SEM ERROS/ERRO dos logs de job) |
| **Usada por** | nenhuma |
| **Esforço** | G (o menu de contexto é a maior parte) |

## Itens de origem (`Ideias.md`)

> - Na visualização dos arquivos da pasta no formato de grade de icones, além dos nomes, é exibido o tamanho do arquivo, quero que remova a exibição do tamanho do arquivo. Mantenha as labels 'OK', 'icompleto', etc. que informam os estados dos arquivos.
> - Na visualização de arquivos em grade, adicione um atalho para voltar para voltar para a pasta anterior, seria um equivalente ao "cd ..", Deve ser sempre o primeiro elemento da grande. è apenas um atalho visual para facilitar a navegação.
> - Quando cliclo com o botão direito do mouse em um arquivo ou pasta, deve abrir algumas opções: 'Abrir local de origem', 'Abrir com' (Para escolher um programa para abrir), 'Copiar', 'Renomear'. Apenas essas opções. No futuro será implementado mais, por enquando só essas.

Decisão confirmada: "Abrir com" é um **submenu de programas** instalados que abrem aquele tipo,
lidos dos `.desktop` do sistema, mais "Outro programa…".

## Situação atual

- Rótulo dos cards: `FileCardDelegate._meta` (`src/qe_studio/ui/widgets/file_grid.py:150`) devolve
  `"12.3 KB · OK"`, `"12.3 KB · incompleto"` ou só o tamanho, e `"N itens"` para pastas. O mesmo texto
  é usado na grade e na lista.
- A grade e a árvore usam modelos `QFileSystemModel` separados (`make_fs_model`,
  `src/qe_studio/ui/widgets/fs_model.py:19`) com filtro `NoDotAndDotDot`, e o `FileFilterProxy` ainda
  esconde nomes que começam com `.` (`fs_model.py:66`). Não existe entrada `..`. Para subir de nível, é
  preciso usar a árvore.
- Navegação: ativar uma pasta na grade emite `folder_activated` → `ExplorerPanel.select_path`
  (`src/qe_studio/ui/main_window.py:218`), que seleciona a pasta na árvore e dispara
  `folder_selected` → `MainWindow.on_folder_selected` → `FilePanel.set_folder`.
- Nenhuma view tem menu de contexto. Os modelos são `setReadOnly(True)`.
- O `QMenu` já tem estilo com tokens (`src/qe_studio/ui/resources/styles/base/app.qss:34-48`).
- `FolderMemory` (`src/qe_studio/core/detection.py:16`) guarda mapeamentos e rótulos por caminho
  absoluto resolvido da pasta.

## Requisitos

### R1: Grade sem tamanho de arquivo
1. No **modo grade**, a linha de metadados dos cards de arquivo mostra só o estado:
   - saídas do QE: "OK" (success), "INCOMPLETO" (warning), "AVISO" (warning), com os mesmos critérios
     da árvore (`explorer.py:87-92`);
   - logs de job: "SEM ERROS" / "ERRO" (spec 4);
   - demais arquivos: linha vazia.
2. Pastas continuam mostrando "N itens".
3. No **modo lista**, os metadados continuam com tamanho, e o estado aparece junto quando existir.
4. Textos em maiúsculas, iguais aos da árvore. Hoje a grade usa "incompleto" em minúsculas.

### R2: Atalho `..` (pasta acima)
1. Quando a pasta exibida na grade **não** é a raiz do projeto (`paths.local_root`), o primeiro item é
   um card `..` com ícone `drive_folder_upload` (token `icon_folder`) e metadado "pasta acima".
2. Ele é sempre o primeiro item em qualquer ordenação (nome, tamanho, data, crescente ou decrescente),
   nos modos grade e lista.
3. Duplo clique ou Enter no `..` navega para a pasta pai pelo mesmo caminho de uma pasta comum
   (`folder_activated` com o caminho do pai), então a árvore acompanha a seleção.
4. Na raiz do projeto, o `..` não aparece. O Lain não navega acima de `local_root`.
5. O `..` não entra na contagem do cabeçalho "ARQUIVOS (N)" nem tem menu de contexto (R3.6).
6. Atalhos de teclado na grade: Backspace e Alt+↑ também sobem um nível.

### R3: Menu de contexto (árvore e grade)
Botão direito sobre um arquivo ou pasta, na árvore ou na grade (modos grade e lista), abre um menu com
**exatamente** estas ações, nesta ordem:

1. **Abrir local de origem.** Abre o gerenciador de arquivos do sistema na pasta que contém o item,
   com o item selecionado quando o ambiente permitir.
   - Linux: D-Bus `org.freedesktop.FileManager1.ShowItems([uri], "")` via `PyQt6.QtDBus` (Dolphin,
     Nautilus, Nemo…). Se falhar, `QDesktopServices.openUrl` na pasta pai.
   - Windows: `explorer /select,<caminho>` via `QProcess.startDetached`.
2. **Abrir com ▸**, um submenu:
   - primeiro, o programa padrão do tipo, com o sufixo " (padrão)";
   - depois, os demais programas registrados para o tipo MIME do item, em ordem alfabética, com ícone
     (`QIcon.fromTheme(Icon)`);
   - separador e **"Outro programa…"**: diálogo para escolher um executável (`QFileDialog`) ou digitar
     um comando, executado com o caminho como argumento;
   - para pastas, usa os programas de `inode/directory`.
   - Tipo MIME via `QMimeDatabase.mimeTypeForFile`, incluindo os tipos pais (ex.: um `.in`
     identificado como `text/plain` lista os editores de texto).
   - Os programas vêm dos `.desktop` em `$XDG_DATA_HOME/applications` e `$XDG_DATA_DIRS/*/applications`
     (campo `MimeType`), ignorando `NoDisplay=true`, `Hidden=true` e `TryExec` inexistente. O padrão
     vem de `mimeapps.list` (`$XDG_CONFIG_HOME`, `$XDG_CONFIG_DIRS`, `applications/`) e, se não
     houver, do primeiro programa da lista.
   - Execução com `QProcess.startDetached(programa, argumentos)`, **sem shell**. Os códigos do campo
     `Exec` (`%f %F %u %U %i %c %k`) são substituídos conforme a especificação Desktop Entry, e o
     caminho vai como argumento separado. Nomes de arquivo nunca são interpolados numa string de
     comando.
   - Windows: o submenu é substituído por uma ação única que abre o diálogo nativo
     (`rundll32 shell32.dll,OpenAs_RunDLL <caminho>`).
3. **Copiar.** Coloca o item na área de transferência, pronto para colar no gerenciador de arquivos
   ou no terminal:
   - `text/uri-list` com a URL `file://`;
   - `x-special/gnome-copied-files` = `copy\nfile://…` (Nautilus/Nemo);
   - `text/plain` com o caminho absoluto.
   - Mensagem no rodapé: "Copiado: <nome>".
4. **Renomear.** Diálogo com o nome atual já preenchido:
   - validações, com mensagem no próprio diálogo: nome vazio; contém `/` (e `\` no Windows); `.` ou
     `..`; nome igual ao atual (fecha sem fazer nada); **destino já existe → recusa, nunca
     sobrescreve** (PRD §7);
   - texto de aviso no diálogo: "Se esta pasta também existe no cluster, a próxima sincronização
     trará de volta o nome original." (o sync é só pull);
   - executa com `Path.rename`. O modelo é somente leitura e continua assim;
   - depois de renomear: `DetectionService.invalidate(pasta pai)`; abas abertas cujo caminho está no
     item renomeado (arquivo, ou qualquer arquivo/gráfico dentro da pasta renomeada) são fechadas, com
     flush do `.plot` antes (spec 3); entradas do `FolderMemory` para a pasta ou subpastas renomeadas
     são migradas (novo `FolderMemory.rename(old, new)`); a seleção passa para o item com o nome novo;
   - erro do sistema (permissão etc.): `QMessageBox.warning` com a mensagem.
5. Clique direito em área vazia não abre menu.
6. O menu não aparece para o `..` (R2). Na raiz do projeto (item raiz da árvore), "Renomear" fica
   desabilitado.

## Fora de escopo
- Colar, excluir, mover, criar pasta, arrastar e soltar.
- Renomear pelo próprio card/linha (edição inline).
- Operações em vários itens selecionados (as views são de seleção única).

## Decisões assumidas (confirmar na revisão)
1. O modo lista mantém o tamanho (R1.3). Só o modo grade perde o tamanho.
2. Backspace e Alt+↑ sobem um nível (R2.6).
3. "Abrir local de origem" numa pasta abre a pasta **pai** com a pasta selecionada, e não a própria
   pasta.
4. Não haverá item "Visualizar no Lain" no "Abrir com" (a lista pedida é fechada).
5. Renomear fecha as abas afetadas em vez de tentar reapontá-las para o novo caminho.

## Notas de implementação
- `..` (abordagem recomendada, verificar na implementação): no modelo da **grade**, trocar
  `NoDotAndDotDot` por `NoDot` para o `QFileSystemModel` listar `..`. No `FileFilterProxy`
  (`fs_model.py:27`), aceitar `..` só quando a pasta exibida é diferente da raiz e forçá-lo em primeiro
  lugar em `lessThan`, independentemente de `sortOrder`. `proxy.path()` de `..` deve resolver para o
  pai. A árvore continua com `NoDotAndDotDot`. **Alternativa**, se o `..` do `QFileSystemModel` se
  mostrar instável: linha sintética via proxy intermediário (`QIdentityProxyModel` que insere a linha 0).
- Contagem do cabeçalho: `FilePanel._update_count` (`file_grid.py:313`) subtrai o `..`.
- Menu: um único construtor, por exemplo `ui/widgets/context_menu.py:build_item_menu(path, is_root)`,
  usado por `ExplorerPanel` e `FilePanel` (`setContextMenuPolicy(CustomContextMenu)` +
  `customContextMenuRequested`). As ações que mexem no estado global (renomear, fechar abas, memória)
  sobem por sinais até o `MainWindow`.
- Descoberta de programas: novo `src/qe_studio/core/desktop_apps.py`, sem Qt, testável:
  `DesktopApp(id, name, exec, icon, mime_types)`, `apps_for(mime_types) -> list[DesktopApp]`,
  `default_app(mime_types)`, `expand_exec(app, path) -> list[str]`. Nome localizado `Name[pt_BR]` →
  `Name[pt]` → `Name`. Cache por sessão, construído na primeira abertura do submenu.
  O `conftest.py` já redireciona `XDG_*`, então os testes criam `.desktop` falsos em
  `XDG_DATA_HOME/applications`.
- `FolderMemory.rename(old: Path, new: Path)`: reescreve chaves que são `old` ou estão abaixo dele e
  também os caminhos dentro dos mapeamentos.

## Critérios de aceite e testes
- [ ] Grade: `_meta` de arquivo comum devolve texto vazio; saída do QE incompleta devolve
      "INCOMPLETO"; nenhum texto contém "KB"/"MB" no modo grade. No modo lista, contém.
- [ ] `..`: presente como linha 0 numa subpasta em todas as ordenações; ausente na raiz; ativá-lo muda
      `files.folder` para o pai e seleciona o pai na árvore; o cabeçalho conta sem ele; Backspace sobe.
- [ ] Menu: para arquivo e pasta, os textos das ações são exatamente
      `["Abrir local de origem", "Abrir com", "Copiar", "Renomear"]`; nenhum menu no `..`; "Renomear"
      desabilitado na raiz.
- [ ] Copiar: `QApplication.clipboard().mimeData()` tem a URL do arquivo, `text/plain` com o caminho e
      `x-special/gnome-copied-files`.
- [ ] Renomear: sucesso renomeia no disco e fecha a aba aberta do arquivo; destino existente →
      recusa, nada muda; nomes inválidos são recusados; renomear pasta com mapeamento em
      `FolderMemory` migra a chave.
- [ ] `tests/test_desktop_apps.py`: `.desktop` falsos com `MimeType=text/plain;` aparecem para `.in`;
      `NoDisplay=true` é ignorado; `mimeapps.list` define o padrão; `expand_exec` com `%f`/`%U` gera
      a lista de argumentos correta e sem shell.
- [ ] "Abrir local de origem" e "Abrir com" são testados com monkeypatch em
      `QProcess.startDetached`/`QDesktopServices.openUrl` (nenhum programa real é lançado).
