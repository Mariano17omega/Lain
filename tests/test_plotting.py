import shutil
import time
from pathlib import Path

import matplotlib
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.image import imread

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.bands import merged_ticks
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.export import (
    existing_targets,
    export_figure,
    next_free_stem,
)
from qe_studio.core.plotting.style import DARK, LIGHT, figure_style
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES, copy_fixture

CONFIG = AppConfig()


def load(folder: Path):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    dataset = result.module.load(result)
    return result.module, dataset, result.module.default_params(CONFIG, dataset)


def render(module, dataset, params, style=DARK):
    figure = Figure(figsize=params.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(style.rc(params.font_size)):
        info = module.render(figure, dataset, params, style)
    figure.canvas.draw()
    return figure, info


# -- bands ---------------------------------------------------------------------------------------
def test_al_bands_dataset():
    _, ds, params = load(FIXTURES / "al_bands")
    assert ds.source == "gnu" and ds.tick_source == "entrada"
    assert ds.fermi == 8.0584 and ds.fermi_kind == "fermi"
    np.testing.assert_allclose(ds.ticks, [0.0, 0.866, 1.866, 2.2196, 3.2802], atol=1e-4)
    assert ds.labels == ["L", "G", "X", "U", "G"]
    assert ds.gap is None  # metal: 3 electrons
    assert params.reference == "fermi" and (params.emin, params.emax) == (-5.0, 5.0)
    assert ds.formula == "Al"


def test_si_bands_gap_and_bandsx_ticks():
    module, ds, _ = load(FIXTURES / "si_bands")
    assert ds.tick_source == "bands.x" and len(ds.ticks) == 7
    assert ds.labels == [""] * 7
    assert ds.n_occupied == 4
    assert ds.vbm == pytest.approx(6.3142, abs=1e-3)
    assert ds.gap == pytest.approx(0.454, abs=0.01)
    assert "E_gap = 0.45" in module.summary(ds)
    assert ds.reference("midgap") == pytest.approx((ds.vbm + ds.cbm) / 2)
    assert ds.reference("absolute") == 0.0


def test_bands_render():
    module, ds, params = load(FIXTURES / "al_bands")
    figure, info = render(module, ds, params)
    ax = figure.axes[0]
    assert ax.get_ylim() == (-5.0, 5.0)
    assert [t.get_text() for t in ax.get_xticklabels()] == ["L", r"$\Gamma$", "X", "U", r"$\Gamma$"]
    collections = [c for c in ax.collections if isinstance(c, LineCollection)]
    assert sum(len(c.get_segments()) for c in collections) == 16
    assert info.xlim == pytest.approx((0.0, 3.2802))
    assert "E_F = 8.0584" in info.summary


def test_bands_reference_change_keeps_window():
    module, ds, params = load(FIXTURES / "si_bands")
    old = params.reference
    params.reference = "absolute"
    module.param_changed(ds, params, "reference", old)
    assert params.emin == pytest.approx(-5.0 + ds.fermi)
    params.reference = "midgap"
    module.param_changed(ds, params, "reference", "absolute")
    assert params.emin == pytest.approx(-5.0 + ds.fermi - ds.reference("midgap"))


def test_bands_label_override_and_merge():
    module, ds, params = load(FIXTURES / "si_bands")
    params.labels = "L, G, X, W, L, K"
    labels = module.tick_labels(ds, params)
    assert labels[:2] == ["L", r"$\Gamma$"] and labels[-1] == ""
    ticks, merged = merged_ticks([0.0, 1.0, 1.0, 2.0], ["A", "B", "C", "D"])
    assert ticks == [0.0, 1.0, 2.0] and merged == ["A", "B|C", "D"]


def test_bands_fallback_sources(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    (folder / "bands.dat.gnu").unlink()
    _, ds, _ = load(folder)
    assert ds.source == "filband" and ds.tick_source == "entrada"
    (folder / "bands.dat").unlink()
    (folder / "bands.out").unlink()
    _, ds, _ = load(folder)
    assert ds.source == "pw"  # al.band.out has 91 k-points with printed eigenvalues
    assert ds.bands.energies.shape == (16, 91)


def test_bands_without_eigenvalues_raises(tmp_path):
    folder = tmp_path / "si"
    folder.mkdir()
    for name in ("si.scf.out", "si.band.in", "si.band.out"):
        shutil.copy(FIXTURES / "si_bands" / name, folder / name)
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    with pytest.raises(LoadError, match="bands.x"):
        result.module.load(result)


# -- pdos ----------------------------------------------------------------------------------------
def test_pdos_render_horizontal(al_pdos_orbitals):
    module, ds, params = load(al_pdos_orbitals)
    assert ds.fermi("scf") == 8.0585 and ds.fermi("nscf") == 7.9421
    figure, info = render(module, ds, params, LIGHT)
    ax = figure.axes[0]
    labels = [line.get_label() for line in ax.get_lines() if not line.get_label().startswith("_")]
    assert labels == ["Total", "Al s", "Al p"]
    assert ax.get_xlim() == (-5.0, 5.0)
    assert ax.get_ylim()[0] == 0.0 and ax.get_ylim()[1] > 0
    assert "E_F = 8.0585 eV (SCF)" in info.summary


def test_pdos_options(al_pdos_orbitals):
    module, ds, params = load(al_pdos_orbitals)
    params.orientation = "vertical"
    params.grouping = "species"
    params.hidden_series = ["Al"]
    params.dos_max = 2.0
    figure, info = render(module, ds, params)
    ax = figure.axes[0]
    assert [ln.get_label() for ln in ax.get_lines() if not ln.get_label().startswith("_")] == [
        "Total"
    ]
    assert ax.get_xlim() == (0.0, 2.0) and ax.get_ylim() == (-5.0, 5.0)

    old = params.fermi_source
    params.fermi_source = "nscf"
    module.param_changed(ds, params, "fermi_source", old)
    assert params.emin == pytest.approx(-5.0 + 8.0585 - 7.9421)


def test_pdos_spin_mirrors_down_channel():
    module, ds, params = load(FIXTURES / "qe731_ni_spin_pdos")
    figure, _ = render(module, ds, params)
    low, high = figure.axes[0].get_ylim()
    assert low == -high < 0


def test_pdos_species_colors_differ():
    module, ds, params = load(FIXTURES / "qe731_ni_spin_pdos")
    colors = module.series_colors(ds, params, DARK)
    assert colors == {"Ni s": "#fbbf24", "Ni d": "#a855f7"}
    params.series_colors = {"Ni d": "#000000"}
    assert module.series_colors(ds, params, DARK)["Ni d"] == "#000000"


# -- export --------------------------------------------------------------------------------------
def test_export_formats_and_size(tmp_path):
    module, ds, params = load(FIXTURES / "al_bands")
    params.figure_width, params.figure_height = 4.0, 3.0
    written = export_figure(
        module, ds, params, LIGHT, tmp_path, "bands", ["png", "svg", "pdf"], 300
    )
    assert [p.name for p in written] == ["bands.png", "bands.svg", "bands.pdf"]
    assert all(p.parent == tmp_path / "plots" and p.stat().st_size > 0 for p in written)
    height, width, _ = imread(written[0]).shape
    assert (width, height) == (1200, 900)
    assert b"<svg" in written[1].read_bytes()[:500]
    assert written[2].read_bytes().startswith(b"%PDF")
    assert not list((tmp_path / "plots").glob(".*tmp"))


def test_versioning(tmp_path):
    formats = ["png", "pdf"]
    assert existing_targets(tmp_path, "bands", formats) == []
    (tmp_path / "plots").mkdir()
    (tmp_path / "plots" / "bands.pdf").write_text("x")
    assert [p.name for p in existing_targets(tmp_path, "bands", formats)] == ["bands.pdf"]
    assert next_free_stem(tmp_path, "bands", formats) == "bands_2"
    (tmp_path / "plots" / "bands_2.png").write_text("x")
    assert next_free_stem(tmp_path, "bands", formats) == "bands_3"


def test_figure_style_follows_the_background():
    white, black = figure_style("#ffffff"), figure_style("#000000")
    assert (white.text, white.guide, white.figure_bg) == (LIGHT.text, LIGHT.guide, "#ffffff")
    assert (black.text, black.palette, black.axes_bg) == (DARK.text, DARK.palette, "#000000")
    navy = figure_style("#123456")
    assert navy.text == DARK.text and navy.figure_bg == navy.axes_bg == "#123456"


def test_export_background(tmp_path):
    module, ds, params = load(FIXTURES / "al_bands")
    assert params.background == "#ffffff"
    (png,) = export_figure(
        module, ds, params, figure_style(params.background), tmp_path, "a", ["png"], 50
    )
    assert matplotlib.colors.to_hex(imread(png)[0, 0]) == "#ffffff"
    params.background = "#123456"
    style = figure_style(params.background)
    png, svg = export_figure(module, ds, params, style, tmp_path, "b", ["png", "svg"], 50)
    assert matplotlib.colors.to_hex(imread(png)[0, 0]) == "#123456"
    assert "fill: #123456" in svg.read_text()


def test_pdos_palette_follows_the_background():
    module, ds, params = load(FIXTURES / "qe731_ni_spin_pdos")
    params.grouping = "species"
    light = module.series_colors(ds, params, figure_style("#ffffff"))
    dark = module.series_colors(ds, params, figure_style("#000000"))
    assert list(light.values()) == [LIGHT.palette[0]]
    assert list(dark.values()) == [DARK.palette[0]]


def test_load_cache_reuses_dataset():
    (result,) = detect_folder(FIXTURES / "al_bands", sniff=SniffCache().sniff)
    module = module_for("bands")
    assert module.load_cached(result) is module.load_cached(result)


# -- performance (NFR §7: < 500 ms for up to 100 bands) ------------------------------------------
@pytest.mark.perf
def test_hundred_bands_load_and_render_under_budget(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    x = np.linspace(0, 3.2802, 91)
    blocks = [
        "\n".join(
            f"{xi:10.4f}{e:10.4f}" for xi, e in zip(x, 5 * np.sin(x + b) + b / 5, strict=True)
        )
        for b in range(100)
    ]
    (folder / "bands.dat.gnu").write_text("\n\n".join(blocks) + "\n")
    (folder / "bands.dat").unlink()
    (folder / "bands.out").unlink()
    (folder / "al.band.out").unlink()
    start = time.perf_counter()
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    dataset = result.module.load(result)
    assert dataset.bands.n_bands == 100
    params = result.module.default_params(CONFIG, dataset)
    render(result.module, dataset, params)
    assert time.perf_counter() - start < 0.5
