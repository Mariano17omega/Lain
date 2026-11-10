# Bands with DOS

One figure with a **shared energy axis**: bands on the left, PDOS on the right. It is never detected; it is born from
**two folders** selected in the grid (one `BANDS`, one `PDOS`), through **Bandas com DOS** in the context menu or
**Plot**/**Gerar Plot** with both selected. It is saved in the bands folder's `plots/`.

- Bands parameters (reference, window, lines, colors, spin channels) and PDOS parameters (grouping, atoms, series,
  total, fill) together, plus `dos_width_ratio` (width of the DOS panel, default 0.35 of the bands panel).
- `spin_mode` defaults to *Overlaid*: mirroring would make the DOS axis symmetric, odd next to the bands.
- `Gap in legend` shows the bands' gap.
- Both panels use the E_F of the bands, which in insulators is the middle of the gap: see
  [Fermi level in insulators](index.md#fermi-in-insulators).
- In cluster mode, selecting both remote folders and **Plotar** works the same way (copies in `tmp_remote/`).

Code: `core/calculations/bands_dos/` (`pair.py` forms the pair; `module.py`, `render.py`, `params.py`, `table.py`).
