"""Spec 22 in the window: "Bandas com DOS" in the grid's menu, its tab, settings and export."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QMessageBox, QPushButton

from grid_helpers import menu_texts, select_names, show_folder
from qe_studio.core.plotting.export import plan_export
from qe_studio.core.plotting.plot_file import read_plot_file
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
        "qe_studio.core.calculations.bands_dos.render.notes", lambda dataset: ("a note",)
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
    assert not (project / "04_pdos" / "bands_dos.plot").exists()

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
