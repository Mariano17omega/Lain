# Projects

A **project** is a first-level folder of `paths.local_root`. The project selector sits in the left panel;
**Criar projeto…** (*File* menu, create project) makes the folder (name validated; `trash` is reserved).

Project settings live in `<local_root>/.lain/` (copying the root takes everything along):

| File | Holds |
|---|---|
| folder memory | manual file mappings per folder |
| grids | saved Grids |
| compounds | PDOS atom selection per compound |
| navigation | favorites and recents |

The folder is hidden, never synced and created only on the first write. If the root is read-only, Lain uses a folder
of its own inside the data folder.

Code: `core/project/` (`projects.py`, `project_data.py`, `folder_memory.py`, `grid_store.py`, `compounds.py`,
`nav_store.py`) and `ui/files/project_controller.py`.
