# Explorador e navegação

- **Árvore** (esquerda) e **grade** de arquivos (centro). `..`, `Backspace` ou `Alt+↑` sobem uma pasta. A árvore lista
  só pastas; o ícone de arquivo no cabeçalho (ou `ui.tree_show_files`) inclui os arquivos.
- **Caminho clicável** na barra superior (caminhos longos dobram níveis do meio em **…**; botão direito copia).
- **Histórico**: `Alt+←` / `Alt+→`, botões ◀ ▶ ou botões laterais do mouse.
- **Filtro rápido** (`Ctrl+F` na árvore ou grade): parte do nome (`*` e `?` valem), e em **Filtrar ▾** o tipo detectado
  (BANDS, PDOS…) ou o estado/tipo do arquivo. `Esc` limpa.
- **FAVORITOS** (botão direito ▸ *Adicionar aos favoritos*) e os últimos 10 **RECENTES**, lembrados por projeto.
- **Multi-seleção** na grade (`Ctrl`/`Shift`-clique, `Ctrl+A`): `Enter` abre os arquivos; o menu de contexto oferece
  *Abrir local de origem*, *Copiar* e, para dois inputs QE, *Comparar*.
- **Foco**: `Ctrl+1` árvore, `Ctrl+2` grade, `Ctrl+3` abas, `Ctrl+4` ajustes.
- `F5` atualiza (mantém o que foi lido de arquivos cujo tamanho e data não mudaram; `ui.paranoid_refresh` relê tudo).
- Pastas ocultas por `ui.hidden_dirs` (padrão `tmp`, `*.save`).

Estados mostrados: saídas `OK` / `INCOMPLETO`; logs de fila (`job.o12345`, `job.e12345`) `SEM ERROS` (vazios ou só com
as máquinas do job) ou `ERRO`. Uma pasta com `CRASH` ou `job.o<id>` com conteúdo recebe a etiqueta vermelha `ERRO`
na árvore (a menos que o log seja uma saída QE terminada com `JOB DONE`).

Código: `ui/files/navigation_controller.py`, `core/files/navigation.py`, `core/files/filtering.py`,
`core/project/nav_store.py`.
