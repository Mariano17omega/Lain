# Quick start

1. **Edit** `config.yaml` with at least `paths.local_root` (where your simulations live). To use the cluster, also set
   `paths.remote_root` and the `cluster:` section — see [Configuration](config.md) and [SSH](ssh.md).
2. Run `uv run lain` (or `lain`).
3. In the tree on the left, pick a simulation folder. The **badges** show what was detected: `BANDS`, `PDOS`, `RELAX`,
   `SCF`, `CALC`; outputs show `OK` / `INCOMPLETO` (*incomplete*).
4. Click **Plot** in the activity bar (or **Ctrl+G**). The plot opens in a tab and the left panel switches to the
   tuning panel; **Árvore** (*Tree*) goes back.
5. Tune it and export with **Exportar** (**Ctrl+E**): figures go to the simulation's `plots/` folder.
6. To generate a new calculation, use **Criar cálculo** ([guide](create-calc/index.md)).
7. To download results from the cluster, use **Sincronizar** (*Cluster* menu) — always with a preview.

## Useful shortcuts

| Shortcut | Action |
|---|---|
| `F1` | Keyboard shortcuts |
| `Ctrl+K` | Command palette |
| `Ctrl+G` / `Ctrl+E` | Generate / export plot |
| `Ctrl+T` | Toggle theme |
| `Ctrl+1..4` | Go to tree, grid, tab area, tuning panel |
| `Alt+←` / `Alt+→` | Back / forward through visited folders |
| `F5` | Refresh |
| `Ctrl+W` / `Ctrl+Q` | Close tab / quit |
