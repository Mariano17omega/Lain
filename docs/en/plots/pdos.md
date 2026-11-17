# PDOS

**Detection (`PDOS`)**: `*pdos_atm#*` files from `projwfc.x` (in the folder or `orbitals/`), plus the SCF/NSCF output
(Fermi, HOMO/LUMO).

## Features

- **Fermi source** (SCF or NSCF), shift to E_F, `E mín`/`E máx` window, `dos_max`, **orientation** (energy on x or y).
  In insulators, E_F is the middle of the gap: see [Fermi level in insulators](index.md#fermi-in-insulators).
- **Grouping**: *Species + orbital*, *Species* or *Orbital*; total DOS (own color); fill occupied states.
- **Átomos…** (atoms): chooses which atoms are included; the selection is remembered per compound (formula + species
  order) in `.lain/compounds.json`.
- **Series** can be hidden and recolored; color maps per orbital and per species.
- **Spin** (when two channels exist): *Mirrored (↓ negative)*, *Overlaid*, *↑ only*, *↓ only*, *Sum (↑+↓)*.
- **Gap in the legend** (`legend_gap`) from HOMO/LUMO or from the DOS curve.
- **Spilling** (read from the projwfc.x output) in the status line: the fraction of the occupied charge the atomic
  basis leaves out, which is why the sum of the projections falls short of the total DOS (`pdos_tot`). Above 5 % it
  becomes a warning.
- With **Átomos…**, the status line adds up the **Löwdin charges** of the chosen atoms (`Löwdin = … e`, with `↑−↓`
  when there is spin): the charge on an adsorbate, for instance.
- CSV of the data on export.

Code: `core/calculations/pdos/` (`atoms.py`, `data.py`, `gap.py`, `params.py`, `render.py`, `table.py`),
parsers in `core/qe/projwfc.py` and `core/qe/lowdin.py`, selection in `core/project/compounds.py`.
