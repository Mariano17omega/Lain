"""Spec 10 R6: the cursor readout of every plot, worded by its module (`format_coordinates`)."""

import logging
import re

from matplotlib.backend_bases import MouseEvent

from qe_studio.core.calculations.bands import merged_ticks
from qe_studio.core.calculations.readout import (
    nearest_tick_label,
    plain_kpoint_label,
    signed,
)


def plot(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)
    return window.current_plot()


def hover(view, x: float, y: float | None = None, axes_index: int = 0) -> str:
    """Move the mouse (synthetic event) over the data point (x, y) of an axes (y: halfway up
    the axes); the toolbar's text."""
    view.canvas.draw()
    ax = view.figure.axes[axes_index]
    px, py = ax.transData.transform((x, ax.get_ylim()[0] if y is None else y))
    if y is None:
        py = ax.transAxes.transform((0, 0.5))[1]
    event = MouseEvent("motion_notify_event", view.canvas, px, py)
    view.canvas.callbacks.process("motion_notify_event", event)
    return view.toolbar.message.text()


def hover_outside(view) -> str:
    view.canvas.draw()
    view.canvas.callbacks.process(
        "motion_notify_event", MouseEvent("motion_notify_event", view.canvas, 1, 1)
    )
    return view.toolbar.message.text()


# -- helpers -----------------------------------------------------------------------------------
def test_signed_uses_a_real_minus():
    assert signed(-1.2345, ".3f") == "−1.234" and signed(0.5, ".3f") == "0.500"


def test_plain_labels():
    assert plain_kpoint_label(r"$\Gamma$") == "Γ"
    assert plain_kpoint_label("Y$_2$") == "Y₂" and plain_kpoint_label("X$_{12}$") == "X₁₂"
    assert plain_kpoint_label("X|W") == "X|W" and plain_kpoint_label("") == ""


def test_nearest_tick_label_tolerance():
    ticks, labels = [0.0, 1.0, 2.0], [r"$\Gamma$", "X", ""]
    assert nearest_tick_label(0.995, ticks, labels, 2.0) == "X"  # within 1 % of the span
    assert nearest_tick_label(0.9, ticks, labels, 2.0) == ""
    assert nearest_tick_label(2.0, ticks, labels, 2.0) == ""  # unlabeled tick
    assert (
        nearest_tick_label(0.0, [], [], 2.0) == "" and nearest_tick_label(0, ticks, labels, 0) == ""
    )


# -- the modules -------------------------------------------------------------------------------
def test_bands_readout(qtbot, main_window, demo_project):
    view = plot(qtbot, main_window, demo_project / "03_bands")
    session = view.session
    x_mid = float(session.dataset.bands.x[len(session.dataset.bands.x) // 2])
    text = hover(view, x_mid + 1e-3, -1.2345)
    assert re.fullmatch(r"k = \d+\.\d{4} · E − E_F = −1\.234 eV", text), text
    assert hover_outside(view) == ""

    ticks, labels = merged_ticks(
        session.dataset.ticks, session.module.tick_labels(session.dataset, session.params)
    )
    named = next(i for i, label in enumerate(labels) if label)
    text = hover(view, ticks[named], 0.5)
    assert text.endswith(f" · {plain_kpoint_label(labels[named])}"), text

    session.params.reference = "absolute"
    assert " · E = " in session.format_coordinates(x_mid, 1.0, 0)
    session.params.reference = "vbm"
    assert " · E − E_VBM = " in session.format_coordinates(x_mid, 1.0, 0)


def test_bands_label_uses_the_visible_span(qtbot, main_window, demo_project):
    view = plot(qtbot, main_window, demo_project / "03_bands")
    session = view.session
    ticks, labels = merged_ticks(
        session.dataset.ticks, session.module.tick_labels(session.dataset, session.params)
    )
    named = next(i for i, label in enumerate(labels) if label)
    off = ticks[named] + 0.005 * (ticks[-1] - ticks[0])
    assert session.format_coordinates(off, 0.0, 0).endswith(plain_kpoint_label(labels[named]))
    # Zoomed in 100x, the same distance is far away from the point.
    session.params.xmin, session.params.xmax = ticks[named] - 0.005, ticks[named] + 0.005
    assert not session.format_coordinates(off + 0.003, 0.0, 0).endswith(
        plain_kpoint_label(labels[named])
    )


def test_pdos_readout_follows_the_orientation(qtbot, main_window, demo_project):
    view = plot(qtbot, main_window, demo_project / "04_pdos")
    params = view.session.params
    params.shift_to_fermi = True
    text = hover(view, -1.0, 0.5)  # energy on X
    assert re.fullmatch(r"E( − E_F)? = −1\.000 eV · PDOS = 0\.500 est\./eV", text), text
    params.orientation = "vertical"
    view.render()
    text = hover(view, 0.5, -1.0)  # now the DOS is on X
    assert re.fullmatch(r"E( − E_F)? = −1\.000 eV · PDOS = 0\.500 est\./eV", text), text
    params.shift_to_fermi = False
    assert view.session.format_coordinates(0.5, -1.0, 0).startswith("E = −1.000 eV")


def test_relax_readout_picks_the_panel_and_the_nearest_step(qtbot, main_window, demo_project):
    view = plot(qtbot, main_window, demo_project / "01_relax")
    session = view.session
    data = session.dataset.data
    assert len(data.energy_deltas) >= 2
    step = 2
    energy = f"passo {step} · |ΔE| = {data.energy_deltas[step - 1]:.1e} Ry"
    force = f"passo {step} · F = {data.steps[step].force_ry_bohr:.1e} Ry/Bohr"
    assert session.params.panels == "both" and len(view.figure.axes) == 2
    assert hover(view, step + 0.3, axes_index=0) == energy  # Y is not used
    assert hover(view, step - 0.2, axes_index=1) == force
    assert hover_outside(view) == ""
    assert session.format_coordinates(99.0, 1.0, 0) == ""  # no such step
    assert session.format_coordinates(0.0, 1.0, 0) == ""  # |ΔE| starts at step 1
    session.params.panels = "force"  # one axes, the force one
    view.render()
    assert len(view.figure.axes) == 1 and session.format_coordinates(step, 1.0, 0) == force
    assert session.format_coordinates(step, 1.0, 1) == ""


def test_scf_readout_picks_the_panel(qtbot, main_window, demo_project):
    window = main_window
    output = demo_project / "02_scf" / "scf.out"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.plot_file(output, "scf")
    view = window.current_plot()
    session = view.session
    iterations = session.dataset.data.iterations
    first, second = iterations[0], iterations[1]
    assert hover(view, first.index, axes_index=0) == (
        f"iteração {first.index} · precisão = {first.accuracy_ry:.1e} Ry"
    )
    delta = abs(second.energy_ry - first.energy_ry)
    assert session.format_coordinates(second.index, 0, 1) == (
        f"iteração {second.index} · |ΔE| = {delta:.1e} Ry"
    )
    assert session.format_coordinates(first.index, 0, 1) == ""  # |ΔE| starts at the 2nd
    session.params.energy_mode = "total"
    assert session.format_coordinates(first.index, 0, 1) == (
        f"iteração {first.index} · E = {signed(first.energy_ry, '.6f')} Ry"
    )
    assert session.format_coordinates(999, 0, 0) == ""
    assert session.format_coordinates(first.index, 0, 5) == ""


def test_readout_is_installed_after_every_render(qtbot, main_window, demo_project):
    view = plot(qtbot, main_window, demo_project / "03_bands")
    old = view.figure.axes[0].format_coord
    view.render()  # new axes
    assert view.figure.axes[0].format_coord is not old
    assert view.figure.axes[0].format_coord(0.1, 0.2).startswith("k = ")


def test_a_failing_module_leaves_the_readout_empty(qtbot, main_window, demo_project, caplog):
    view = plot(qtbot, main_window, demo_project / "03_bands")
    module = view.session.module

    def broken(*args):
        raise RuntimeError("boom")

    module.format_coordinates = broken  # type: ignore[method-assign]
    try:
        with caplog.at_level(logging.ERROR):
            assert hover(view, 0.1, 0.2) == "" and hover(view, 0.2, 0.2) == ""
        assert len([r for r in caplog.records if "readout" in r.message]) == 1  # logged once
    finally:
        del module.format_coordinates  # back to the class method
    assert hover(view, 0.1, 0.2).startswith("k = ")
