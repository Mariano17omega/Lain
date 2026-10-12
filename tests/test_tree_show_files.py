"""Spec 37 R2: ``ui.tree_show_files`` (the folder tree lists folders only unless it is on)."""

from pathlib import Path

from grid_helpers import names, show_folder, tree_names
from qe_studio.core.config import LoadedConfig, UiConfig, parse_config
from qe_studio.ui.widgets.explorer import ExplorerPanel

FOLDERS = ["01_relax", "02_scf", "03_bands", "04_pdos"]


def reloaded(window, **ui) -> None:
    """ "Recarregar config.yaml" with the ``ui:`` keys of ``ui``."""
    config = parse_config({"paths": {"local_root": str(window.root)}, "ui": ui})
    window._apply_loaded(LoadedConfig(config, None))


def test_the_tree_lists_folders_only_by_default(qtbot, main_window, demo_project):
    window = main_window
    assert window.explorer.proxy.dirs_only
    window.explorer.select_path(demo_project / "03_bands")  # opens it: its files are loaded
    qtbot.waitUntil(lambda: "bands.in" in names(window.files), timeout=5000)
    assert tree_names(window) == FOLDERS
    folder = window.explorer.proxy.index_for(demo_project / "03_bands")
    assert (
        folder.isValid() and tree_names(window, folder) == []
    )  # "tmp" is hidden, the rest are files


def test_the_option_lists_the_files_too(qtbot, tree_files_window, demo_project):
    window = tree_files_window
    assert not window.explorer.proxy.dirs_only
    window.explorer.select_path(demo_project / "03_bands")
    folder = demo_project / "03_bands"
    qtbot.waitUntil(
        lambda: "bands.in" in tree_names(window, window.explorer.proxy.index_for(folder)),
        timeout=5000,
    )


def test_the_grid_is_the_same_either_way(qtbot, window_factory, demo_project):
    seen = []
    for ui in ({}, {"tree_show_files": True}):
        window = window_factory(ui=ui)
        show_folder(qtbot, window, demo_project / "03_bands")
        seen.append(names(window.files))
        window.close()
    assert seen[0] == seen[1] and "bands.in" in seen[0]


def test_reloading_the_config_switches_without_restarting(qtbot, main_window, demo_project):
    window = main_window
    window.explorer.select_path(demo_project / "03_bands")
    folder = window.explorer.proxy.index_for(demo_project / "03_bands")
    assert folder.isValid() and tree_names(window, folder) == []
    reloaded(window, tree_show_files=True)
    assert not window.explorer.proxy.dirs_only
    bands = demo_project / "03_bands"
    qtbot.waitUntil(
        lambda: "bands.in" in tree_names(window, window.explorer.proxy.index_for(bands)),
        timeout=5000,
    )
    reloaded(window, tree_show_files=False)
    assert window.explorer.proxy.dirs_only
    assert tree_names(window) == FOLDERS
    folder = window.explorer.proxy.index_for(demo_project / "03_bands")
    assert folder.isValid() and tree_names(window, folder) == []


def test_selecting_a_file_selects_its_folder_in_a_folders_only_tree(
    qtbot, main_window, demo_project
):
    window = main_window
    bands_in = demo_project / "03_bands" / "bands.in"
    window.explorer.select_path(bands_in)
    assert window.explorer.current_path() == bands_in.parent
    qtbot.waitUntil(lambda: window.files.folder == bands_in.parent, timeout=5000)
    # the file stays selectable in the grid: it is the one selected there
    qtbot.waitUntil(
        lambda: window.files.proxy.path(window.files.view.currentIndex()) == bands_in,
        timeout=5000,
    )


def test_selecting_a_file_of_the_root_selects_the_root(qtbot, main_window, demo_project):
    window = main_window
    loose = demo_project / "notas.txt"
    loose.write_text("x")
    window.explorer.select_path(demo_project / "03_bands")
    window.explorer.select_path(loose)
    assert window.explorer.current_path() is None  # the root is the tree's root, not a row
    qtbot.waitUntil(lambda: window.files.folder == demo_project, timeout=5000)


def test_the_panel_takes_the_ui_section(qapp, qtbot, demo_project):
    from qe_studio.ui.services import DetectionService
    from qe_studio.ui.theme.manager import ThemeManager

    theme = ThemeManager("dark")
    service = DetectionService()
    panel = ExplorerPanel(theme, service, demo_project, UiConfig(hidden_dirs=["04_*"]))
    qtbot.addWidget(panel)
    assert panel.proxy.dirs_only and panel.proxy.hidden_dirs == ["04_*"]
    panel.apply_config(Path(demo_project), UiConfig(tree_show_files=True))
    assert not panel.proxy.dirs_only
