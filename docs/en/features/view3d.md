# 3D view

Any `pw.x` input has **Visualização 3D**: each click opens a window of its own (two clicks on the same file = two
windows, each with its own settings). A relax shows its *input* geometry.

## Panel

- **Clicked atom**: name as QE numbers it (`O43`), species, mass, pseudopotential, positions, `if_pos`, starting
  magnetization and bonded neighbours.
- **Options**: style, radius, bond factor, repetition, labels and their size, background, bonds, cell, perspective and
  the **x, y, z** and **a, b, c** axes (each with its own thickness).
- **Species** (color, visibility) and **cell**.

## Controls

Drag turns; `Shift`+drag or middle button moves; wheel zooms. `R` / **Resetar vista**; `X`/`Y`/`Z` (*Vista* menu) and
`A`/`B`/`C` look along an axis; `P` toggles perspective. **Rotação** (`x+ x- y+ y- z+ z-`) turns 45° by the right-hand
rule without changing the zoom.

## Measures

**Distância** (two atoms) and **Ângulos** (three; the second is the vertex): each measure becomes a row
(`O43 - H59  0.965 Å`). **Copiar**, **Apagar** (last), **Limpar**, `Delete`.

## Other

- **Print**: PNG at twice the pixels in the folder's `plots/` (`<folders>-<file>-3d.png`, never overwritten).
- **Átomos fixos** (fixed atoms): a ring around atoms with `if_pos = 0`.
- **Restaurar padrões**: options and camera back to defaults (measures stay).
- The view is remembered in `view3d.plot` (in `plots/`, one section per file) when a changed window closes.
- In "Criar cálculo", **Visualizar 3D** shows the SCF and each generated structure and follows the fields as you edit.
- **CIF** generation and **Abrir com XCrysDen** are in the context menu.

Code: `core/structure3d/` (model, bonds, camera, measures) and `ui/widgets/structure3d/`,
`ui/tools/structure3d_controller.py`.
