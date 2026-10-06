"""Legend size / transparency and the tick and axis label sizes (the "Legenda" section)."""

import math
import shutil

import pytest

from qe_studio.core.calculations.bands import BandsParams
from qe_studio.core.calculations.params import COMMON_FIELDS
from qe_studio.core.calculations.pdos import PdosParams
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.ui.widgets.param_widgets import Section
from spin_helpers import SPIN_PDOS, copy_fixture
from test_bands_dos_render import combined
from test_plotting import load, render

from conftest import FIXTURES

NEW = ("legend_size", "legend_transparency", "tick_size", "label_size")


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
    names = [f.name for f in COMMON_FIELDS if f.section == "Legenda"]
    assert names == ["show_legend", "legend_loc", "legend_frame", *NEW]
    fields = {f.name: f for f in COMMON_FIELDS}
    assert [fields[n].label for n in NEW] == [
        "Tamanho",
        "Transparência",
        "Marcações",
        "Rotulagem dos eixos",
    ]
    assert (fields["legend_transparency"].minimum, fields["legend_transparency"].maximum) == (0, 1)
    assert all(fields[n].optional for n in ("legend_size", "tick_size", "label_size"))


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


# -- stored junk never breaks a render ----------------------------------------------------------------
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
    (legend,) = [s for s in body.findChildren(Section) if s.title == "Legenda"]
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
