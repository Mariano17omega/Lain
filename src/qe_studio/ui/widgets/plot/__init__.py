"""The plot's widgets: the figure, the adjustments panel and the preview of a grid (PRD §2.1.2,
spec 23).

- ``plot_view``: the plot tab, a toolbar and the canvas kept at the export aspect ratio.
- ``plot_params``: the adjustments panel, one ``params_body`` per open plot, built from the module's
  parameter schema; ``param_widgets``: its building blocks.
- ``atom_table``: a table of atoms to pick from (the PDOS atoms, the "Átomos" tab of "Criar
  cálculo").
- ``grid_preview``: the thumbnail of a grid of plots.
"""
