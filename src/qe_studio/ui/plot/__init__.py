"""Detecting, plotting, tuning and exporting, and the Grids (PRD §3, §4, spec 23).

- ``plot_workflow``: detect → choose or map → load → plot tab → render → export.
- ``plot_button``: the activity bar's "Plot"; ``generate_plot``: the panel's "Gerar Plot" (Ctrl+G).
- ``plot_settings``: the ``<kind>.plot`` files, written off the GUI thread.
- ``plot_export``: saving into ``<simulation>/plots/`` without blocking the window.
- ``grids_controller``: the "Grids" button and window; ``grid_loader``: the sessions of its cells.

Their widgets are in ``ui/widgets/plot``.
"""
