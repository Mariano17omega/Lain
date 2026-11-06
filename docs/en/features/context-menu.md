# Context menu

Right-click a file or folder (grid or tree):

| Item | Purpose |
|---|---|
| **Abrir local de origem** | open the folder in the file manager |
| **Abrir com** | installed programs for the type, or any other |
| **Copiar** | copy the item (paste in the file manager or a terminal) |
| **Renomear** | never overwrites; closes tabs showing the item |
| **Comparar** | two selected QE inputs |
| **Resumo** | QE outputs: tab with state, times, results |
| **Plotar** | SCF output: convergence, not saved |
| **Bandas com DOS** | one bands folder + one PDOS folder selected |
| **Gerar SCF convergido** | converged relax/vc-relax output: creates only the `.in` |
| **Visualização 3D** | any pw.x input |
| **Abrir com XCrysDen** | `xcrysden --pwi` (input) / `--pwo` (output) — needs `paths.xcrysden_path` |
| **Calcular adsorção…** | 2+ selected SCF outputs |
| **Adicionar aos favoritos** | folders |

In cluster mode the menu changes: **Baixar**, **Plotar**, **Copiar caminho**, **Submeter…**, **Cancelar simulação…**,
**Apagar…** — see [Remote mode](../remote-mode.md).

Code: actions in `ui/files/*`, `ui/tools/*` and `ui/cluster/*`; what each module offers comes from hooks in
`core/calculations/base.py` (the UI never knows a module's kind).
