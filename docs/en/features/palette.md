# Command palette

`Ctrl+K` (menu *Ajuda ▸ Paleta de comandos*, i.e. *Help ▸ Command palette*) opens a fuzzy search over **menu
actions** and the project's **folders**. Type part of a name, arrows to choose, `Enter` runs/opens.

- Actions come from the single table `ui/actions.py:ACTIONS` (stable id, menu, text, shortcut).
- Folders come from the index `core/search/folder_index.py`, searched by `core/search/fuzzy.py` (accent-insensitive).
- `F1` lists all shortcuts.
