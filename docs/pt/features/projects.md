# Projetos

Um **projeto** é uma pasta de primeiro nível de `paths.local_root`. O seletor de projeto fica no painel esquerdo;
**Criar projeto…** (menu *Arquivo*) cria a pasta (nome validado; `trash` é reservado).

As configurações do projeto ficam em `<local_root>/.lain/` (copiar a raiz leva tudo junto):

| Arquivo | Guarda |
|---|---|
| folder memory | mapeamentos manuais de arquivos por pasta |
| grids | Grids salvos |
| compounds | seleção de átomos da PDOS por composto |
| navegação | favoritos e recentes |

A pasta é oculta, nunca sincronizada e só é criada na primeira gravação. Se a raiz é somente leitura, o Lain usa uma
pasta própria dentro da pasta de dados.

Código: `core/project/` (`projects.py`, `project_data.py`, `folder_memory.py`, `grid_store.py`, `compounds.py`,
`nav_store.py`) e `ui/files/project_controller.py`.
