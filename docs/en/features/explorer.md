# Explorer and navigation

- **Tree** (left) and file **grid** (center). `..`, `Backspace` or `Alt+↑` go up a folder. The tree lists only
  folders; the file icon in its header (or `ui.tree_show_files`) adds files.
- **Clickable path** in the top bar (long paths fold middle levels into **…**; right-click copies).
- **History**: `Alt+←` / `Alt+→`, the ◀ ▶ buttons or the mouse side buttons.
- **Quick filter** (`Ctrl+F` in tree or grid): part of a name (`*` and `?` work) and, under **Filtrar ▾**, the
  detected type (BANDS, PDOS…) or the file state/kind. `Esc` clears.
- **FAVORITOS** (right-click ▸ *Adicionar aos favoritos*) and the last 10 **RECENTES**, remembered per project.
- **Multi-select** in the grid (`Ctrl`/`Shift`-click, `Ctrl+A`): `Enter` opens the files; the context menu offers
  *Abrir local de origem*, *Copiar* and, for two QE inputs, *Comparar*.
- **Focus**: `Ctrl+1` tree, `Ctrl+2` grid, `Ctrl+3` tabs, `Ctrl+4` tuning panel.
- `F5` refreshes (keeps what was read from files whose size and date did not change; `ui.paranoid_refresh` rereads
  everything).
- Folders hidden by `ui.hidden_dirs` (default `tmp`, `*.save`).

States shown: outputs `OK` / `INCOMPLETO` (*incomplete*); queue logs (`job.o12345`, `job.e12345`) `SEM ERROS` (empty
or listing only the job's machines) or `ERRO`. A folder with `CRASH` or a non-empty `job.o<id>` gets the red `ERRO`
tag in the tree (unless the log is a finished QE output with `JOB DONE`).

Code: `ui/files/navigation_controller.py`, `core/files/navigation.py`, `core/files/filtering.py`,
`core/project/nav_store.py`.
