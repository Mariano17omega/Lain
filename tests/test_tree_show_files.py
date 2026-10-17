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


# -- the "Mostrar arquivos" button (spec 50 R1) ------------------------------------------------------


def test_the_files_button_sits_between_collapse_and_refresh(main_window):
    panel = main_window.explorer
    layout = panel.files_button.parent().buttons  # the PanelHeader's button row
    order = [
        layout.indexOf(button)
        for button in (panel.collapse_button, panel.files_button, panel.refresh_button)
    ]
    assert order == [order[0], order[0] + 1, order[0] + 2] and order[0] >= 0
    assert panel.files_button.isCheckable()


def test_the_button_starts_from_the_config(window_factory):
    for shown in (False, True):
        window = window_factory(ui={"tree_show_files": shown})
        assert window.explorer.files_button.isChecked() is shown
        assert window.explorer.proxy.dirs_only is (not shown)
        window.close()


def test_the_button_shows_and_hides_the_files(qtbot, main_window, demo_project):
    window = main_window
    bands = demo_project / "03_bands"
    window.explorer.select_path(bands)
    qtbot.waitUntil(lambda: window.files.folder == bands, timeout=5000)

    def listed() -> list[str]:
        return tree_names(window, window.explorer.proxy.index_for(bands))

    assert listed() == []
    window.explorer.files_button.click()
    assert not window.explorer.proxy.dirs_only
    qtbot.waitUntil(lambda: "bands.in" in listed(), timeout=5000)
    assert window.current_folder() == bands and window.files.folder == bands
    window.explorer.files_button.click()
    assert window.explorer.proxy.dirs_only and listed() == []
    assert window.current_folder() == bands and window.files.folder == bands


def test_hiding_the_files_keeps_the_folder_of_the_selected_file(
    qtbot, tree_files_window, demo_project
):
    window = tree_files_window
    bands = demo_project / "03_bands"
    bands_in = bands / "bands.in"
    window.explorer.select_path(bands)
    qtbot.waitUntil(
        lambda: "bands.in" in tree_names(window, window.explorer.proxy.index_for(bands)),
        timeout=5000,
    )
    window.explorer.select_path(bands_in)
    assert window.explorer.current_path() == bands_in
    qtbot.waitUntil(
        lambda: window.files.proxy.path(window.files.view.currentIndex()) == bands_in,
        timeout=5000,
    )

    told = []
    window.explorer.folder_selected.connect(told.append)
    window.explorer.file_selected.connect(told.append)
    window.explorer.files_button.click()  # hide the files: the row of bands.in goes

    assert window.explorer.current_path() == bands  # its folder takes the highlight, silently
    assert window.current_folder() == bands and told == []
    assert window.files.folder == bands
    assert window.files.proxy.path(window.files.view.currentIndex()) == bands_in  # still selected

    window.explorer.files_button.click()  # and back
    assert not window.explorer.proxy.dirs_only
    assert window.current_folder() == bands


def test_hiding_the_file_of_the_root_leaves_the_root(qtbot, tree_files_window, demo_project):
    window = tree_files_window
    loose = demo_project / "notas.txt"
    loose.write_text("x")
    qtbot.waitUntil(lambda: "notas.txt" in tree_names(window), timeout=5000)
    window.explorer.select_path(loose)
    assert window.explorer.current_path() == loose
    window.explorer.files_button.click()
    assert window.explorer.current_path() is None
    assert window.current_folder() == demo_project


def test_the_button_tooltip_follows_the_state(main_window):
    button = main_window.explorer.files_button
    assert button.toolTip() == "Mostrar arquivos na árvore"
    assert button.accessibleName() == "Mostrar arquivos na árvore"
    button.click()
    assert button.toolTip() == "Ocultar arquivos da árvore"
    button.click()
    assert button.toolTip() == "Mostrar arquivos na árvore"


def test_reloading_the_config_puts_the_button_back_without_toggling(main_window):
    window = main_window
    button = window.explorer.files_button
    button.click()  # the user turns the files on for this session
    assert button.isChecked() and not window.explorer.proxy.dirs_only

    toggles = []
    button.toggled.connect(toggles.append)
    reloaded(window, tree_show_files=False)  # the file says folders only
    assert not button.isChecked() and window.explorer.proxy.dirs_only
    assert button.toolTip() == "Mostrar arquivos na árvore"
    reloaded(window, tree_show_files=True)
    assert button.isChecked() and not window.explorer.proxy.dirs_only
    assert button.toolTip() == "Ocultar arquivos da árvore"
    assert toggles == []


def test_the_button_is_for_the_session_and_stores_nothing(main_window):
    window = main_window
    window.settings.sync()
    before = set(window.settings.allKeys())
    window.explorer.files_button.click()
    window.explorer.files_button.click()
    window.explorer.files_button.click()
    window.settings.sync()
    assert set(window.settings.allKeys()) == before
