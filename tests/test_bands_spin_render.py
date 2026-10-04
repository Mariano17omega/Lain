"""Spin (two channels) in the band figure, parameters, summary and persistence (spec 13, R3, R4)."""

import time

import numpy as np
import pytest
from matplotlib.collections import LineCollection
from matplotlib.colors import to_hex

from figure_structure import figure_structure
from qe_studio.core.calculations.bands import BandsDataset, BandsModule, BandsParams
from qe_studio.core.calculations.bands.data import ChannelEdges
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.calculations.params import ordered_sections
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.bands_x import BandData
from spin_helpers import (
    SPIN_BANDS,
    detect_one,
    spin_bands_copy,
    with_fixed_magnetization,
    write_gnu,
)
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

SPIN_FIELDS = ["spin_channels", "spin_layout", "spin_coloring", "up_color", "down_color"]


def collections(ax):
    return [c for c in ax.collections if isinstance(c, LineCollection)]


def fermi_lines(ax, params):
    """The horizontal E_F lines: (y, linestyle) of every line in the Fermi color."""
    return [
        (float(line.get_ydata()[0]), line.get_linestyle())
        for line in ax.get_lines()
        if line.get_color() == params.fermi_color
    ]


@pytest.fixture
def spin():
    return load(SPIN_BANDS)


# -- overlay (default) ---------------------------------------------------------------------------
def test_overlay_draws_both_channels_on_one_axes_with_down_dashed(spin):
    module, dataset, params = spin
    params.show_legend = True
    figure, info = render(module, dataset, params, LIGHT)
    assert len(figure.axes) == 1
    up, down = collections(figure.axes[0])
    assert len(up.get_segments()) == len(down.get_segments()) == 14
    assert _hex(up) == params.up_color and _hex(down) == params.down_color
    assert up.get_linestyles()[0][1] is None  # solid
    assert down.get_linestyles()[0][1] is not None  # dashed
    assert [t.get_text() for t in figure.axes[0].get_legend().get_texts()] == [
        "Spin ↑",
        "Spin ↓",
        "$E_F$",
    ]
    assert "↑ metálico · ↓ metálico" in info.summary


def _hex(collection):
    return to_hex(collection.get_colors()[0])


def test_channel_selection_draws_one_channel(spin):
    module, dataset, params = spin
    for channels, color in (("up", params.up_color), ("down", params.down_color)):
        params.spin_channels = channels
        figure, _ = render(module, dataset, params, LIGHT)
        (only,) = collections(figure.axes[0])
        assert _hex(only) == color and only.get_linestyles()[0][1] is None
    params.spin_channels = "down"
    _, info = render(module, dataset, params, LIGHT)
    assert info.xlim == pytest.approx((0.0, dataset.bands_down.x[-1]))


def test_occupation_coloring_uses_valence_and_conduction_colors(spin):
    module, dataset, params = spin
    params.spin_coloring = "occupation"
    params.show_legend = True
    figure, _ = render(module, dataset, params, LIGHT)
    ax = figure.axes[0]
    colors = {_hex(c) for c in collections(ax)}
    assert colors <= {params.valence_color, params.conduction_color}
    assert sum(len(c.get_segments()) for c in collections(ax)) == 28
    dashed = [c for c in collections(ax) if c.get_linestyles()[0][1] is not None]
    solid = [c for c in collections(ax) if c.get_linestyles()[0][1] is None]
    assert sum(len(c.get_segments()) for c in dashed) == sum(len(c.get_segments()) for c in solid)
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Valência" in labels and "Condução" in labels
    assert labels.count("Spin ↑") == labels.count("Spin ↓") == 1


# -- side by side --------------------------------------------------------------------------------
def test_side_layout_makes_two_axes_sharing_y_with_titles_and_one_energy_label(spin):
    module, dataset, params = spin
    params.spin_layout = "side"
    params.title = "Ni"
    figure, info = render(module, dataset, params, LIGHT)
    left, right = figure.axes
    assert left.get_shared_y_axes().joined(left, right)
    assert [left.get_title(), right.get_title()] == ["Spin ↑", "Spin ↓"]
    assert left.get_ylabel() == r"$E - E_F$ (eV)" and right.get_ylabel() == ""
    assert figure._suptitle.get_text() == "Ni"
    for ax, color in ((left, params.up_color), (right, params.down_color)):
        (only,) = collections(ax)
        assert _hex(only) == color and only.get_linestyles()[0][1] is None
        assert [t.get_text() for t in ax.get_xticklabels()][0] == "L"
    assert left.get_ylim() == right.get_ylim() == (params.emin, params.emax)
    assert info.ylim == (params.emin, params.emax)


def test_side_layout_with_one_channel_is_a_single_axes(spin):
    module, dataset, params = spin
    params.spin_layout, params.spin_channels = "side", "up"
    figure, _ = render(module, dataset, params, LIGHT)
    assert len(figure.axes) == 1


def test_zooming_either_side_panel_is_what_apply_limits_stores(spin):
    module, dataset, params = spin
    params.spin_layout = "side"
    figure, _ = render(module, dataset, params, LIGHT)
    figure.axes[1].set_xlim(0.5, 2.0)
    figure.axes[1].set_ylim(-1.0, 3.0)
    limits = [(ax.get_xlim(), ax.get_ylim()) for ax in figure.axes]
    assert limits[0] == limits[1]
    module.apply_limits(params, limits)
    assert (params.xmin, params.xmax, params.emin, params.emax) == (0.5, 2.0, -1.0, 3.0)


# -- Fermi lines ---------------------------------------------------------------------------------
def test_one_fermi_line_for_one_fermi_energy(spin):
    module, dataset, params = spin
    figure, _ = render(module, dataset, params, LIGHT)
    assert fermi_lines(figure.axes[0], params) == [(0.0, "--")]


def test_two_fermi_energies_draw_two_lines_up_solid_down_dashed(tmp_path):
    folder = with_fixed_magnetization(spin_bands_copy(tmp_path))
    module, dataset, params = load(folder)
    params.show_legend = True
    figure, _ = render(module, dataset, params, LIGHT)
    half = (dataset.fermi_up_down[1] - dataset.fermi_up_down[0]) / 2  # the reference is the mean
    (up_line, up_style), (down_line, down_style) = fermi_lines(figure.axes[0], params)
    assert (up_line, down_line) == (pytest.approx(-half), pytest.approx(half))
    assert (up_style, down_style) == ("-", "--")
    legend = [t.get_text() for t in figure.axes[0].get_legend().get_texts()]
    assert "$E_F$ ↑" in legend and "$E_F$ ↓" in legend

    params.spin_layout = "side"
    figure, _ = render(module, dataset, params, LIGHT)
    assert fermi_lines(figure.axes[0], params) == [(pytest.approx(-half), "-")]
    assert fermi_lines(figure.axes[1], params) == [(pytest.approx(half), "--")]


def test_fermi_line_can_be_hidden(spin):
    module, dataset, params = spin
    params.show_fermi_line = False
    figure, _ = render(module, dataset, params, LIGHT)
    assert fermi_lines(figure.axes[0], params) == []


# -- schema, defaults and persistence ------------------------------------------------------------
def test_spin_fields_appear_only_with_two_channels(spin):
    module, dataset, _ = spin
    fields = {f.name: f for f in module.param_schema(dataset)}
    assert all(fields[name].section == "Spin" for name in SPIN_FIELDS)
    assert [c[0] for c in fields["spin_channels"].choices] == ["both", "up", "down"]
    assert [c[0] for c in fields["spin_layout"].choices] == ["overlay", "side"]
    assert [c[0] for c in fields["spin_coloring"].choices] == ["channel", "occupation"]
    sections = [s.name for s in ordered_sections(module)]
    assert sections.index("Spin") == sections.index("Estilo") - 1

    plain_module, plain, _ = load(FIXTURES / "al_bands")
    assert not set(SPIN_FIELDS) & {f.name for f in plain_module.param_schema(plain)}


def test_default_spin_parameters():
    params = BandsParams()
    assert (params.spin_channels, params.spin_layout, params.spin_coloring) == (
        "both",
        "overlay",
        "channel",
    )
    assert (params.up_color, params.down_color) == ("#2563eb", "#f97316")


def test_an_old_bands_plot_file_without_spin_fields_loads_the_defaults(tmp_path, spin):
    module, dataset, params = spin
    (tmp_path / "bands.plot").write_text(
        "lain_plot: 1\nkind: bands\nparams:\n  emin: -3.0\n  emax: 3.0\n  reference: absolute\n"
    )
    stored, warnings = read_plot_file(tmp_path, "bands")
    assert warnings == []
    assert apply_stored(params, stored, module.param_schema(dataset)) == []
    assert (params.emin, params.spin_layout, params.spin_channels) == (-3.0, "overlay", "both")


def test_spin_fields_round_trip_through_the_plot_file(tmp_path, spin):
    module, dataset, params = spin
    params.spin_layout, params.spin_coloring, params.down_color = "side", "occupation", "#112233"
    write_plot_file(tmp_path, "bands", params)
    stored, _ = read_plot_file(tmp_path, "bands")
    fresh = module.default_params(CONFIG, dataset)
    assert apply_stored(fresh, stored, module.param_schema(dataset)) == []
    assert (fresh.spin_layout, fresh.spin_coloring, fresh.down_color) == (
        "side",
        "occupation",
        "#112233",
    )


def test_stored_spin_values_are_validated_with_and_without_spin_fields(spin):
    module, dataset, params = spin
    bad = {"spin_layout": "diagonal", "up_color": "not-a-color", "spin_channels": "up"}
    ignored = apply_stored(params, bad, module.param_schema(dataset))
    assert sorted(ignored) == ["spin_layout", "up_color"] and params.spin_channels == "up"

    plain_module, plain, plain_params = load(FIXTURES / "al_bands")
    ignored = apply_stored(plain_params, bad, plain_module.param_schema(plain))
    assert ignored == ["up_color"]  # no schema field for the colors: the dataclass says "color"


# -- summary -------------------------------------------------------------------------------------
def _dataset(**kwargs):
    base = {
        "folder": SPIN_BANDS,
        "bands": BandData(np.linspace(0, 1, 200), np.zeros((12, 200))),
        "source": "gnu",
        "fermi": 5.1234,
        "fermi_kind": "fermi",
        "ticks": [],
        "labels": [],
        "tick_source": "nenhum",
        "bands_down": BandData(np.linspace(0, 1, 200), np.zeros((12, 200))),
        "magnetization": 0.62,
    }
    return BandsDataset(**{**base, **kwargs})


def test_summary_of_a_gapped_up_channel_and_a_metallic_down_channel():
    dataset = _dataset(
        edges={"up": ChannelEdges(5.1, -1.0, 0.234), "down": ChannelEdges(5.1, metallic=True)}
    )
    assert BandsModule.summary(dataset) == (
        "E_F = 5.1234 eV · spin polarizado · gap ↑ 1.234 eV · ↓ metálico · "
        "M = 0.62 μB/célula · 12 bandas × 200 pontos k"
    )


def test_summary_adds_the_global_gap_when_both_channels_have_one():
    edges = {"up": ChannelEdges(5.1, 3.0, 4.2), "down": ChannelEdges(5.1, 3.2, 4.0)}
    dataset = _dataset(edges=edges, vbm=3.2, cbm=4.0)
    text = BandsModule.summary(dataset)
    assert "gap ↑ 1.200 eV · gap ↓ 0.800 eV · gap global 0.800 eV" in text


def test_summary_with_two_fermi_energies_and_without_magnetization():
    dataset = _dataset(fermi_up_down=(5.0, 5.2), magnetization=None, fermi_kind="spin_fermi")
    assert BandsModule.summary(dataset).startswith(
        "E_F↑ = 5.0000 eV · E_F↓ = 5.2000 eV · spin polarizado"
    )
    assert "M =" not in BandsModule.summary(dataset)


# -- a spin run whose second channel is missing, and latency -------------------------------------
def test_a_missing_down_channel_still_plots_the_up_channel(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_dw.dat.gnu", "bands_dw.dat"))
    module, dataset, params = load(folder)
    figure, info = render(module, dataset, params, LIGHT)
    assert len(figure.axes) == 1 and "spin polarizado" not in info.summary
    assert figure_structure(figure)[0]["line_collections"]
    assert "↑ metálico" in info.summary and "· metálico" not in info.summary


def test_summary_of_an_insulating_up_channel_without_its_down_channel():
    dataset = _dataset(bands_down=None, edges={"up": ChannelEdges(5.1, -1.0, 0.234)})
    assert (
        BandsModule.summary(dataset)
        == "E_F = 5.1234 eV · gap ↑ 1.234 eV · 12 bandas × 200 pontos k"
    )


def test_occupation_coloring_counts_the_bands_of_fixed_occupations(spin):
    module, dataset, params = spin
    params.spin_coloring = "occupation"
    n_up = 6  # E_F (inside the bands of Ni) alone would make another split
    dataset.edges = {**dataset.edges, "up": ChannelEdges(dataset.fermi, n_occupied=n_up)}
    figure, _ = render(module, dataset, params, LIGHT)
    solid = [c for c in collections(figure.axes[0]) if c.get_linestyles()[0][1] is None]
    valence = [c for c in solid if _hex(c) == params.valence_color]
    assert len(valence) == 1 and len(valence[0].get_segments()) == n_up


def test_a_dataset_without_eigenvalues_still_fails_cleanly(tmp_path):
    folder = spin_bands_copy(
        tmp_path,
        remove=(
            "ni.band.out",
            "bands_up.dat.gnu",
            "bands_dw.dat.gnu",
            "bands_up.dat",
            "bands_dw.dat",
        ),
    )
    result = detect_one(folder)
    with pytest.raises(LoadError):
        result.module.load(result)


@pytest.mark.perf
def test_two_channels_of_a_hundred_bands_load_and_render_under_budget(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_up.dat", "bands_dw.dat", "ni.band.out"))
    x = np.linspace(0, 3.7802, 91)
    for name, shift in (("bands_up.dat.gnu", 0.0), ("bands_dw.dat.gnu", 0.4)):
        write_gnu(folder / name, x, [5 * np.sin(x + b) + b / 5 + shift for b in range(100)])
    start = time.perf_counter()
    result = detect_one(folder)
    dataset = result.module.load(result)
    assert dataset.spin and dataset.bands.n_bands == dataset.bands_down.n_bands == 100
    params = result.module.default_params(CONFIG, dataset)
    render(result.module, dataset, params, LIGHT)
    assert time.perf_counter() - start < 0.5


def test_side_legend_names_no_channel_already_titled(spin):
    module, dataset, params = spin
    params.spin_layout, params.show_legend = "side", True
    figure, _ = render(module, dataset, params, LIGHT)
    assert [t.get_text() for t in figure.axes[0].get_legend().get_texts()] == ["$E_F$"]
    assert figure.axes[1].get_legend() is None

    params.spin_coloring = "occupation"  # the colors now need a key
    figure, _ = render(module, dataset, params, LIGHT)
    assert [t.get_text() for t in figure.axes[0].get_legend().get_texts()] == [
        "Valência",
        "Condução",
        "$E_F$",
    ]
