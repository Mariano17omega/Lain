# Band structure

**Detection (`BANDS`)**: the `bands.x` output (`.gnu`/`.dat`), the `pw.x` input/output with `calculation='bands'` (for
the k path and labels) and the SCF (Fermi energy, electrons). Missing SCF → looked up in sibling `*scf*` folders;
missing roles can be mapped by hand.

## Features

- High-symmetry path with Γ labels (`labels` overrides; **Linhas de alta simetria** toggles the lines).
- Energy **reference**: `E_F (SCF)`, `Topo da valência (VBM)`, `Meio do gap` (mid-gap) or `Absoluta`; `E mín`/`E máx`
  window; x-axis window (`x mín`/`x máx`); Fermi line.
- Colors: valence, conduction, Fermi.
- **Energy gap in the legend** (`legend_gap`): gap = CBM − VBM (not the Fermi energy), with **Método do gap**:
  *Automático* (electron count), *HOMO/LUMO do SCF* or *Maior intervalo na janela* (largest gap in the window).
- **Spin-polarized** (two `bands.x` runs, `spin_component` 1 and 2): **Canais** (Both/↑ only/↓ only), **Disposição**
  (overlaid/side by side), **Cores por** (channel or valence/conduction), ↑/↓ colors; one gap per channel.
- CSV of the data on export.

Code: `core/calculations/bands/` (`detection.py`, `data.py`, `gap.py`, `params.py`, `render.py`, `table.py`,
`module.py`), parser in `core/qe/bands_x.py`.
