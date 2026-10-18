"""Spec 22 in the window: "Bandas com DOS" in the grid's menu and from "Gerar Plot" with the two folders
selected, its tab, settings and export."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QMessageBox, QPushButton

from grid_helpers import menu_texts, select_names, show_folder
from qe_studio.core.plotting.export import plan_export
from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.ui.dialogs.overwrite import OverwriteChoice
from qe_studio.ui.widgets.plot_view import PlotView


@pytest.fixture
def menus(monkeypatch):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


@pytest.fixture
def project(qtbot, main_window, demo_project) -> Path:
    """The grid showing the project, its four folders detected."""
    show_folder(qtbot, main_window, demo_project, up=False)
    for folder in sorted(p for p in demo_project.iterdir() if p.is_dir()):
        main_window.service.detect_now(folder)
    return demo_project


def menu_of(window, menus, *names: str) -> QMenu:
    window._show_item_menu(select_names(window.files, *names), QPoint())
    return menus[-1]


def open_pair(qtbot, window, menus, *names: str):
    menu = menu_of(window, menus, *names)
    action = next(a for a in menu.actions() if a.text() == "Bandas com DOS")
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        action.trigger()
    return blocker.args[0]


def test_the_menu_offers_it_for_a_bands_and_a_pdos_folder(main_window, project, menus):
    assert menu_texts(menu_of(main_window, menus, "04_pdos", "03_bands")) == [
        "2 itens",
        "Abrir local de origem",
        "Copiar",
        "Bandas com DOS",
        "Adicionar aos favoritos",
    ]
    for names in (("01_relax", "04_pdos"), ("02_scf", "03_bands"), ("01_relax", "02_scf")):
        assert "Bandas com DOS" not in menu_texts(menu_of(main_window, menus, *names))
    three = menu_of(main_window, menus, "01_relax", "03_bands", "04_pdos")
    assert "Bandas com DOS" not in menu_texts(three)


def test_the_item_comes_once_detection_has_run(qtbot, main_window, project, menus):
    service = main_window.service
    service.invalidate()  # nothing cached: the menu asks for detection and goes without
    assert "Bandas com DOS" not in menu_texts(menu_of(main_window, menus, "03_bands", "04_pdos"))
    qtbot.waitUntil(
        lambda: all(service.peek_results(project / n) is not None for n in ("03_bands", "04_pdos")),
        timeout=10_000,
    )
    assert "Bandas com DOS" in menu_texts(menu_of(main_window, menus, "03_bands", "04_pdos"))


def test_the_figure_opens_in_one_tab(qtbot, main_window, project, menus):
    bands, pdos = project / "03_bands", project / "04_pdos"
    session = open_pair(qtbot, main_window, menus, "04_pdos", "03_bands")
    key = f"plot:bands_dos:{bands}|{pdos}"
    assert session.key == key and session.kind == "bands_dos"
    assert session.title == "Bandas + DOS — Al" and session.paths == (bands, pdos)
    workspace = main_window.workspace
    view = workspace.widget_for(key)
    assert isinstance(view, PlotView) and workspace.current() is view
    assert len(view.figure.axes) == 2
    body = main_window.params.body
    assert body.session is session
    assert "Remapear arquivos…" not in [b.text() for b in body.findChildren(QPushButton)]
    assert "DOS: 2 projeções" in body.readout.text()

    open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")  # again: the same tab
    plots = [w for _k, w in workspace.items() if isinstance(w, PlotView)]
    assert len(plots) == 1 and workspace.current() is workspace.widget_for(key)
    assert main_window.plot_workflow.plot_of(bands) is None  # not *the* plot of 03_bands


def test_render_notes_show_in_the_panel(qtbot, main_window, project, menus, monkeypatch):
    open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")
    body = main_window.params.body
    assert body.notes.isHidden()
    monkeypatch.setattr(
        "qe_studio.core.calculations.bands_dos.render.notes", lambda dataset, params: ("a note",)
    )
    view = main_window.current_plot()
    assert view is not None
    with qtbot.waitSignal(view.rendered):
        view.render()
    assert not body.notes.isHidden() and body.notes.text() == "⚠ a note"


def test_edits_are_saved_in_the_bands_folder_on_close(qtbot, main_window, project, menus):
    bands = project / "03_bands"
    session = open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")
    main_window.params.set_param("dos_width_ratio", 0.5)
    main_window.workspace.close_key(session.key)
    main_window.plot_settings.flush_now()
    values, warnings = read_plot_file(bands, "bands_dos")
    assert warnings == [] and values is not None
    assert values["dos_width_ratio"] == 0.5 and values["dos_folder"] == "../04_pdos"
    assert not (project / "04_pdos" / "plots" / "bands_dos.plot").exists()

    reopened = open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")
    assert reopened.params.dos_width_ratio == 0.5


def test_export_goes_to_the_bands_folder(qtbot, main_window, project, menus):
    bands = project / "03_bands"
    session = open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")
    session.params.export_svg = session.params.export_pdf = False
    with qtbot.waitSignal(main_window.export_finished, timeout=20_000) as blocker:
        assert main_window.export_plot()
    written = [
        bands / "plots" / "03_bands-bands_dos.png",
        bands / "plots" / "03_bands-bands_dos.csv",
    ]
    assert blocker.args[0] == written  # the DOS folder is not in the name: it is the bands' figure
    plan = plan_export(session, main_window.root)  # a second export would ask before overwriting
    assert plan.existing == written
    assert plan.new_stem == "03_bands-bands_dos_2"


def test_renaming_the_dos_folder_closes_the_figure(qtbot, main_window, project, menus, monkeypatch):
    session = open_pair(qtbot, main_window, menus, "03_bands", "04_pdos")
    monkeypatch.setattr("qe_studio.ui.rename_controller.ask_rename", lambda parent, path: "04_dos")
    main_window.rename_path(project / "04_pdos")
    assert main_window.workspace.widget_for(session.key) is None


def test_a_dos_folder_that_is_gone_is_reported(qtbot, main_window, project, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a[2])))
    with qtbot.waitSignal(main_window.plot_failed, timeout=10_000) as blocker:
        main_window.plot_workflow.plot_pair(project / "03_bands", project / "gone")
    assert blocker.args[0].startswith("Pasta da DOS não encontrada")
    assert warnings == [blocker.args[0]]


# -- "Gerar Plot" with a bands folder and a PDOS folder selected in the grid -----------------------------


def gerar_plot(qtbot, window):
    """Click the panel's "Gerar Plot"; the session it opened and the files it saved."""
    window.set_left_mode("params")
    with (  # ready is waited for first: the export is asked once the tab is shown
        qtbot.waitSignal(window.export_finished, timeout=20_000) as done,
        qtbot.waitSignal(window.plot_ready, timeout=10_000) as ready,
    ):
        window.params.generate_button.click()
    return ready.args[0], done.args[0]


def test_gerar_plot_makes_and_saves_the_figure_of_the_selected_pair(
    qtbot, main_window, project, monkeypatch
):
    asked = []
    monkeypatch.setattr(
        "qe_studio.ui.plot_export.ask_overwrite",
        lambda parent, existing, stem: asked.append(stem) or (OverwriteChoice.OVERWRITE, False),
    )
    bands, pdos = project / "03_bands", project / "04_pdos"
    select_names(main_window.files, "04_pdos", "03_bands")
    session, written = gerar_plot(qtbot, main_window)
    assert session.kind == "bands_dos" and session.paths == (bands, pdos)
    assert bands / "plots" / "03_bands-bands_dos.png" in written
    assert not (pdos / "plots").exists()
    assert "Detectando cálculo…" not in main_window.plot_workflow.busy.labels

    main_window.params.set_param("dos_width_ratio", 0.5)
    again, _written = gerar_plot(qtbot, main_window)  # the same tab, redrawn with its edits
    assert again.key == session.key and again.params.dos_width_ratio == 0.5
    plots = [w for _k, w in main_window.workspace.items() if isinstance(w, PlotView)]
    assert len(plots) == 1 and asked == ["03_bands-bands_dos_2"]


def test_gerar_plot_with_two_folders_that_make_no_pair_plots_the_selected_folder(
    qtbot, main_window, project, monkeypatch
):
    asked = []
    monkeypatch.setattr(main_window.plot_workflow, "generate", lambda folder: asked.append(folder))
    select_names(main_window.files, "01_relax", "02_scf")
    main_window.params.generate_button.click()
    qtbot.waitUntil(lambda: asked == [project], timeout=10_000)
    assert main_window.current_plot() is None


# -- the activity bar's "Plot" with a bands folder and a PDOS folder selected ---------------------------


def test_plot_makes_the_selected_pair_then_shows_it_without_saving_again(
    qtbot, main_window, project, monkeypatch
):
    asked = []
    monkeypatch.setattr(
        "qe_studio.ui.plot_export.ask_overwrite",
        lambda *args: asked.append(args) or (OverwriteChoice.CANCEL, False),
    )
    bands = project / "03_bands"
    select_names(main_window.files, "03_bands", "04_pdos")
    with (
        qtbot.waitSignal(main_window.export_finished, timeout=20_000) as done,
        qtbot.waitSignal(main_window.plot_ready, timeout=10_000) as ready,
    ):
        main_window.activity.generate.click()  # never plotted: plotted and saved
    session = ready.args[0]
    assert (
        session.kind == "bands_dos" and bands / "plots" / "03_bands-bands_dos.png" in done.args[0]
    )
    assert main_window.left.currentIndex() == 1  # the adjustments panel

    view = main_window.current_plot()
    main_window.open_file(bands / "bands.in")
    with qtbot.assertNotEmitted(main_window.plot_ready, wait=300):
        main_window.activity.generate.click()  # open: brought to front
    qtbot.waitUntil(lambda: main_window.current_plot() is view, timeout=5_000)

    main_window.workspace.close_key(session.key)
    with qtbot.waitSignal(main_window.plot_ready, timeout=10_000) as ready:
        main_window.activity.generate.click()  # plotted before: shown again, not saved
    assert ready.args[0].kind == "bands_dos" and asked == []
    assert "Detectando cálculo…" not in main_window.plot_workflow.busy.labels


def test_plot_with_auto_generation_off_opens_the_panel_and_gerar_plot_makes_the_pair(
    qtbot, window_factory, demo_project
):
    window = window_factory(ui={"auto_generate_plot": False})
    show_folder(qtbot, window, demo_project, up=False)
    select_names(window.files, "04_pdos", "03_bands")
    with qtbot.assertNotEmitted(window.plot_ready, wait=500):
        window.activity.generate.click()
    qtbot.waitUntil(lambda: window.left.currentIndex() == 1, timeout=5_000)
    assert window.current_plot() is None and not (demo_project / "03_bands" / "plots").exists()
    session, _written = gerar_plot(qtbot, window)
    assert session.kind == "bands_dos"


def test_plot_with_two_folders_that_make_no_pair_plots_the_selected_folder(
    qtbot, main_window, project, monkeypatch
):
    asked = []
    monkeypatch.setattr(
        main_window.plot_workflow, "generate", lambda folder, auto_export=True: asked.append(folder)
    )
    select_names(main_window.files, "01_relax", "02_scf")
    main_window.activity.generate.click()
    qtbot.waitUntil(lambda: asked == [project], timeout=10_000)
