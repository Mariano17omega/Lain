"""Spec 81 R3: "Visualizar 3D" of the "Criar cálculo" window, one 3D window of the structures being created
that follows the dialog's step and plan and closes with it."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6 import sip

from fragment_helpers import SMALL
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog, setup_page
from qe_studio.ui.dialogs.calc_create import structure_preview as preview_module
from qe_studio.ui.dialogs.calc_create.setup_page import CHOOSE_SCF
from qe_studio.ui.theme.manager import ThemeManager
from structure3d_helpers import camera_state, same_camera

from calc_dialog_helpers import fill_setup, pick_scf, to_files
from calc_helpers import AL_SCF, JOBS, SI_SCF
from surface_helpers import MOLECULE, SUPERCELL_001

SURFACE = "SCF base (scf-kaolinite-slab-001-2x1x1.in)"
COMPLEX = "Molécula na superfície (relax_kaolinite-slab-001-2x1x1.in)"


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    return folder


@pytest.fixture
def dialog(qtbot, place, monkeypatch):
    """A window on ``place``, closed at teardown unless the test closed (deleted) it."""
    warnings: list[str] = []
    monkeypatch.setattr(preview_module, "warn_failed", lambda parent, text: warnings.append(text))
    window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS)
    window.set_mode("avancado")
    window.show()
    window.warnings = warnings  # type: ignore[attr-defined]
    yield window
    if not sip.isdeleted(window):
        window.preview.close()
        window._close_confirmed = True
        window.close()


def open_preview(qtbot, dialog):
    """Click "Visualizar 3D" and wait for the window's structures."""
    assert dialog.view_button.isEnabled(), dialog.view_button.toolTip()
    with qtbot.waitSignal(dialog.preview.shown, timeout=10_000):
        dialog.view_button.click()
    window = dialog.preview.window
    assert window is not None
    return window


def choices(window) -> list[str]:
    combo = window.choice_combo
    return [combo.itemText(index) for index in range(combo.count())]


def complex_ready(qtbot, dialog, monkeypatch):
    """Step 2 of a molecule on a surface with the molecule, site 43 and the H removed."""
    monkeypatch.setattr(setup_page, "choose_scf", lambda parent, start: MOLECULE)
    tabs = to_files(qtbot, dialog, "adsorption", scf=SUPERCELL_001, suffix="kao")
    field = tabs.widget_of("molecule")
    with qtbot.waitSignal(field.changed, timeout=10_000):
        field.choose_button.click()
    tabs.widget_of("site").checks[43].click()
    tabs.widget_of("remove_h").click()
    assert dialog.create_button.isEnabled(), dialog.create_button.toolTip()
    return tabs


def test_the_button_sits_left_of_cancel_and_waits_for_a_scf(qtbot, dialog):
    layout = dialog.cancel_button.parentWidget().layout()
    row = next(
        layout.itemAt(i).layout()
        for i in range(layout.count())
        if layout.itemAt(i).layout() is not None
        and layout.itemAt(i).layout().indexOf(dialog.cancel_button) >= 0
    )
    assert row.indexOf(dialog.view_button) == row.indexOf(dialog.cancel_button) - 1
    assert dialog.view_button.text() == "Visualizar 3D"
    assert not dialog.view_button.isEnabled() and dialog.view_button.toolTip() == CHOOSE_SCF
    dialog.setup.set_type("bandas")
    pick_scf(qtbot, dialog, AL_SCF)
    assert dialog.view_button.isEnabled()


def test_bands_shows_the_scf_and_a_second_click_raises_it(qtbot, dialog):
    fill_setup(qtbot, dialog, "bandas")
    window = open_preview(qtbot, dialog)
    assert str(window.structure.source.path) == str(AL_SCF) and len(window.structure) == 1
    assert window.choice_combo.isHidden() and choices(window) == ["SCF base (al.scf.in)"]
    assert window.print_button.isEnabled()  # the SCF is a file: its plots/ is next to it
    with qtbot.waitSignal(dialog.preview.shown, timeout=10_000):
        dialog.continue_button.click()  # step 2: the bands input has the SCF's structure
    assert choices(window) == ["SCF base (al.scf.in)"] and window.choice_combo.isHidden()
    dialog.view_button.click()
    assert dialog.preview.window is window  # one window per dialog


def test_the_complex_follows_the_fields(qtbot, dialog, monkeypatch):
    tabs = complex_ready(qtbot, dialog, monkeypatch)
    window = open_preview(qtbot, dialog)
    assert choices(window) == [SURFACE, COMPLEX] and window.choice_combo.currentIndex() == 1
    assert not window.choice_combo.isHidden()
    canvas = window.canvas
    assert len(canvas.structure) == 72 and canvas.structure.source.path is None
    assert not window.print_button.isEnabled()  # not written yet
    assert window.windowTitle() == "relax_kaolinite-slab-001-2x1x1.in · Visualização 3D"
    canvas.rotate_structure("y")
    turned, before = camera_state(canvas), canvas.structure.cart
    edit = tabs.widget_of("ads_distance")
    edit.clear()
    qtbot.keyClicks(edit, "3.0")
    qtbot.waitUntil(lambda: not np.allclose(canvas.structure.cart, before), timeout=10_000)
    after = canvas.structure.cart
    moved = np.flatnonzero(np.linalg.norm(after - before, axis=1) > 1e-6)
    assert moved.size and moved.min() >= 60  # the molecule's atoms, at the end
    shift = after[moved] - before[moved]
    assert np.allclose(shift, shift[0], atol=1e-6)  # rigidly
    assert np.linalg.norm(shift[0]) == pytest.approx(1.0, abs=1e-6)  # 2.0 → 3.0 Å
    assert same_camera(camera_state(canvas), turned)  # the same cell: the view stays


def test_the_choice_of_the_user_stays_while_listed(qtbot, dialog, monkeypatch):
    tabs = complex_ready(qtbot, dialog, monkeypatch)
    window = open_preview(qtbot, dialog)
    combo = window.choice_combo
    combo.setCurrentIndex(0)
    combo.activated.emit(0)
    assert len(window.structure) == 68 and window.print_button.isEnabled()
    with qtbot.waitSignal(dialog.preview.shown, timeout=10_000):
        tabs.widget_of("ads_distance").setText("2.5")
        tabs.flush()
    assert combo.currentIndex() == 0 and len(window.structure) == 68


def test_a_charge_difference_lists_three(qtbot, dialog, place):
    scf = place / "scf.in"
    scf.write_text(SMALL)
    tabs = to_files(qtbot, dialog, "charge_diff", scf=scf, suffix="ilita")
    atoms = tabs.widget_of("atoms")
    atoms.checks[5].click()
    atoms.checks[6].click()
    window = open_preview(qtbot, dialog)
    assert choices(window) == [
        "SCF base (scf.in)",
        "SCF clean (scf_ilita_clean.in)",
        "SCF isolated (scf_ilita_isolated.in)",
    ]
    combo = window.choice_combo
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    assert window.structure.labels == ("Fe", "Fe", "O", "O")


def test_an_adsorption_energy_lists_its_scfs_on_step_1(qtbot, dialog):
    fill_setup(qtbot, dialog, "ads_energy")
    window = open_preview(qtbot, dialog)
    assert choices(window) == ["al.scf.in", "si.scf.in"] and window.choice_combo.currentIndex() == 0
    combo = window.choice_combo
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    assert str(window.structure.source.path) == str(SI_SCF)


def test_closing_the_dialog_closes_the_window_and_writes_nothing(qtbot, dialog, place):
    fill_setup(qtbot, dialog, "bandas")
    window = open_preview(qtbot, dialog)
    window.canvas.rotate_structure("x")  # a change a 3D window of a file would save
    dialog.reject()
    qtbot.waitUntil(lambda: sip.isdeleted(window), timeout=5_000)
    assert dialog.preview.window is None
    assert not list(place.parent.rglob("view3d.plot"))
    assert not (AL_SCF.parent / "view3d.plot").exists()


def test_closing_the_window_lets_the_button_open_another(qtbot, dialog):
    fill_setup(qtbot, dialog, "bandas")
    first = open_preview(qtbot, dialog)
    first.close()
    assert dialog.preview.window is None
    second = open_preview(qtbot, dialog)
    assert second is not first and dialog.warnings == []
