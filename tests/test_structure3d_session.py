"""Spec 47 R2–R4: a 3D window opens with the view saved in its folder's ``view3d.plot`` and, when closed,
saves it there, a section per file, only when the user changed something. Every folder is a copy in
``demo_project`` (``tmp_path``): never a fixture."""

import os
import shutil

import numpy as np
import pytest
import yaml
from PyQt6 import sip
from PyQt6.QtCore import Qt

from qe_studio.core.file_ops import rename_item
from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.core.structure3d.camera import frame_from
from structure3d_helpers import (
    SI_SCF,
    SLAB_2X1,
    Windows,
    camera_state,
    click_atom,
    clickable_atoms,
    same_camera,
    wheel,
)
from test_structure3d_ui import open_from_menu

from conftest import FIXTURES

NAME = "si.scf.in"
ROTATION = frame_from(np.array([1.0, -0.5, 0.3]), np.array([0.0, 0.0, 1.0]))
ISOMETRIC = frame_from(np.array([1.0, 1.0, 1.0]), np.array([0.0, 0.0, 1.0]))
SAVED = {
    "options": {
        "radius_scale": 1.5,
        "style": "fio",
        "species_colors": {"Si": "#ff00ff"},
        "show_abc": False,
        "label_size": 16,
    },
    "camera": {"rotation": ROTATION.tolist(), "zoom": 33.0, "pan": [10.0, -5.0], "focal": 30.0},
}
GONE = "A pasta 05_si não existe mais: a vista de si.scf.in não foi salva em view3d.plot."
NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes anywhere"
)


@pytest.fixture
def si_folder(demo_project):
    folder = demo_project / "05_si"
    shutil.copytree(FIXTURES / "si_bands", folder)
    return folder


@pytest.fixture
def window(main_window):
    """The main window; the 3D windows a test leaves open are closed at the end."""
    yield main_window
    main_window.structure3d.close_dialog()


@pytest.fixture
def toasts(main_window, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window.toast, "show_message", lambda *args: shown.append(args))
    return shown


@pytest.fixture
def restore_yes(monkeypatch):
    answers = []

    def ask(parent):
        answers.append(parent)
        return True

    monkeypatch.setattr("qe_studio.ui.widgets.structure3d.panel.ask_restore", ask)
    return answers


def open_view(qtbot, main_window, path):
    controller = main_window.structure3d
    with qtbot.waitSignal(controller.opened, timeout=10_000) as blocker:
        controller.open(path)
    view = blocker.args[0]
    qtbot.waitExposed(view)
    view.canvas.grab()  # the first frame: framed now, unless a camera was restored
    return view


def write_view(folder, sections) -> None:
    data = {"lain_plot": 1, "kind": "view3d", "params": sections}
    (folder / "view3d.plot").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def sections_of(folder) -> dict:
    sections, warnings = read_plot_file(folder, "view3d")
    assert warnings == []
    assert sections is not None
    return sections


def stamp(path):
    return path.read_bytes(), path.stat().st_mtime_ns


def restore_defaults(view) -> None:
    view.panel.restore_button.click()


# -- R2: opening restores ------------------------------------------------------------------------------


def test_the_saved_view_is_restored_without_framing_again(qtbot, window, si_folder, monkeypatch):
    write_view(si_folder, {NAME: SAVED})
    window.service.detect_now(si_folder)
    view = open_from_menu(qtbot, window, monkeypatch, si_folder / NAME)
    qtbot.waitExposed(view)
    view.canvas.grab()
    o, panel = view.canvas.options, view.panel
    assert (o.radius_scale, o.style, o.show_abc, o.label_size) == (1.5, "fio", False, 16)
    assert o.species_colors == {0: (255, 0, 255)}
    assert panel.radius.value() == 1.5 and panel.style_choice.currentData() == "fio"
    assert not panel.show_abc.isChecked() and not panel.abc_width.isEnabled()
    assert panel.label_size.value() == 16 and panel.swatches[0].color == "#ff00ff"
    camera = view.canvas.camera
    assert (camera.zoom, camera.focal) == (33.0, 30.0)
    np.testing.assert_allclose(camera.pan, [10.0, -5.0])
    np.testing.assert_allclose(camera.rotation, ROTATION, atol=1e-12)
    assert not view.canvas.dirty


def test_without_a_file_the_defaults_and_the_theme(qtbot, window, si_folder, toasts):
    view = open_view(qtbot, window, si_folder / NAME)
    assert view.canvas.options.radius_scale == 1.0
    assert view.canvas.options.background == "escuro"
    np.testing.assert_allclose(view.canvas.camera.rotation, ISOMETRIC, atol=1e-12)
    assert toasts == []


def test_a_saved_background_wins_over_the_theme(qtbot, window, si_folder):
    write_view(si_folder, {NAME: {"options": {"background": "claro"}}})
    view = open_view(qtbot, window, si_folder / NAME)
    assert window.theme.name == "dark"
    assert view.canvas.options.background == "claro"
    assert view.panel.background.currentData() == "claro"
    np.testing.assert_allclose(view.canvas.camera.rotation, ISOMETRIC, atol=1e-12)  # no camera


def test_an_unreadable_file_gives_a_toast_and_the_defaults(qtbot, window, si_folder, toasts):
    (si_folder / "view3d.plot").write_text("params: [unclosed", encoding="utf-8")
    view = open_view(qtbot, window, si_folder / NAME)
    assert toasts == [("view3d.plot inválido; usando ajustes padrão.", "warning")]
    assert view.canvas.options.radius_scale == 1.0


def test_one_bad_field_is_ignored_and_the_rest_holds(qtbot, window, si_folder, toasts):
    write_view(si_folder, {NAME: {"options": {"radius_scale": 99, "style": "fio"}}})
    view = open_view(qtbot, window, si_folder / NAME)
    assert (view.canvas.options.radius_scale, view.canvas.options.style) == (1.0, "fio")
    assert toasts == []


def test_the_section_of_another_file_is_not_this_ones(qtbot, window, si_folder):
    write_view(si_folder, {"outro.in": SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    assert view.canvas.options.radius_scale == 1.0
    assert view.canvas.camera.zoom != 33.0


# -- R3: closing saves what the user changed -----------------------------------------------------------


def test_a_changed_view_is_saved_on_close_and_restored(qtbot, window, si_folder):
    view = open_view(qtbot, window, si_folder / NAME)
    panel = view.panel
    panel.radius.setValue(1.75)
    panel.style_choice.setCurrentIndex(panel.style_choice.findData("vareta"))
    panel.swatches[0].color_changed.emit("#00ff00")
    wheel(view.canvas, 2)
    panel.rotation.buttons["x+"].click()
    camera = camera_state(view.canvas)
    view.close()

    saved = sections_of(si_folder)[NAME]
    assert saved["options"]["radius_scale"] == 1.75 and saved["options"]["style"] == "vareta"
    assert saved["options"]["species_colors"] == {"Si": "#00ff00"}
    assert saved["camera"]["zoom"] == pytest.approx(camera[0])

    again = open_view(qtbot, window, si_folder / NAME)
    assert again.canvas.options.radius_scale == 1.75 and again.canvas.options.style == "vareta"
    assert again.canvas.options.species_colors == {0: (0, 255, 0)}
    assert again.panel.radius.value() == 1.75 and again.panel.swatches[0].color == "#00ff00"
    assert same_camera(camera_state(again.canvas), camera)


def test_open_and_close_without_a_change_writes_nothing(qtbot, window, si_folder):
    open_view(qtbot, window, si_folder / NAME).close()
    assert not (si_folder / "view3d.plot").exists()


def test_clicks_and_measures_are_no_change(qtbot, window, si_folder):
    slab = si_folder / "slab.in"  # Si2 seen along (1, 1, 1) shows one atom over the other
    shutil.copy(SLAB_2X1, slab)
    view = open_view(qtbot, window, slab)
    a, b = clickable_atoms(view.canvas, 2)
    view.panel.measures.buttons["distancia"].click()
    for ref in (a, b):
        click_atom(qtbot, view.canvas, ref)
    assert len(view.panel.measures.tables["distancia"].texts()) == 1
    assert view.canvas.current is not None and not view.canvas.dirty
    view.close()
    assert not (si_folder / "view3d.plot").exists()


def test_an_untouched_saved_view_leaves_the_file_as_it_was(qtbot, window, si_folder):
    write_view(si_folder, {NAME: SAVED})
    before = stamp(si_folder / "view3d.plot")
    open_view(qtbot, window, si_folder / NAME).close()
    assert stamp(si_folder / "view3d.plot") == before


@pytest.mark.parametrize("how", ["key", "button"])
def test_resetting_the_view_is_a_change(qtbot, window, si_folder, how):
    write_view(si_folder, {NAME: SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    if how == "key":
        qtbot.keyClick(view.canvas, Qt.Key.Key_R)
    else:
        view.reset_button.click()
    view.close()
    camera = sections_of(si_folder)[NAME]["camera"]
    np.testing.assert_allclose(camera["rotation"], ISOMETRIC, atol=1e-12)
    assert camera["zoom"] != 33.0
    assert (
        sections_of(si_folder)[NAME]["options"]["radius_scale"] == 1.5
    )  # the options as they were


def test_opening_a_section_of_the_panel_is_no_change(qtbot, window, si_folder):
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.sections["Célula"].header.click()
    assert view.panel.sections["Célula"].header.isChecked()
    view.close()
    assert not (si_folder / "view3d.plot").exists()


def test_a_folder_renamed_while_open_is_not_created_again(qtbot, window, si_folder, toasts):
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.radius.setValue(1.75)
    renamed = rename_item(si_folder, "06_si")
    view.close()
    assert toasts == [(GONE, "warning")]
    assert not si_folder.exists()
    assert not (renamed / "view3d.plot").exists()


@NOT_ROOT
def test_a_folder_without_write_permission_gives_a_toast(qtbot, window, si_folder, toasts):
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.radius.setValue(1.75)
    si_folder.chmod(0o500)
    try:
        view.close()
    finally:
        si_folder.chmod(0o700)
    assert len(toasts) == 1 and toasts[0][1] == "warning"
    assert toasts[0][0].startswith(f"Não foi possível salvar view3d.plot em {si_folder}: ")
    assert sip.isdeleted(view) or not view.isVisible()
    assert window.structure3d.windows == []
    assert not (si_folder / "view3d.plot").exists()


def test_closing_the_main_window_saves_a_changed_view(qtbot, main_window, si_folder):
    view = open_view(qtbot, main_window, si_folder / NAME)
    view.panel.radius.setValue(2.0)
    main_window.close()
    assert sections_of(si_folder)[NAME]["options"]["radius_scale"] == 2.0


def test_a_window_without_the_controller_writes_nothing_into_the_fixtures(qtbot):
    windows = Windows(qtbot)
    try:
        view = windows.open(SI_SCF)
        view.panel.radius.setValue(1.75)
        assert view.canvas.dirty
    finally:
        windows.close_all()
    assert not (FIXTURES / "si_bands" / "view3d.plot").exists()


# -- R3.5: "Restaurar padrões" removes the section on close --------------------------------------------


def test_restoring_and_closing_removes_the_section(qtbot, window, si_folder, restore_yes):
    write_view(si_folder, {NAME: SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    restore_defaults(view)
    assert restore_yes and view.canvas.restored and not view.canvas.dirty
    assert (si_folder / "view3d.plot").exists()  # removed on close, not on the click
    view.close()
    assert not (si_folder / "view3d.plot").exists()  # it was the only section
    again = open_view(qtbot, window, si_folder / NAME)
    assert again.canvas.options.radius_scale == 1.0
    np.testing.assert_allclose(again.canvas.camera.rotation, ISOMETRIC, atol=1e-12)


def test_restoring_removes_only_the_section_of_its_file(qtbot, window, si_folder, restore_yes):
    shutil.copy(si_folder / NAME, si_folder / "si.scf2.in")
    other = {"options": {"radius_scale": 0.5}}
    write_view(si_folder, {NAME: SAVED, "si.scf2.in": other})
    view = open_view(qtbot, window, si_folder / NAME)
    restore_defaults(view)
    view.close()
    assert sections_of(si_folder) == {"si.scf2.in": other}


def test_restoring_then_changing_saves_the_new_view(qtbot, window, si_folder, restore_yes):
    write_view(si_folder, {NAME: SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    restore_defaults(view)
    view.panel.radius.setValue(1.75)
    view.close()
    saved = sections_of(si_folder)[NAME]
    assert saved["options"]["radius_scale"] == 1.75
    assert saved["options"]["style"] == "bola-vareta" and saved["options"]["species_colors"] == {}
    np.testing.assert_allclose(saved["camera"]["rotation"], ISOMETRIC, atol=1e-12)


def test_restoring_a_window_without_a_file_creates_nothing(qtbot, window, si_folder, restore_yes):
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.radius.setValue(1.75)
    restore_defaults(view)
    view.close()
    assert not (si_folder / "view3d.plot").exists()


def test_restoring_answered_no_leaves_the_file(qtbot, window, si_folder, monkeypatch):
    monkeypatch.setattr("qe_studio.ui.widgets.structure3d.panel.ask_restore", lambda parent: False)
    write_view(si_folder, {NAME: SAVED})
    before = stamp(si_folder / "view3d.plot")
    view = open_view(qtbot, window, si_folder / NAME)
    restore_defaults(view)
    assert not view.canvas.restored
    view.close()
    assert stamp(si_folder / "view3d.plot") == before


def test_restoring_in_a_renamed_folder_creates_nothing(
    qtbot, window, si_folder, restore_yes, toasts
):
    write_view(si_folder, {NAME: SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    restore_defaults(view)
    renamed = rename_item(si_folder, "06_si")
    before = stamp(renamed / "view3d.plot")
    view.close()
    assert not si_folder.exists()
    assert stamp(renamed / "view3d.plot") == before
    assert toasts == []


# -- R4: a section per file ----------------------------------------------------------------------------


def test_two_inputs_of_one_folder_keep_their_own_views(qtbot, window, si_folder):
    second = si_folder / "si.scf2.in"
    shutil.copy(si_folder / NAME, second)
    cameras = {}
    for path, radius, color, steps in (
        (si_folder / NAME, 1.5, "#ff0000", 2),
        (second, 0.5, "#0000ff", -2),
    ):
        view = open_view(qtbot, window, path)
        view.panel.radius.setValue(radius)
        view.panel.swatches[0].color_changed.emit(color)
        wheel(view.canvas, steps)
        cameras[path.name] = camera_state(view.canvas)
        view.close()
    assert list(sections_of(si_folder)) == [NAME, "si.scf2.in"]

    for path, radius, rgb in ((si_folder / NAME, 1.5, (255, 0, 0)), (second, 0.5, (0, 0, 255))):
        view = open_view(qtbot, window, path)
        assert view.canvas.options.radius_scale == radius
        assert view.canvas.options.species_colors == {0: rgb}
        assert same_camera(camera_state(view.canvas), cameras[path.name])
        view.close()  # untouched: nothing written

    kept = sections_of(si_folder)["si.scf2.in"]
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.radius.setValue(2.0)
    view.close()
    assert sections_of(si_folder)["si.scf2.in"] == kept
    assert sections_of(si_folder)[NAME]["options"]["radius_scale"] == 2.0


def test_the_same_name_in_another_folder_has_no_section(qtbot, window, si_folder, demo_project):
    write_view(si_folder, {NAME: SAVED})
    other = demo_project / "06_si"
    shutil.copytree(FIXTURES / "si_bands", other)
    view = open_view(qtbot, window, other / NAME)
    assert view.canvas.options.radius_scale == 1.0
    view.panel.radius.setValue(0.5)
    view.close()
    assert sections_of(other)[NAME]["options"]["radius_scale"] == 0.5
    assert sections_of(si_folder) == {NAME: SAVED}


def test_a_name_with_a_space_and_an_accent_makes_the_round_trip(qtbot, window, si_folder):
    path = si_folder / "cálculo 2.in"
    shutil.copy(si_folder / NAME, path)
    view = open_view(qtbot, window, path)
    view.panel.radius.setValue(1.75)
    view.close()
    assert list(sections_of(si_folder)) == ["cálculo 2.in"]
    assert open_view(qtbot, window, path).canvas.options.radius_scale == 1.75


def test_the_section_of_a_file_that_is_gone_stays(qtbot, window, si_folder):
    write_view(si_folder, {"apagado.in": SAVED})
    view = open_view(qtbot, window, si_folder / NAME)
    view.panel.radius.setValue(1.75)
    view.close()
    assert list(sections_of(si_folder)) == ["apagado.in", NAME]
    assert sections_of(si_folder)["apagado.in"] == SAVED
