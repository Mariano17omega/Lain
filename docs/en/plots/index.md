# Plots — overview

Plots are made with matplotlib and meant for publication. There are five detectable types and two composed ones:

| Type | Source | Page |
|---|---|---|
| Band structure | `BANDS` folder | [Bands](bands.md) |
| PDOS | `PDOS` folder | [PDOS](pdos.md) |
| Bands + DOS | one bands folder + one PDOS folder | [Bands with DOS](bands-dos.md) |
| Relax / vc-relax | `pw.x` output | [Relax](relax.md) |
| SCF convergence | `pw.x` output | [SCF](scf.md) |
| Plot grid | plots already open | [Grids](grids.md) |

## How to plot

1. Select the folder (or, for Bands + DOS, both folders with `Ctrl`-click).
2. **Plot** in the activity bar, **Gerar gráfico** (`Ctrl+G`) or **Plotar** in the context menu.
3. The left panel switches to the **tuning panel** (the **Árvore** button goes back). The panel is generated from the
   module's `ParamField` list, in sections (Energy, x axis, Style, Spin, Projections…).
4. **Exportar** (`Ctrl+E`) saves into the simulation's `plots/`.

A folder plotted before reopens as it was (from its `.plot`) without saving again. With
`ui.auto_generate_plot: false`, a never-plotted folder only opens the panel and **Gerar Plot** plots.

Hovering shows the values under the cursor in the plot toolbar (k and energy with the nearest high-symmetry point,
PDOS, relax step, SCF iteration). Toolbar zoom/pan update the energy window.

## Persistent settings (`.plot`)

Settings are kept in `<kind>.plot` (e.g. `bands.plot`) in `<simulation>/plots/` and come back next time.
**Restaurar padrões** (restore defaults) deletes the file. An old `.plot` in the simulation folder itself is no longer
read.

## Styles { #styles }

The look of a new plot (size, line width, colors, background, legend) comes from the **style** picked in
**Estilo do gráfico** (the first field of the Style section). Each style is a YAML file in
`src/qe_studio/resources/templates/plot_styles/`; `padrao.yaml` is the default. To make one, copy it with another
name, set `name:` and keep only the fields that change:

```yaml
lain_style: 1
name: Dark
params:
  background: "#111827"
  valence_color: "#facc15"
  orbital_colors: {s: "#f97316"}   # added to the default's map, not replacing it
```

A new style shows up after **Recarregar config.yaml** (or the next start). Lain only **reads** styles.

!!! info "Figures are independent of the app theme"
    The look comes from the parameters (`core/plotting/style.py:figure_style`), never from the dark/light theme, so the
    preview and the export are identical. The default background is white.

## Export

- Formats: `plot.export.formats` (`png`, `svg`, `pdf`) and DPI `plot.export.dpi` (300/600).
- Name: `<project>-<folders>-<plot>.png` (path from the root); bands, PDOS and Bands + DOS also get a `.csv` of the
  plotted data (`;` separator and decimal comma, for Excel/Origin in pt-BR).
- An existing file is never replaced without asking.
- Plot of a remote folder: copy in `tmp_remote/`, exports in `tmp_remote/plots_remote/`.

Code: `core/calculations/*` (modules), `core/plotting/*` (style, export, session), `ui/plot/*`.
To create a new type: [Code map](../code-map.md#adding-a-plot).
