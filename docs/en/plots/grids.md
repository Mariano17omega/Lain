# Grids

The **Grids** button (activity bar; *Plots ▸ Grids…* menu) joins **already plotted** plots in one N × M figure. It is
never detected: it is born from open plot sessions.

- Each cell has a position and a title; `cell_width`/`cell_height` set the size of each.
- Grids are saved by name in `.lain/` (`grid_store.py`) and reopened later.
- The individual plots can be hidden with the **Gráficos** button.
- Exports like any plot (PNG/SVG/PDF).

Code: `core/calculations/grid/`, `core/plotting/grid.py`, `grid_session.py`, `core/project/grid_store.py`,
`ui/plot/grids_controller.py`, `ui/dialogs/grid_dialog.py`.
