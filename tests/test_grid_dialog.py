"""Spec 23 R3.3, R4: the "Grids" window."""

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from qe_studio.core.plotting.grid import GridCell, GridSpec, PlotRef
from qe_studio.ui.dialogs.grid_dialog import GRID_FULL


def plot(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)
    return window.current_plot()


@pytest.fixture
def two_plots(qtbot, main_window, demo_project):
    bands = plot(qtbot, main_window, demo_project / "03_bands")
    relax = plot(qtbot, main_window, demo_project / "01_relax")
    main_window.open_file(demo_project / "03_bands" / "bands.in")  # a text tab: never a choice
    return main_window, bands.session, relax.session


def open_dialog(qtbot, window):
    window.activity.grids.click()
    dialog = window.grids.dialog
    assert dialog is not None
    qtbot.waitExposed(dialog)
    return dialog


def test_the_choices_are_the_open_plot_tabs(qtbot, two_plots):
    window, bands, relax = two_plots
    dialog = open_dialog(qtbot, window)
    assert [c.ref for c in window.grids.choices()] == [bands.ref, relax.ref]
    combo = dialog.table.combo(0)
    assert [combo.itemData(i) for i in range(combo.count())] == [bands.ref, relax.ref]
    assert combo.itemText(0).startswith(bands.title) and "03_bands" in combo.itemText(0)
    # a new grid starts with one row of the open plots, one cell each
    assert (dialog.rows.value(), dialog.cols.value()) == (1, 2)
    assert dialog.spec().validate() == []
    assert [c.ref for c in dialog.spec().cells] == [bands.ref, relax.ref]


def test_one_window_at_a_time(qtbot, two_plots):
    window = two_plots[0]
    dialog = open_dialog(qtbot, window)
    window.grids.open()
    assert window.grids.dialog is dialog
    dialog.close()
    qtbot.waitUntil(lambda: window.grids.dialog is None, timeout=2000)


def test_positions_are_limited_to_the_grid(qtbot, two_plots):
    dialog = open_dialog(qtbot, two_plots[0])
    assert dialog.table.spin(0, 1).maximum() == 1 and dialog.table.spin(0, 2).maximum() == 2
    dialog.rows.setValue(3)
    assert dialog.table.spin(1, 1).maximum() == 3
    dialog.table.spin(1, 1).setValue(9)
    assert dialog.table.spin(1, 1).value() == 3


def test_errors_disable_generate(qtbot, two_plots):
    dialog = open_dialog(qtbot, two_plots[0])
    assert dialog.generate_button.isEnabled() and dialog.problem.isHidden()
    dialog.table.spin(1, 2).setValue(1)  # both cells at (1, 1)
    assert not dialog.generate_button.isEnabled() and not dialog.save_button.isEnabled()
    assert "mesma posição" in dialog.problem.text()
    dialog.table.spin(1, 2).setValue(2)
    dialog.name.setText("")
    assert not dialog.generate_button.isEnabled()
    assert dialog.problem.text() == "Dê um nome à grade."


def test_add_and_remove_cells(qtbot, two_plots):
    dialog = open_dialog(qtbot, two_plots[0])
    dialog.rows.setValue(2)
    dialog.add_button.click()
    cells = dialog.spec().cells
    assert len(cells) == 3 and (cells[2].row, cells[2].col) == (1, 0)  # the first free position
    dialog.table.selectRow(0)
    dialog.remove_button.click()
    assert len(dialog.spec().cells) == 2


def test_a_full_grid_has_no_room_for_a_new_cell(qtbot, two_plots):
    """1 x 2 with two cells: no free position, so no cell is made on top of another."""
    dialog = open_dialog(qtbot, two_plots[0])
    assert not dialog.add_button.isEnabled() and dialog.add_button.toolTip() == GRID_FULL
    dialog.table.add_cell()  # what the button would do: nothing
    assert len(dialog.spec().cells) == 2 and dialog.spec().validate() == []
    dialog.rows.setValue(2)
    assert dialog.add_button.isEnabled() and dialog.add_button.toolTip() == ""
    dialog.add_button.click()
    cells = dialog.spec().cells
    assert len(cells) == 3 and (cells[2].row, cells[2].col) == (1, 0)
    dialog.rows.setValue(2)
    dialog.cols.setValue(2)
    dialog.add_button.click()  # the last free position, (2, 2) in the table's numbering
    assert len(dialog.spec().cells) == 4 and not dialog.add_button.isEnabled()
    dialog.table.spin(3, 2).setValue(1)  # a cell moved away (it now overlaps another)
    assert dialog.table.has_free_position() and dialog.add_button.isEnabled()


def test_the_wheel_never_changes_a_cell(qtbot, two_plots):
    """The wheel over the table scrolls it: the spin boxes and the plot combo ignore it."""
    dialog = open_dialog(qtbot, two_plots[0])
    dialog.rows.setValue(3)
    spin, combo = dialog.table.spin(1, 1), dialog.table.combo(1)
    before = (spin.value(), combo.currentIndex())
    assert before == (1, 1) and spin.maximum() == 3 and combo.count() == 2
    for widget in (spin, combo):
        wheel = QWheelEvent(
            QPointF(4, 4),
            QPointF(4, 4),
            QPoint(0, 0),
            QPoint(0, 120),  # up: a spin box would take it to 2, the combo to its first plot
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(widget, wheel)
        assert not wheel.isAccepted()
    assert (spin.value(), combo.currentIndex()) == before


def test_loading_cells_validates_once(qtbot, two_plots):
    window, bands, _relax = two_plots
    dialog = open_dialog(qtbot, window)
    dialog.rows.setValue(3)
    changes = []
    dialog.table.changed.connect(lambda: changes.append(1))
    cells = [GridCell(r, c, bands.ref) for r, c in ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0))]
    dialog.table.set_cells(cells)
    assert len(changes) == 1 and len(dialog.spec().cells) == 5


def test_a_plot_opened_meanwhile_clears_the_stale_error(qtbot, main_window, demo_project):
    """No plot is open: a new cell has none to show, and the window says so. Opening one and
    coming back to the window fills the cell, and the message, Gerar and Salvar follow."""
    dialog = open_dialog(qtbot, main_window)
    dialog.add_button.click()
    assert "escolha um gráfico" in dialog.problem.text()
    assert not dialog.generate_button.isEnabled() and not dialog.save_button.isEnabled()
    plot(qtbot, main_window, demo_project / "03_bands")
    QApplication.sendEvent(dialog, QEvent(QEvent.Type.WindowActivate))
    assert dialog.table.combo(0).count() == 1 and dialog.table.cells()[0].ref is not None
    assert dialog.problem.isHidden() and dialog.problem.text() == ""
    assert dialog.generate_button.isEnabled() and dialog.save_button.isEnabled()


def test_save_and_open_round_trip(qtbot, two_plots, demo_project):
    window, bands, relax = two_plots
    dialog = open_dialog(qtbot, window)
    dialog.name.setText("Al")
    dialog.table.title_edit(1).setText("Relaxação")
    assert dialog.save()
    saved = dialog.spec()
    dialog.close()

    window.workspace.close_all()  # reopened with no plot open: the saved plots are offered
    dialog = open_dialog(qtbot, window)
    assert dialog.open_grid("Al")
    assert dialog.spec() == saved
    assert dialog.table.combo(0).currentText().startswith("Estrutura de bandas · 03_bands")


def test_a_gone_folder_is_marked_in_the_table(qtbot, two_plots, demo_project):
    window = two_plots[0]
    store = window.plot_workflow.stores.grids
    gone = PlotRef(demo_project / "99_gone", "bands")
    store.save(GridSpec("x", 1, 1, [GridCell(0, 0, gone)]))
    dialog = open_dialog(qtbot, window)
    dialog.open_grid("x")
    assert dialog.table.combo(0).currentText().endswith("(pasta não encontrada)")


def test_saving_over_another_grid_asks(qtbot, two_plots, monkeypatch):
    window = two_plots[0]
    dialog = open_dialog(qtbot, window)
    dialog.name.setText("Al")
    assert dialog.save()
    dialog.close()
    dialog = open_dialog(qtbot, window)
    dialog.name.setText("Al")
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: asked.append(a[2]) or QMessageBox.StandardButton.No
    )
    assert not dialog.save()
    assert asked and "Substituir" in asked[0]


def test_delete_asks_first(qtbot, two_plots, monkeypatch):
    window = two_plots[0]
    store = window.plot_workflow.stores.grids
    dialog = open_dialog(qtbot, window)
    dialog.name.setText("Al")
    dialog.save()
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "question", lambda *a: answers.pop(0))
    dialog.delete_button.click()
    assert store.names() == ["Al"]
    dialog.delete_button.click()
    assert store.names() == [] and not answers


def test_preview_shows_the_layout(qtbot, two_plots):
    dialog = open_dialog(qtbot, two_plots[0])
    assert dialog.preview.isHidden()
    dialog.preview_button.click()
    assert dialog.preview.isVisible()
    dialog.table.title_edit(0).setText("Primeira")
    assert dialog.preview.labels[0] == (0, 0, "Primeira")
    assert (dialog.preview.rows, dialog.preview.cols) == (1, 2)
    left, right = dialog.preview.cell_rect(0, 0), dialog.preview.cell_rect(0, 1)
    assert left.right() < right.left() and left.top() == right.top()
    dialog.preview.grab()  # paints without error


def test_the_table_header_is_not_a_black_bar(qtbot, two_plots):
    window = two_plots[0]
    dialog = open_dialog(qtbot, window)
    header = dialog.table.horizontalHeader()
    assert header is not None
    pixel = header.grab().toImage().pixelColor(2, 2)  # the padding of the first section
    assert pixel.rgb() == window.theme.color("chrome").rgb()
    assert pixel.rgb() != QColor("black").rgb()
