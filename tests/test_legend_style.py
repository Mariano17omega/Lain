"""Legend size / transparency and the tick and axis label sizes (the "Legenda" section); spec 36
adds the shift of the legend (``legend_dx`` / ``legend_dy``)."""

import math
import shutil

import pytest
from matplotlib.legend import Legend
from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox

from qe_studio.core.calculations.bands import BandsParams
from qe_studio.core.calculations.params import COMMON_FIELDS
from qe_studio.core.calculations.pdos import PdosParams
from qe_studio.core.plotting.draw import LEGEND_ANCHORS, OUTSIDE_ANCHOR
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.ui.widgets.param_widgets import Section
from spin_helpers import SPIN_PDOS, copy_fixture
from test_bands_dos_render import combined
from test_plotting import load, render

from conftest import FIXTURES

NEW = ("legend_size", "legend_transparency", "tick_size", "label_size")
SHIFT = ("legend_dx", "legend_dy")


def scf_only(folder):
    """A folder with just the Al SCF output: the SCF convergence plot."""
    shutil.copy(FIXTURES / "al_bands" / "al.scf.out", folder)
    return folder


CASES = {
    "pdos": lambda tmp: load(FIXTURES / "al_pdos_flat"),
    "pdos spin": lambda tmp: load(SPIN_PDOS),
    "bands": lambda tmp: load(FIXTURES / "al_bands"),
    "scf": lambda tmp: load(scf_only(tmp)),
    "relax": lambda tmp: load(FIXTURES / "si_relax"),
    "bands + dos": lambda tmp: combined(),
}


@pytest.fixture
def drawn(tmp_path):
    """``drawn(case, **changes)``: the figure of a case with those parameters set, and the params."""

    def draw(case: str, **changes):
        module, dataset, params = CASES[case](tmp_path)
        params.show_legend = True
        for name, value in changes.items():
            setattr(params, name, value)
        return render(module, dataset, params, LIGHT)[0], params

    return draw


def legends(figure):
    return [ax.get_legend() for ax in figure.axes if ax.get_legend()]


def label_sizes(figure):
    return {
        round(label.get_fontsize(), 3)
        for ax in figure.axes
        for label in (ax.xaxis.label, ax.yaxis.label)
        if label.get_text()
    }


def tick_sizes(figure):
    return {
        round(t.get_fontsize(), 3)
        for ax in figure.axes
        for t in (*ax.get_xticklabels(), *ax.get_yticklabels())
        if t.get_text()
    }


# -- the schema ---------------------------------------------------------------------------------
def test_the_four_fields_follow_the_legend_frame_in_the_legend_section():
    names = [f.name for f in COMMON_FIELDS if f.section == "legend"]
    assert names == ["show_legend", "legend_loc", *SHIFT, "legend_frame", *NEW]
    fields = {f.name: f for f in COMMON_FIELDS}
    assert [fields[n].label for n in NEW] == [
        "Tamanho",
        "Transparência",
        "Marcações",
        "Rotulagem dos eixos",
    ]
    assert (fields["legend_transparency"].minimum, fields["legend_transparency"].maximum) == (0, 1)
    assert all(fields[n].optional for n in ("legend_size", "tick_size", "label_size"))


def test_the_shift_fields_come_after_the_position_and_need_the_legend():
    fields = {f.name: f for f in COMMON_FIELDS}
    assert [fields[n].label for n in SHIFT] == ["dx", "dy"]
    for name in SHIFT:
        field = fields[name]
        assert (field.kind, field.minimum, field.maximum, field.step) == ("float", -1, 1, 0.05)
        assert field.requires == "show_legend" and "Superior direita" in field.tooltip
    assert "direita" in fields["legend_dx"].tooltip and "cima" in fields["legend_dy"].tooltip


@pytest.mark.parametrize("case", CASES)
def test_every_module_offers_the_shift_in_the_legend_section(case, tmp_path):
    module, dataset, _params = CASES[case](tmp_path)
    schema = {f.name: f for f in module.param_schema(dataset)}
    for name in SHIFT:
        assert schema[name].section == "legend" and schema[name].requires == "show_legend"


# -- defaults leave every figure as it was --------------------------------------------------------
@pytest.mark.parametrize("case", CASES)
def test_the_defaults_keep_the_old_sizes_and_the_matplotlib_frame_alpha(case, drawn):
    figure, params = drawn(case)
    assert legends(figure)
    for legend in legends(figure):
        assert {t.get_fontsize() for t in legend.get_texts()} == {params.font_size * 0.85}
        assert legend.get_frame().get_alpha() == pytest.approx(0.8)
    assert label_sizes(figure) <= {params.font_size}
    assert tick_sizes(figure) <= {params.font_size}


# -- each parameter changes its artists ----------------------------------------------------------
@pytest.mark.parametrize("case", CASES)
def test_the_legend_size_is_the_text_size(case, drawn):
    figure, _ = drawn(case, legend_size=7.0)
    assert {t.get_fontsize() for lg in legends(figure) for t in lg.get_texts()} == {7.0}


@pytest.mark.parametrize("transparency, alpha", [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)])
def test_the_transparency_is_the_frame_alpha_upside_down(transparency, alpha, drawn):
    figure, _ = drawn("pdos", legend_frame=True, legend_transparency=transparency)
    assert legends(figure)[0].get_frame().get_alpha() == pytest.approx(alpha)


@pytest.mark.parametrize("case", CASES)
def test_tick_and_label_sizes_reach_every_axes(case, drawn):
    figure, _ = drawn(case, tick_size=15.0, label_size=17.0)
    assert tick_sizes(figure) == {15.0}
    assert label_sizes(figure) == {17.0}


def test_each_size_is_independent_of_the_other(drawn):
    figure, params = drawn("pdos", tick_size=15.0)
    assert tick_sizes(figure) == {15.0} and label_sizes(figure) == {params.font_size}
    figure, params = drawn("pdos", label_size=17.0)
    assert label_sizes(figure) == {17.0} and tick_sizes(figure) == {params.font_size}


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_the_pdos_sizes_hold_in_both_orientations(orientation, drawn):
    figure, _ = drawn("pdos", orientation=orientation, tick_size=13.0, label_size=14.0)
    assert tick_sizes(figure) == {13.0} and label_sizes(figure) == {14.0}


def test_bands_dos_applies_both_panels(drawn):
    figure, _ = drawn("bands + dos", tick_size=13.0, label_size=14.0)
    assert len(figure.axes) == 2 and tick_sizes(figure) == {13.0}


# -- the shift of the legend (spec 36) ----------------------------------------------------------------
INSIDE = [loc for loc in LEGEND_ANCHORS if loc != "best"]


def anchor_of(legend) -> tuple[float, float]:
    """Where the legend hangs from, in the fractions of its axes."""
    box = legend.get_bbox_to_anchor()
    return tuple(legend.axes.transAxes.inverted().transform((box.x0, box.y0)))


def box_of(figure, legend) -> tuple[float, float, float, float]:
    """The legend's box in the fractions of its axes: x0, y0, x1, y1."""
    extent = legend.get_window_extent(figure.canvas.get_renderer())
    inverse = legend.axes.transAxes.inverted()
    return (*inverse.transform((extent.x0, extent.y0)), *inverse.transform((extent.x1, extent.y1)))


@pytest.mark.parametrize("loc", [*INSIDE, "best"])
def test_without_a_shift_the_legend_is_where_it_always_was(loc, drawn):
    figure, _ = drawn("pdos", legend_loc=loc)
    (legend,) = legends(figure)
    assert legend._loc == Legend.codes[loc]
    assert anchor_of(legend) == pytest.approx((0.0, 0.0))  # the axes' own box: no anchor was set
    assert tuple(legend.get_bbox_to_anchor().bounds) == tuple(legend.axes.bbox.bounds)


def test_outside_without_a_shift_hangs_from_the_right_edge(drawn):
    figure, _ = drawn("pdos", legend_loc="outside")
    (legend,) = legends(figure)
    assert legend._loc == Legend.codes["upper left"]
    assert anchor_of(legend) == pytest.approx(OUTSIDE_ANCHOR)


@pytest.mark.parametrize("loc", INSIDE)
def test_the_shift_adds_to_the_corner_of_the_position(loc, drawn):
    figure, _ = drawn("pdos", legend_loc=loc, legend_dx=0.2, legend_dy=-0.1)
    (legend,) = legends(figure)
    x, y = LEGEND_ANCHORS[loc]
    assert legend._loc == Legend.codes[loc]  # the same corner of the legend hangs from it
    assert anchor_of(legend) == pytest.approx((x + 0.2, y - 0.1))


def test_outside_shifts_from_its_own_anchor(drawn):
    figure, _ = drawn("pdos", legend_loc="outside", legend_dx=-0.3, legend_dy=0.15)
    (legend,) = legends(figure)
    assert legend._loc == Legend.codes["upper left"]
    assert anchor_of(legend) == pytest.approx((OUTSIDE_ANCHOR[0] - 0.3, OUTSIDE_ANCHOR[1] + 0.15))


def test_best_with_a_shift_counts_as_upper_right(drawn):
    best, _ = drawn("pdos", legend_loc="best", legend_dx=0.1, legend_dy=0.05)
    upper, _ = drawn("pdos", legend_loc="upper right", legend_dx=0.1, legend_dy=0.05)
    (a,), (b,) = legends(best), legends(upper)
    assert a._loc == b._loc == Legend.codes["upper right"]
    assert anchor_of(a) == pytest.approx((1.1, 1.05))
    assert anchor_of(b) == pytest.approx((1.1, 1.05))


@pytest.mark.parametrize("loc", ["upper left", "lower left"])
def test_a_positive_dx_moves_the_box_to_the_right_by_that_fraction(loc, drawn):
    still, _ = drawn("pdos", legend_loc=loc)
    moved, _ = drawn("pdos", legend_loc=loc, legend_dx=0.2)
    (a,), (b,) = legends(still), legends(moved)
    # the legend stays inside the axes, so the layout is the same and the box moves by dx
    assert box_of(moved, b)[0] - box_of(still, a)[0] == pytest.approx(0.2, abs=1e-3)
    assert box_of(moved, b)[3] == pytest.approx(box_of(still, a)[3])


def test_a_positive_dy_moves_the_box_up(drawn):
    still, _ = drawn("pdos", legend_loc="lower left")
    moved, _ = drawn("pdos", legend_loc="lower left", legend_dy=0.2)
    (a,), (b,) = legends(still), legends(moved)
    assert box_of(moved, b)[1] - box_of(still, a)[1] == pytest.approx(0.2, abs=1e-3)


@pytest.mark.parametrize("case", CASES)
def test_the_shift_reaches_the_legend_of_every_module(case, drawn):
    figure, _ = drawn(case, legend_loc="upper right", legend_dx=0.1, legend_dy=-0.1)
    assert legends(figure)
    for legend in legends(figure):
        assert anchor_of(legend) == pytest.approx((1.1, 0.9))


def test_the_shift_of_a_hidden_legend_draws_nothing(drawn):
    figure, _ = drawn("pdos", show_legend=False, legend_dx=0.2)
    assert legends(figure) == []


# -- stored junk never breaks a render ----------------------------------------------------------------
@pytest.mark.parametrize("junk", [math.nan, math.inf, 1.5, -2.0, "alto", None])
def test_an_unusable_shift_is_no_shift(junk, drawn):
    still, _ = drawn("pdos", legend_loc="upper left")
    figure, _ = drawn("pdos", legend_loc="upper left", legend_dx=junk, legend_dy=junk)
    (a,), (b,) = legends(still), legends(figure)
    assert b._loc == a._loc and tuple(b.get_bbox_to_anchor().bounds) == tuple(b.axes.bbox.bounds)
    assert box_of(figure, b) == pytest.approx(box_of(still, a))


@pytest.mark.parametrize("value", [-1, -1.0, 0, 0.25, 1, 1.0])
def test_a_stored_shift_within_range_is_applied(value):
    params = PdosParams()
    assert apply_stored(params, {"legend_dx": value, "legend_dy": value}) == []
    assert (params.legend_dx, params.legend_dy) == (float(value), float(value))
    assert isinstance(params.legend_dx, float)


@pytest.mark.parametrize("junk", [1.01, -1.5, 7, "alto", True, None, [0.1]])
def test_a_stored_shift_outside_range_or_not_a_number_is_ignored(junk):
    params = PdosParams(legend_dx=0.3, legend_dy=-0.3)
    assert apply_stored(params, {"legend_dx": junk, "legend_dy": junk}) == [
        "legend_dx",
        "legend_dy",
    ]
    assert (params.legend_dx, params.legend_dy) == (0.3, -0.3)


# -- the .plot file (shift) -------------------------------------------------------------------------
@pytest.mark.parametrize("params_class, kind", [(BandsParams, "bands"), (PdosParams, "pdos")])
def test_the_shift_round_trips_and_an_old_file_without_it_loads(tmp_path, params_class, kind):
    write_plot_file(tmp_path, kind, params_class(legend_dx=0.3, legend_dy=-0.25))
    stored, _ = read_plot_file(tmp_path, kind)
    fresh = params_class()
    assert apply_stored(fresh, stored) == []
    assert (fresh.legend_dx, fresh.legend_dy) == (0.3, -0.25)
    old = {name: value for name, value in stored.items() if name not in SHIFT}
    fresh = params_class(legend_dx=0.1)
    assert apply_stored(fresh, old) == [] and fresh.legend_dx == 0.1
    assert (params_class().legend_dx, params_class().legend_dy) == (0.0, 0.0)


# -- (sizes) stored junk never breaks a render -------------------------------------------------------
@pytest.mark.parametrize("junk", [math.nan, math.inf, -3.0, 0.0])
def test_unusable_sizes_fall_back_to_the_defaults(junk, drawn):
    figure, params = drawn("pdos", legend_size=junk, tick_size=junk, label_size=junk)
    assert {t.get_fontsize() for t in legends(figure)[0].get_texts()} == {params.font_size * 0.85}
    assert tick_sizes(figure) == {params.font_size} and label_sizes(figure) == {params.font_size}


@pytest.mark.parametrize("junk, alpha", [(-1.0, 1.0), (7.0, 0.0), (math.nan, 0.8)])
def test_a_transparency_outside_zero_to_one_is_clamped(junk, alpha, drawn):
    figure, _ = drawn("pdos", legend_frame=True, legend_transparency=junk)
    assert legends(figure)[0].get_frame().get_alpha() == pytest.approx(alpha)


# -- the .plot file -----------------------------------------------------------------------------------
@pytest.mark.parametrize("params_class, kind", [(BandsParams, "bands"), (PdosParams, "pdos")])
def test_the_fields_round_trip_and_an_old_file_without_them_loads(tmp_path, params_class, kind):
    changed = params_class(legend_size=9, legend_transparency=0.6, tick_size=12.5, label_size=None)
    write_plot_file(tmp_path, kind, changed)
    stored, _ = read_plot_file(tmp_path, kind)
    fresh = params_class()
    assert apply_stored(fresh, stored) == []
    assert (fresh.legend_size, fresh.legend_transparency) == (9.0, 0.6)
    assert (fresh.tick_size, fresh.label_size) == (12.5, None)
    old = {name: value for name, value in stored.items() if name not in NEW}
    fresh = params_class(legend_size=5.0)
    assert apply_stored(fresh, old) == [] and fresh.legend_size == 5.0
    assert apply_stored(params_class(), {"tick_size": "grande"}) == ["tick_size"]


# -- through the window -----------------------------------------------------------------------------
def test_the_panel_edits_reach_the_figure_and_the_plot_file(qtbot, main_window, tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    with qtbot.waitSignal(main_window.plot_ready, timeout=10_000):
        main_window.generate_plot_for(folder, auto_export=False)
    view = main_window.current_plot()
    body = main_window.params.body
    (legend,) = [s for s in body.findChildren(Section) if s.id == "legend"]
    assert legend is not None
    for name in ("legend_size", "legend_transparency", "tick_size", "label_size"):
        assert name in body._setters

    main_window.params.set_param("tick_size", 15.0)
    main_window.params.set_param("label_size", 16.0)
    main_window.params.set_param("legend_size", 8.0)
    qtbot.waitUntil(lambda: tick_sizes(view.figure) == {15.0}, timeout=3000)
    assert label_sizes(view.figure) == {16.0}
    assert {t.get_fontsize() for t in view.figure.axes[0].get_legend().get_texts()} == {8.0}

    main_window.plot_settings.flush_now()
    stored, _ = read_plot_file(folder, "pdos")
    assert (stored["tick_size"], stored["label_size"], stored["legend_size"]) == (15.0, 16.0, 8.0)


def test_the_shift_fields_follow_the_legend_switch_and_move_the_legend(
    qtbot, main_window, tmp_path
):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    with qtbot.waitSignal(main_window.plot_ready, timeout=10_000):
        main_window.generate_plot_for(folder, auto_export=False)
    view = main_window.current_plot()
    body = main_window.params.body
    spins = {
        name: next(w for w in body.findChildren(QDoubleSpinBox) if w.accessibleName() == label)
        for name, label in (("legend_dx", "dx"), ("legend_dy", "dy"))
    }
    (switch,) = [c for c in body.findChildren(QCheckBox) if c.accessibleName() == "Mostrar legenda"]
    switch.setChecked(False)
    assert not any(spin.isEnabled() for spin in spins.values())  # no legend, nothing to shift
    switch.setChecked(True)
    assert all(spin.isEnabled() for spin in spins.values())

    main_window.params.set_param("legend_loc", "upper left")
    main_window.params.set_param("legend_dx", 0.25)
    main_window.params.set_param("legend_dy", -0.15)

    def moved() -> bool:
        legend = view.figure.axes[0].get_legend()
        return legend is not None and abs(anchor_of(legend)[0] - 0.25) < 1e-6

    qtbot.waitUntil(moved, timeout=3000)
    assert anchor_of(view.figure.axes[0].get_legend()) == pytest.approx((0.25, 0.85))
    main_window.plot_settings.flush_now()
    stored, _ = read_plot_file(folder, "pdos")
    assert (stored["legend_dx"], stored["legend_dy"]) == (0.25, -0.15)
