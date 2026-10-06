"""Spec 22 R3–R5: the bands + DOS figure, its parameters and its ``.plot``."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from matplotlib.ticker import MaxNLocator

from qe_studio.core.calculations.bands.gap import NO_GAP_NOTE
from qe_studio.core.calculations.bands_dos.render import JOIN_CLEARANCE, ClearOfJoin
from qe_studio.core.calculations.params import ordered_sections
from qe_studio.core.calculations.pdos.gap import GapInfo
from qe_studio.core.compounds import Compound
from qe_studio.core.detection import PairTarget
from qe_studio.core.plotting.gap_label import gap_label
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.session import load_plot
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.sniff import SniffCache
from spin_helpers import SPIN_BANDS, SPIN_PDOS
from test_plotting import CONFIG, render

from conftest import FIXTURES

AL_BANDS, AL_PDOS = FIXTURES / "al_bands", FIXTURES / "al_pdos_flat"
AL_FERMI = 8.0584


def combined(bands: Path = AL_BANDS, dos: Path = AL_PDOS, **changes):
    cache = SniffCache()
    result, dataset = load_plot(PairTarget(bands, dos, cache.sniff), cache.sniff)
    module = result.module
    params = module.default_params(CONFIG, dataset)
    for name, value in changes.items():
        setattr(params, name, value)
    return module, dataset, params


def with_parts(dataset, **parts):
    """``dataset`` with its ``bands`` / ``dos`` replaced by copies changed as asked."""
    changed = {name: dataclasses.replace(getattr(dataset, name), **c) for name, c in parts.items()}
    return dataclasses.replace(dataset, **changed)


def fermi_lines(ax, color):
    return [line for line in ax.get_lines() if line.get_color() == color]


def legend_texts(figure) -> list[str]:
    return [t.get_text() for ax in figure.axes if ax.get_legend() for t in ax.get_legend().texts]


def test_two_panels_share_the_energy_axis_with_no_space_between():
    module, dataset, params = combined()
    figure, info = render(module, dataset, params)
    bands_ax, dos_ax = figure.axes
    assert bands_ax.get_shared_y_axes().joined(bands_ax, dos_ax)
    assert bands_ax.get_ylim() == dos_ax.get_ylim() == (params.emin, params.emax)
    left, right = bands_ax.get_position(), dos_ax.get_position()
    assert right.width / left.width == pytest.approx(params.dos_width_ratio, rel=0.02)
    assert right.x0 == pytest.approx(left.x1, abs=1e-6)
    assert dos_ax.get_ylabel() == "" and bands_ax.get_ylabel() == "$E - E_F$ (eV)"
    assert dos_ax.get_xlabel() == "PDOS (estados/eV)"
    assert info.ylim == (params.emin, params.emax)
    assert info.xlim == pytest.approx((0.0, 3.2802), abs=1e-4)


def test_a_wider_dos_panel():
    module, dataset, params = combined(dos_width_ratio=0.8)
    bands_ax, dos_ax = render(module, dataset, params)[0].axes
    assert dos_ax.get_position().width / bands_ax.get_position().width == pytest.approx(
        0.8, rel=0.02
    )


def test_one_reference_for_both_panels():
    module, dataset, params = combined()
    color = params.fermi_color
    figure, _ = render(module, dataset, params)
    for ax in figure.axes:  # E_F at 0 on both
        assert [list(line.get_ydata()) for line in fermi_lines(ax, color)] == [[0, 0]]
    total = next(line for line in figure.axes[1].get_lines() if line.get_label() == "Total")
    np.testing.assert_allclose(total.get_ydata(), dataset.dos.data.energy - AL_FERMI)

    module.param_changed(dataset, params, "reference", params.reference)  # no change: no shift
    params.reference = "absolute"
    module.param_changed(dataset, params, "reference", "fermi")
    assert (params.emin, params.emax) == pytest.approx((AL_FERMI - 5, AL_FERMI + 5))
    figure, _ = render(module, dataset, params)
    for ax in figure.axes:
        assert [list(line.get_ydata()) for line in fermi_lines(ax, color)] == [[AL_FERMI] * 2]
    total = next(line for line in figure.axes[1].get_lines() if line.get_label() == "Total")
    np.testing.assert_allclose(total.get_ydata(), dataset.dos.data.energy)


def test_a_different_fermi_energy_of_the_dos_gets_a_note():
    module, dataset, params = combined()
    same = with_parts(dataset, dos={"fermi_scf": AL_FERMI})
    assert render(module, same, params)[1].notes == ()
    near = with_parts(dataset, dos={"fermi_scf": AL_FERMI + 0.04})
    assert render(module, near, params)[1].notes == ()
    off = with_parts(dataset, dos={"fermi_scf": AL_FERMI + 0.1})
    assert render(module, off, params)[1].notes == ("E_F da DOS difere do das bandas em 0.100 eV",)


def test_a_dos_of_another_compound_gets_a_note():
    module, dataset, params = combined()
    other = dataclasses.replace(
        with_parts(dataset, dos={"fermi_scf": AL_FERMI}), bands_compound=Compound("Si2:x", "Si2")
    )
    (note,) = render(module, other, params)[1].notes
    assert "compostos diferentes" in note and "Si2" in note


def test_one_legend_on_the_dos_with_the_series_and_the_bands():
    module, dataset, params = combined()
    figure, _ = render(module, dataset, params)
    assert [ax.get_legend() is not None for ax in figure.axes] == [False, True]
    assert legend_texts(figure) == ["Total", "Al s", "Al p", "Valência", "Condução", "$E_F$"]


def test_the_legend_goes_to_the_bands_when_the_dos_draws_nothing():
    module, dataset, params = combined(show_total=False, hidden_series=["Al s", "Al p"])
    figure, _ = render(module, dataset, params)
    assert [ax.get_legend() is not None for ax in figure.axes] == [True, False]


def test_the_dos_panel_draws_with_the_element_colors():
    module, dataset, params = combined()
    assert params.atomos_colors["Al"] == "#E41A1C"
    assert module.series_colors(dataset, params, LIGHT)["Al s"] == "#E41A1C"


def test_a_metal_with_the_gap_asked_has_the_note_in_the_combined_readout():
    module, dataset, params = combined(legend_gap=True, show_legend=True)
    _figure, info = render(module, dataset, params)
    assert NO_GAP_NOTE in info.notes
    _figure, info = render(module, dataset, combined(legend_gap=False, show_legend=True)[2])
    assert NO_GAP_NOTE not in info.notes


def test_the_gap_is_in_the_legend_once_from_the_bands():
    module, dataset, params = combined(legend_gap=True)
    gapped = with_parts(
        dataset,
        bands={"vbm": AL_FERMI - 1.0, "cbm": AL_FERMI + 0.5},
        dos={"gap": GapInfo(0.7, "dos")},
    )
    texts = legend_texts(render(module, gapped, params)[0])
    assert [t for t in texts if "E_{gap}" in t] == [gap_label(1.5)]
    assert not any(
        "E_{gap}" in t for t in legend_texts(render(module, dataset, params)[0])
    )  # metal


def test_spin_bands_with_an_overlaid_spin_dos():
    module, dataset, params = combined(SPIN_BANDS, SPIN_PDOS, legend_gap=True)
    assert dataset.bands.spin and dataset.dos.data.spin_polarized
    assert params.spin_mode == "overlay"
    figure, info = render(module, dataset, params)
    bands_ax, dos_ax = figure.axes
    assert len(bands_ax.collections) >= 2  # ↑ and ↓
    assert any(line.get_linestyle() == "--" for line in dos_ax.get_lines())  # ↓ dashed
    texts = legend_texts(figure)
    assert "Spin ↑" in texts and "Spin ↓" in texts
    assert "↓ tracejada" not in texts  # the bands' entries already tell the channels apart
    assert not any("E_{gap}" in t for t in texts)  # Ni is a metal
    assert "spin polarizado" in info.summary

    params.spin_channels = "up"  # one band channel: the DOS says which line is which
    assert "↓ tracejada" in legend_texts(render(module, dataset, params)[0])
    params.spin_mode = "mirror"
    bands_ax, dos_ax = render(module, dataset, params)[0].axes
    low, high = dos_ax.get_xlim()
    assert low == pytest.approx(-high)


def test_no_tick_label_where_the_panels_meet():
    locator = ClearOfJoin(nbins=4)
    for low, high in ((0.0, 1.0), (-2.2, 2.2), (0.0, 0.31)):
        plain = MaxNLocator(nbins=4).tick_values(low, high)
        ticks = locator.tick_values(low, high)
        assert plain.min() <= low + JOIN_CLEARANCE * (high - low)  # one would sit at the join
        assert len(ticks) and ticks.min() > low + JOIN_CLEARANCE * (high - low)


def test_toolbar_limits_go_to_the_panel_they_belong_to():
    module, _dataset, params = combined()
    module.apply_limits(params, [((0.5, 2.0), (-3.0, 2.0)), ((0.0, 0.8), (-3.0, 2.0))])
    assert (params.xmin, params.xmax, params.emin, params.emax) == (0.5, 2.0, -3.0, 2.0)
    assert params.dos_max == 0.8
    params.spin_mode = "mirror"
    module.apply_limits(params, [((0.5, 2.0), (-3.0, 2.0)), ((-1.5, 1.2), (-3.0, 2.0))])
    assert params.dos_max == 1.5


def test_the_cursor_readout_of_each_panel():
    module, dataset, params = combined()
    bands_text = module.format_coordinates(0.866, -1.234, 0, dataset, params)
    assert bands_text.startswith("k = 0.8660 · E − E_F = −1.234 eV")
    assert module.format_coordinates(0.5, -1.234, 1, dataset, params) == (
        "E − E_F = −1.234 eV · PDOS = 0.500 est./eV"
    )


def test_defaults_and_title():
    module, dataset, params = combined()
    assert params.spin_mode == "overlay" and params.show_legend and params.legend_loc == "outside"
    assert params.reference == "fermi" and params.dos_width_ratio == 0.35
    assert params.dos_folder == "../al_pdos_flat"
    assert module.plot_title(AL_BANDS, dataset) == "Bandas + DOS — Al"
    assert module.export_stem(params) == "bands_dos"


@pytest.mark.parametrize("bands, dos", [(AL_BANDS, AL_PDOS), (SPIN_BANDS, SPIN_PDOS)])
def test_every_field_has_a_section_of_this_figure(bands, dos):
    module, dataset, params = combined(bands, dos)
    schema = module.param_schema(dataset)
    sections = [s.name for s in ordered_sections(module)]
    assert {f.section for f in schema} <= set(sections)
    names = [f.name for f in schema]
    assert len(names) == len(set(names))
    assert all(hasattr(params, name) for name in names)
    assert not {"spin_layout", "orientation", "fermi_source", "shift_to_fermi"} & set(names)
    by_name = {f.name: f.section for f in schema}
    assert by_name["emin"] == "Energia" and by_name["labels"] == "Bandas ▸ Eixo k"
    assert by_name["atoms"] == by_name["hidden_series"] == "DOS ▸ Projeções"
    assert by_name["dos_width_ratio"] == by_name["dos_max"] == "DOS ▸ Eixo"
    assert sections.index("DOS ▸ Projeções") < sections.index("Estilo")
    spin = dataset.bands.spin
    assert ("spin_channels" in by_name) == spin and ("spin_mode" in by_name) == spin


def test_the_plot_file_names_the_dos_folder_but_never_applies_it(tmp_path):
    module, dataset, params = combined(dos_width_ratio=0.5)
    write_plot_file(tmp_path, "bands_dos", params)
    values, warnings = read_plot_file(tmp_path, "bands_dos")
    assert warnings == [] and values is not None
    assert values["dos_folder"] == "../al_pdos_flat" and "atoms" not in values
    fresh = module.default_params(CONFIG, dataset)
    fresh.dos_folder = "../another_dos"  # this session's pair
    assert apply_stored(fresh, values, module.param_schema(dataset)) == []
    assert fresh.dos_width_ratio == 0.5 and fresh.dos_folder == "../another_dos"


def test_the_pair_saved_in_the_bands_folder(demo_project):
    bands, pdos = demo_project / "03_bands", demo_project / "04_pdos"
    sniff = SniffCache().sniff
    assert PairTarget.from_plot_file(bands, sniff) is None
    module, dataset, params = combined(bands, pdos)
    write_plot_file(bands, "bands_dos", params)
    target = PairTarget.from_plot_file(bands, sniff)
    assert target is not None and (target.bands, target.dos) == (bands, pdos)
    target.build()
    pdos.rename(demo_project / "04_moved")
    with pytest.raises(Exception, match="Pasta da DOS não encontrada"):
        target.build()
