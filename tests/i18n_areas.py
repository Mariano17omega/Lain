"""Which spec translates which part of the code: the per-area gate of the i18n series (spec 52 R2).

``AREAS`` maps a file prefix (relative to ``src/qe_studio``) to the number of the spec that
translates it; the longest matching prefix wins and a file that matches none is spec 53's. A spec of
the series adds its number to ``DONE`` when its area is translated: from then on ``test_i18n`` fails
on an untranslated message with a location there (a message shared by two areas is required when the
first of them is done). ``scripts/i18n.py check`` prints the table. Spec 60 removes this module.
"""

from __future__ import annotations

DEFAULT_AREA = 53  # the window, menus, tree, grid, general dialogs, core/*.py, i18n.py

AREAS: dict[str, int] = {
    # 54: text, input, diff and summary viewers, and the reading of QE outputs
    "core/qe/": 54,
    "core/text_preview.py": 54,
    "core/textfile.py": 54,
    "core/qsub_lint.py": 54,
    "ui/widgets/text_viewer.py": 54,
    "ui/widgets/diff_view.py": 54,
    "ui/widgets/input_view.py": 54,
    "ui/widgets/summary_view.py": 54,
    "ui/widgets/summary_widgets.py": 54,
    "ui/widgets/markdown_view.py": 54,
    "ui/widgets/code_view.py": 54,
    # 55: plots, the adjustments panel, Grids and the atoms
    "core/calculations/": 55,
    "core/plotting/": 55,
    "core/compounds.py": 55,
    "core/grid_store.py": 55,
    "ui/plot_button.py": 55,
    "ui/plot_export.py": 55,
    "ui/plot_settings.py": 55,
    "ui/plot_workflow.py": 55,
    "ui/generate_plot.py": 55,
    "ui/grid_loader.py": 55,
    "ui/dialogs/atoms.py": 55,
    "ui/dialogs/grid_cells.py": 55,
    "ui/dialogs/grid_dialog.py": 55,
    "ui/widgets/atom_table.py": 55,
    "ui/widgets/param_widgets.py": 55,
    "ui/widgets/params_body.py": 55,
    "ui/widgets/plot_params.py": 55,
    "ui/widgets/plot_view.py": 55,
    # 56: the "Criar cálculo" window, its base and the surface package
    "core/calc_create/": 56,
    "ui/dialogs/calc_create/": 56,
    "ui/widgets/kpath_editor.py": 56,
    "ui/calc_create_controller.py": 56,
    "ui/derive_controller.py": 56,
    # 57: the calculation types of "Criar cálculo"
    "core/calc_create/types/": 57,
    # 58: cluster and sync
    "core/sync/": 58,
    "ui/sync_coordinator.py": 58,
    "ui/dialogs/sync_dialog.py": 58,
    "ui/dialogs/sync_pages.py": 58,
    # 59: the 3D view
    "core/structure3d/": 59,
    "ui/widgets/structure3d/": 59,
    "ui/structure3d_controller.py": 59,
}

DONE: set[int] = {53, 54, 55}


def area_of(filename: str) -> int:
    """The area of a file (relative to ``src/qe_studio``): its longest prefix in ``AREAS``."""
    prefixes = [prefix for prefix in AREAS if filename.startswith(prefix)]
    return AREAS[max(prefixes, key=len)] if prefixes else DEFAULT_AREA
