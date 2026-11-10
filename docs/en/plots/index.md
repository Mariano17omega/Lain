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

## Fermi level in insulators { #fermi-in-insulators }

In an insulator or intrinsic semiconductor, the Fermi level lies inside the gap, roughly in the middle. `pw.x` does not
print that value: with fixed occupations it gives the HOMO (the top of the valence) and, with smearing, some point of the
gap. So, when the gap is proven, the E_F of the plots is the **middle of the gap**, `(VBM + CBM) / 2`. Otherwise it is the
value `pw.x` printed.

| Plot | The rule applies when | Middle of the gap |
|---|---|---|
| Bands, no spin | the electron count fills whole bands and there are a VBM and a CBM: fixed occupations, or smearing with E_F between the VBM and the CBM | `(VBM + CBM) / 2` along the k path |
| Bands, spin | both channels have a gap, the global gap opens, the valence bands of both channels add up to the electron count and `pw.x` printed a single E_F | global VBM and CBM |
| PDOS, printed pair | `pw.x` printed HOMO and LUMO (from the NSCF, else the SCF) and the pair opens a gap. An SCF pair, when the NSCF printed none, must agree with the DOS: if its middle falls on states, the empty region just above the HOMO is used | mean of HOMO and LUMO, or the middle of that region |
| PDOS, fixed occupations without a LUMO | an empty region of the total DOS starts up to 0.25 eV above the HOMO | middle of that region |
| PDOS, smearing | the E_F of the NSCF or the SCF is **inside** an empty region of the total DOS and the electron count can fill whole bands | middle of that region |

An **empty region** is a stretch where the total DOS (both spin channels summed) stays within 0.1 % of its maximum, with
states on both sides, and reaches at most 0.01 states/eV at its deepest point. An NSCF E_F inside a band, beyond the
broadened tail (0.25 eV), says the system is a metal, and the SCF is not asked.

The rule does **not** apply, and the printed value stays, when:

- the system is metallic: a band crosses E_F, or E_F falls outside [VBM, CBM] on the path;
- the electron count does not fill whole bands (an odd count without spin);
- E_F was not found (the energies stay absolute);
- only the ↑ channel of a spin run was found;
- every band of the output is filled, leaving no empty band to measure a gap to;
- there are two Fermi energies (↑/↓), from a run with a fixed total magnetization.

**What follows the new E_F:** the Fermi line, the zero of the axis (`E − E_F`), the limit of the filled occupied states, the
valence and conduction colors, the CSV and the Grids. In **Bands + DOS**, both panels follow the E_F of the bands.

**The footer** says when the rule is in force: `HOMO = … eV · E_F = … eV (mid-gap)` with fixed occupations (in the PDOS,
`HOMO = … eV (SCF)` or `(NSCF)`, the run it came from) and `E_F = … eV (mid-gap)` with smearing. In the bands, the
`E_F (SCF)` reference is then called `E_F (meio do gap)`. The **E_F de** field (SCF/NSCF) leaves the PDOS panel when it
would have no effect.

**What does not change:** the **Método do gap** and the references `Topo da valência (VBM)`, `Meio do gap` and `Absoluta`.
With the rule in force, the gap the PDOS legend shows in *Automático* is the one of the region E_F was placed in.

!!! note "Limits"
    - In a PDOS with smearing whose E_F falls in the broadened tail of a band, the printed value stays: the rule prefers not
      to move the E_F of a metal.
    - In a PDOS with only a HOMO printed and a broadening above about 0.1 eV, the empty region starts too far from the HOMO
      and the printed value stays.
    - In the bands, the middle of the gap is the one along the k path. An extremum off the path shifts it.
    - Bands and PDOS of the same material may differ slightly, since they measure the gap on different grids.

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
