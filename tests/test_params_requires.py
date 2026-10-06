"""A field that needs another one on (``ParamField.requires``) is disabled in the panel while it
is off, and says what to turn on: the gap in the legend needs the legend."""

import shutil

import pytest
from PyQt6.QtWidgets import QCheckBox

from qe_studio.core.calculations.bands.gap import NO_GAP_NOTE
from test_plot_workflow_unit import rig  # noqa: F401

from conftest import FIXTURES

GAP_LABEL = "Gap de energia na legenda"


def checkbox(body, label):
    (box,) = [c for c in body.findChildren(QCheckBox) if c.accessibleName() == label]
    return box


@pytest.fixture
def body(qtbot, rig, tmp_path):  # noqa: F811
    folder = tmp_path / "project" / "si"
    shutil.copytree(FIXTURES / "si_bands", folder)
    rig.generate(qtbot, folder)
    return rig.params.body


def test_the_gap_is_disabled_while_the_legend_is_hidden(body):
    gap = checkbox(body, GAP_LABEL)
    assert body.session.params.show_legend is False
    assert not gap.isEnabled()
    assert "Ligue “Mostrar legenda”" in gap.toolTip()
    assert "CBM − VBM" in gap.toolTip()  # the field's own tooltip stays


def test_turning_the_legend_on_and_off_enables_and_disables_it(body):
    gap = checkbox(body, GAP_LABEL)
    checkbox(body, "Mostrar legenda").setChecked(True)
    assert gap.isEnabled() and "Ligue" not in gap.toolTip()
    checkbox(body, "Mostrar legenda").setChecked(False)
    assert not gap.isEnabled()


def test_a_value_pushed_into_the_panel_updates_the_gate(body):
    gap = checkbox(body, GAP_LABEL)
    body.session.params.show_legend = True  # e.g. restored defaults, or a reloaded .plot
    body.refresh_values()
    assert gap.isEnabled()


def test_the_gap_in_the_legend_shows_once_the_legend_is_on(qtbot, rig, body):  # noqa: F811
    view = rig.workflow.current_plot()
    checkbox(body, "Mostrar legenda").setChecked(True)
    checkbox(body, GAP_LABEL).setChecked(True)

    def legend_texts():
        legend = view.figure.axes[0].get_legend()
        return [] if legend is None else [t.get_text() for t in legend.get_texts()]

    qtbot.waitUntil(lambda: any(t.startswith("$E_{gap}$") for t in legend_texts()), timeout=5_000)


def test_a_metal_with_the_gap_asked_shows_the_note_in_the_panel(qtbot, rig, tmp_path):  # noqa: F811
    folder = tmp_path / "project" / "al"
    shutil.copytree(FIXTURES / "al_bands", folder)
    rig.generate(qtbot, folder)
    body = rig.params.body
    checkbox(body, "Mostrar legenda").setChecked(True)
    checkbox(body, GAP_LABEL).setChecked(True)
    qtbot.waitUntil(lambda: NO_GAP_NOTE in body.notes.text(), timeout=5_000)
    assert body.notes.isVisible() or not body.isVisible()  # shown as a ⚠ line under the readout
