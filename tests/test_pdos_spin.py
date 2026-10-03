"""Spin (two channels) in the PDOS figure: modes, channel cues, two Fermi energies (spec 13, R5)."""

import numpy as np
import pytest
from matplotlib.collections import PolyCollection

from figure_structure import figure_structure
from qe_studio.core.calculations.pdos import PdosModule
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from spin_helpers import FIXED_FERMI, SPIN_FIXED, SPIN_PDOS, copy_fixture
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

MODES = ["mirror", "overlay", "up", "down", "sum"]


@pytest.fixture
def spin():
    return load(SPIN_PDOS)


def lines(ax, label):
    return [line for line in ax.get_lines() if line.get_label() == label]


def texts(ax):
    return [t.get_text() for t in ax.texts]


def fermi_lines(ax, params):
    return [line for line in ax.get_lines() if line.get_color() == params.fermi_color]


# -- the five modes ------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_every_mode_renders_in_both_orientations(spin, mode, orientation):
    module, dataset, params = spin
    params.spin_mode, params.orientation = mode, orientation
    figure, info = render(module, dataset, params, LIGHT)
    dos = info.xlim if orientation == "vertical" else info.ylim
    if mode == "mirror":
        assert dos[0] == -dos[1] < 0
    else:
        assert dos[0] == 0.0 and dos[1] > 0
    ax = figure.axes[0]
    assert (ax.get_xlim() if orientation == "vertical" else ax.get_ylim()) == dos


def test_mirror_is_the_default_and_draws_the_down_channel_negative(spin):
    module, dataset, params = spin
    assert params.spin_mode == "mirror"
    figure, _ = render(module, dataset, params, LIGHT)
    (total,) = lines(figure.axes[0], "Total")
    down = [ln for ln in figure.axes[0].get_lines() if ln.get_label().startswith("_")]
    assert np.allclose(total.get_ydata(), dataset.data.total.up)
    assert np.allclose(down[0].get_ydata(), -dataset.data.total.down)


def test_mirror_marks_the_two_channels_on_each_side_of_zero(spin):
    module, dataset, params = spin
    figure, _ = render(module, dataset, params, LIGHT)
    ax = figure.axes[0]
    assert texts(ax) == ["↑", "↓"]
    up, down = ax.texts
    assert up.get_position()[1] > 0.5 > down.get_position()[1]
    assert up.get_color() == down.get_color() == LIGHT.guide

    params.orientation = "vertical"
    figure, _ = render(module, dataset, params, LIGHT)
    up, down = figure.axes[0].texts
    assert up.get_position()[0] > 0.5 > down.get_position()[0]


def test_overlay_draws_the_down_channel_positive_dashed_and_fills_only_up(spin):
    module, dataset, params = spin
    params.spin_mode, params.show_legend = "overlay", True
    figure, _ = render(module, dataset, params, LIGHT)
    ax = figure.axes[0]
    (total,) = lines(ax, "Total")
    dashed = [
        ln
        for ln in ax.get_lines()
        if ln.get_linestyle() == "--" and ln.get_color() == total.get_color()
    ]
    assert dashed and np.allclose(dashed[0].get_ydata(), dataset.data.total.down)
    assert len(ax.collections) == 3  # one fill per series and the total, ↑ only
    assert [t.get_text() for t in ax.get_legend().get_texts()] == [
        "Total", "Ni s", "Ni d", "↑ contínua", "↓ tracejada",
    ]  # fmt: skip
    assert texts(ax) == []


def test_up_and_down_modes_draw_one_positive_channel(spin):
    module, dataset, params = spin
    for mode, expected in (("up", dataset.data.total.up), ("down", dataset.data.total.down)):
        params.spin_mode = mode
        figure, _ = render(module, dataset, params, LIGHT)
        ax = figure.axes[0]
        (total,) = lines(ax, "Total")
        assert np.allclose(total.get_ydata(), expected)
        assert (
            len(
                [
                    ln
                    for ln in ax.get_lines()
                    if ln.get_label() == "Total" or ln.get_label().startswith("Ni")
                ]
            )
            == 3
        )
        assert texts(ax) == []


def test_sum_mode_adds_the_channels(spin):
    module, dataset, params = spin
    params.spin_mode = "sum"
    figure, _ = render(module, dataset, params, LIGHT)
    (total,) = lines(figure.axes[0], "Total")
    assert np.allclose(total.get_ydata(), dataset.data.total.up + dataset.data.total.down)
    assert len(figure.axes[0].get_lines()) == 3 + 1  # three series, one Fermi line


def test_a_dataset_without_spin_ignores_spin_mode():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    reference, _ = render(module, dataset, params, LIGHT)
    for mode in MODES:
        params.spin_mode = mode
        figure, _ = render(module, dataset, params, LIGHT)
        assert figure_structure(figure) == figure_structure(reference)


# -- Fermi energies ------------------------------------------------------------------------------
def test_one_fermi_energy_one_line(spin):
    module, dataset, params = spin
    for mode in MODES:
        params.spin_mode = mode
        figure, _ = render(module, dataset, params, LIGHT)
        (line,) = fermi_lines(figure.axes[0], params)
        assert line.get_linestyle() == "--"


@pytest.fixture
def fixed(tmp_path):
    folder = copy_fixture(SPIN_PDOS.name, tmp_path)
    (folder / "ni.scf.out").write_text((SPIN_FIXED / "ni.scf.out").read_text())
    return load(folder)


def test_two_fermi_energies_draw_up_solid_and_down_dashed(fixed):
    module, dataset, params = fixed
    assert dataset.fermi_channels("scf") == FIXED_FERMI
    assert dataset.fermi_channels("nscf") is None  # the NSCF run printed a single E_F
    ref = dataset.fermi("scf")
    for mode, expected in (
        ("mirror", [("-", FIXED_FERMI[0]), ("--", FIXED_FERMI[1])]),
        ("overlay", [("-", FIXED_FERMI[0]), ("--", FIXED_FERMI[1])]),
        ("up", [("-", FIXED_FERMI[0])]),
        ("down", [("--", FIXED_FERMI[1])]),
        ("sum", [("--", ref)]),
    ):
        params.spin_mode = mode
        figure, _ = render(module, dataset, params, LIGHT)
        got = [
            (ln.get_linestyle(), float(ln.get_xdata()[0]))
            for ln in fermi_lines(figure.axes[0], params)
        ]
        assert got == [(style, pytest.approx(value - ref)) for style, value in expected]


def test_each_channel_fills_up_to_its_own_fermi_energy(fixed):
    module, dataset, params = fixed
    figure, _ = render(module, dataset, params, LIGHT)
    fills = [c for c in figure.axes[0].collections if isinstance(c, PolyCollection)]
    ref = dataset.fermi("scf")
    up_max = [c.get_paths()[0].vertices[:, 0].max() for c in fills[0::2]]
    down_max = [c.get_paths()[0].vertices[:, 0].max() for c in fills[1::2]]
    assert max(up_max) <= FIXED_FERMI[0] - ref + 1e-9
    assert max(down_max) <= FIXED_FERMI[1] - ref + 1e-9
    assert max(down_max) > FIXED_FERMI[0] - ref  # the ↓ channel is filled further than ↑


def test_the_nscf_source_falls_back_to_a_single_line(fixed):
    module, dataset, params = fixed
    params.fermi_source = "nscf"
    figure, _ = render(module, dataset, params, LIGHT)
    (line,) = fermi_lines(figure.axes[0], params)
    assert line.get_linestyle() == "--"


# -- limits, schema, persistence, summary --------------------------------------------------------
def test_apply_limits_stores_the_symmetric_limit_only_when_mirrored(spin):
    module, _, params = spin
    module.apply_limits(params, [((-5.0, 5.0), (-1.5, 2.0))])
    assert params.dos_max == 2.0  # mirrored: the larger side
    params.spin_mode = "overlay"
    module.apply_limits(params, [((-5.0, 5.0), (0.0, 1.2))])
    assert params.dos_max == 1.2
    params.orientation = "vertical"
    module.apply_limits(params, [((0.1, 1.4), (-3.0, 3.0))])
    assert (params.dos_max, params.emin, params.emax) == (1.4, -3.0, 3.0)


def test_spin_mode_is_offered_only_for_a_spin_polarized_pdos(spin):
    module, dataset, _ = spin
    fields = {f.name: f for f in module.param_schema(dataset)}
    assert fields["spin_mode"].section == "Projeções"
    assert [c[0] for c in fields["spin_mode"].choices] == MODES
    plain_module, plain, _ = load(FIXTURES / "al_pdos_flat")
    assert "spin_mode" not in {f.name for f in plain_module.param_schema(plain)}


def test_an_old_pdos_plot_file_loads_with_the_mirror_mode(tmp_path, spin):
    module, dataset, params = spin
    (tmp_path / "pdos.plot").write_text(
        "lain_plot: 1\nkind: pdos\nparams:\n  emin: -3.0\n  grouping: species\n"
    )
    stored, warnings = read_plot_file(tmp_path, "pdos")
    assert warnings == []
    assert apply_stored(params, stored, module.param_schema(dataset)) == []
    assert (params.emin, params.grouping, params.spin_mode) == (-3.0, "species", "mirror")


def test_spin_mode_round_trips_and_an_unknown_value_is_ignored(tmp_path, spin):
    module, dataset, params = spin
    params.spin_mode = "overlay"
    write_plot_file(tmp_path, "pdos", params)
    stored, _ = read_plot_file(tmp_path, "pdos")
    fresh = module.default_params(CONFIG, dataset)
    assert apply_stored(fresh, stored, module.param_schema(dataset)) == []
    assert fresh.spin_mode == "overlay"
    assert apply_stored(fresh, {"spin_mode": "diagonal"}, module.param_schema(dataset)) == [
        "spin_mode"
    ]
    assert fresh.spin_mode == "overlay"


def test_summary_has_the_magnetization_of_the_spin_run(spin):
    module, dataset, params = spin
    assert dataset.magnetization == 0.71
    assert PdosModule.summary(dataset, params) == (
        "E_F = 14.2704 eV (SCF) · 2 projeções · 1 espécies · spin polarizado · M = 0.71 μB/célula"
    )


def test_summary_with_two_fermi_energies(fixed):
    module, dataset, params = fixed
    text = PdosModule.summary(dataset, params)
    assert text.startswith("E_F↑ = 13.8484 eV · E_F↓ = 14.1389 eV (SCF)")
    assert text.endswith("M = 0.50 μB/célula")


def test_summary_of_a_pdos_without_spin_has_no_magnetization():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    assert dataset.magnetization is None
    assert "μB" not in PdosModule.summary(dataset, params)
