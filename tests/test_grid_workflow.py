"""Spec 23 R3–R4 in the window: the "Grids" button, generating, reopening and renaming."""

import json
import shutil

from qe_studio.core.appdirs import data_dir
from qe_studio.core.plotting.plot_file import plot_file_path, write_plot_file
from qe_studio.ui.widgets.plot_view import PlotView


def plot(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)
    return window.current_plot()


def generate(qtbot, window, name="Al", saved=False):
    """Open the window, name the grid (or open the ``saved`` one) and press "Gerar"; its view."""
    window.grids.open()
    dialog = window.grids.dialog
    if saved:
        assert dialog.open_grid(name)
    else:
        dialog.name.setText(name)
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as ready:
        dialog.generate_button.click()
    assert window.grids.dialog is None or not dialog.isVisible()
    session = ready.args[0]
    view = window.workspace.widget_for(session.key)
    assert isinstance(view, PlotView)
    return view


def test_the_top_bar_and_the_palette_open_the_grids(qtbot, main_window):
    button = main_window.top_bar.grids
    assert button.text() == "Grids" and not button.isHidden()
    action = main_window._actions["grids.open"]
    assert action.text() == "Grids…"
    action.trigger()
    assert main_window.grids.dialog is not None
    rows = main_window.command_palette.rows_for(">grids")
    assert rows and rows[0].key == "action:grids.open"


def test_two_plots_make_a_grid_tab(qtbot, main_window, demo_project):
    bands = plot(qtbot, main_window, demo_project / "03_bands")
    relax = plot(qtbot, main_window, demo_project / "01_relax")
    bands.session.params.emin = -2.0  # an edit not saved yet: the grid takes the plot as it is
    view = generate(qtbot, main_window)
    grid = view.session
    assert grid.key == "plot:grid:Al" and main_window.workspace.current() is view
    cells = [data.session for data in grid.dataset.cells]
    assert [c.ref for c in cells] == [bands.session.ref, relax.session.ref]
    assert cells[0] is not bands.session and cells[0].params.emin == -2.0
    assert len(view.figure.axes) == 3  # bands + the two relax panels
    assert main_window.params.session is grid
    assert grid.dataset.spec.name in main_window.plot_workflow.stores.grids.names()  # Gerar saves


def test_a_saved_grid_reloads_its_plots_from_their_plot_files(qtbot, main_window, demo_project):
    bands = plot(qtbot, main_window, demo_project / "03_bands")
    plot(qtbot, main_window, demo_project / "01_relax")
    generate(qtbot, main_window)
    main_window.workspace.close_all()
    params = bands.session.params
    params.emin = -1.5
    write_plot_file(demo_project / "03_bands", "bands", params)

    view = generate(qtbot, main_window, saved=True)  # no plot open: both load from their folders
    cells = [data.session for data in view.session.dataset.cells]
    assert all(cell is not None for cell in cells)
    assert cells[0].params.emin == -1.5
    assert main_window.status.spinner.isHidden()


def test_a_cell_of_a_gone_folder_is_unavailable(qtbot, main_window, demo_project):
    plot(qtbot, main_window, demo_project / "03_bands")
    plot(qtbot, main_window, demo_project / "01_relax")
    generate(qtbot, main_window)
    main_window.workspace.close_all()
    shutil.rmtree(demo_project / "01_relax")
    view = generate(qtbot, main_window, saved=True)
    failed = view.session.dataset.cells[1]
    assert failed.session is None and failed.error.startswith("Pasta não encontrada")
    assert (
        view.session.info.notes
        and "Plot indisponível" in view.figure.subfigs[1].texts[0].get_text()
    )


def test_grid_settings_go_to_the_store_not_to_a_plot_file(qtbot, main_window, demo_project):
    plot(qtbot, main_window, demo_project / "03_bands")
    view = generate(qtbot, main_window)
    main_window.params.set_param("cell_width", 4.0)
    assert view.session.params.figure_size[0] == 4.0
    main_window.plot_settings.flush_now()
    assert not plot_file_path(demo_project, "grid").exists()
    saved = json.loads((data_dir() / "grids.json").read_text())
    assert saved["grids"]["Al"]["params"]["cell_width"] == 4.0
    main_window.workspace.close_all()
    assert generate(qtbot, main_window, saved=True).session.params.cell_width == 4.0


def test_renaming_a_folder_follows_it_and_closes_the_grid(
    qtbot, main_window, demo_project, monkeypatch
):
    plot(qtbot, main_window, demo_project / "03_bands")
    view = generate(qtbot, main_window)
    monkeypatch.setattr("qe_studio.ui.rename_controller.ask_rename", lambda *_a: "03_bandas")
    main_window.rename_path(demo_project / "03_bands")
    assert main_window.workspace.widget_for(view.session.key) is None
    spec = main_window.plot_workflow.stores.grids.get("Al")
    assert spec.cells[0].ref.path == demo_project / "03_bandas"


def test_the_grid_exports_into_the_project_plots(qtbot, main_window, demo_project):
    plot(qtbot, main_window, demo_project / "03_bands")
    generate(qtbot, main_window)
    main_window.params.set_param("export_svg", False)
    main_window.params.set_param("export_pdf", False)
    with qtbot.waitSignal(main_window.export_finished, timeout=20_000) as done:
        assert main_window.export_plot()
    assert done.args[0] == [demo_project / "plots" / "grid_Al.png"]
