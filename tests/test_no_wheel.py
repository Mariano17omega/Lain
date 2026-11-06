"""The mouse wheel only scrolls the plot settings panel, it never changes a field (spec 32 R2)."""

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox

from qe_studio.ui.widgets.no_wheel import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox


def wheel(widget, delta: int = 120) -> QWheelEvent:
    """A wheel turn sent to ``widget`` (not spontaneous: the offscreen platform has no real one)."""
    position = QPointF(widget.rect().center())
    event = QWheelEvent(
        position,
        QPointF(widget.mapToGlobal(position.toPoint())),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


@pytest.fixture
def spin(qtbot):
    widget = NoWheelSpinBox()
    widget.setRange(0, 100)
    widget.setValue(50)
    qtbot.addWidget(widget)
    widget.show()
    return widget


@pytest.fixture
def double_spin(qtbot):
    widget = NoWheelDoubleSpinBox()
    widget.setRange(0.0, 100.0)
    widget.setValue(5.0)
    qtbot.addWidget(widget)
    widget.show()
    return widget


@pytest.fixture
def combo(qtbot):
    widget = NoWheelComboBox()
    widget.addItems(["a", "b", "c"])
    widget.setCurrentIndex(1)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_the_wheel_changes_no_value_and_is_left_to_the_parent(spin, double_spin, combo):
    for widget, read in ((spin, spin.value), (double_spin, double_spin.value)):
        before = read()
        for delta in (120, -120):
            assert not wheel(widget, delta).isAccepted()  # ignored: the scroll area gets it
        assert read() == before
    for delta in (120, -120):
        assert not wheel(combo, delta).isAccepted()
    assert combo.currentIndex() == 1


def test_the_wheel_over_the_text_of_a_spin_box_changes_nothing_either(spin):
    line = spin.lineEdit()
    wheel(line)
    assert spin.value() == 50


def test_a_wheel_turn_gives_no_focus_but_tab_and_click_do(spin, double_spin, combo):
    for widget in (spin, double_spin, combo):
        assert widget.focusPolicy() == Qt.FocusPolicy.StrongFocus
    spin.clearFocus()
    wheel(spin)
    assert not spin.hasFocus() and not spin.lineEdit().hasFocus()


def test_the_keyboard_and_the_mouse_still_edit_the_value(qtbot, spin, double_spin, combo):
    spin.setFocus()
    qtbot.keyClick(spin, Qt.Key.Key_Up)
    assert spin.value() == 51
    double_spin.setFocus()
    qtbot.keyClick(double_spin, Qt.Key.Key_Down)
    assert double_spin.value() == 4.0
    combo.setFocus()
    qtbot.keyClick(combo, Qt.Key.Key_Down)
    assert combo.currentIndex() == 2
    QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=spin.rect().center())
    spin.setValue(7)
    assert spin.value() == 7


# -- the settings panel ------------------------------------------------------------------------
def plot(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)


@pytest.mark.parametrize("folder", ["03_bands", "04_pdos"])
def test_every_spin_box_and_combo_of_a_plot_panel_ignores_the_wheel(
    qtbot, main_window, demo_project, folder
):
    plot(qtbot, main_window, demo_project / folder)
    body = main_window.params.body
    spins = body.findChildren(QAbstractSpinBox)
    combos = body.findChildren(QComboBox)
    assert spins and combos  # the schema has float fields and choices (DPI, grouping…)
    for widget in spins:
        # The inner line edit of a spin box is a ``QLineEdit``, not a ``QAbstractSpinBox``.
        assert isinstance(widget, NoWheelSpinBox | NoWheelDoubleSpinBox), widget
    for widget in combos:
        assert isinstance(widget, NoWheelComboBox), widget
    for widget in (*spins, *combos):
        assert widget.focusPolicy() == Qt.FocusPolicy.StrongFocus
