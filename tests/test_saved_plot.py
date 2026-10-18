"""``was_plotted``: what the sidebar "Plot" takes as "plotted before"."""

from __future__ import annotations

from qe_studio.core.plotting.saved import was_plotted


def test_a_new_folder_was_not_plotted(tmp_path):
    (tmp_path / "scf.in").write_text("x")
    assert not was_plotted(tmp_path) and not was_plotted(tmp_path / "missing")


def test_a_plot_file_or_an_exported_figure_counts(tmp_path):
    (tmp_path / "plots").mkdir()
    (tmp_path / "plots" / "bands.plot").write_text("x")
    assert was_plotted(tmp_path)
    other = tmp_path / "other"
    (other / "plots").mkdir(parents=True)
    (other / "plots" / "other-bands.png").write_bytes(b"")
    assert was_plotted(other)


def test_the_3d_window_and_grids_are_not_plots_of_the_folder(tmp_path):
    (tmp_path / "plots").mkdir()
    (tmp_path / "plots" / "view3d.plot").write_text("x")
    for name in ("a-scf-3d.png", "a-scf-3d_2.png", "grid_um.png"):
        (tmp_path / "plots" / name).write_bytes(b"")
    assert not was_plotted(tmp_path)


def test_only_figures_in_plots_count(tmp_path):
    plots = tmp_path / "plots"
    (plots / "old.png").mkdir(parents=True)  # a folder named like a figure
    for name in (".x-bands.png.tmp", "notes.txt", "x-bands.csv", ".hidden.png"):
        (plots / name).write_bytes(b"")
    assert not was_plotted(tmp_path)
    (plots / "x-bands.SVG").write_bytes(b"")
    assert was_plotted(tmp_path)


def test_a_plot_file_outside_plots_does_not_count(tmp_path):
    """Older versions wrote ``<folder>/<kind>.plot``: not read any more, so not a plot either."""
    (tmp_path / "bands.plot").write_text("x")
    assert not was_plotted(tmp_path)


def test_one_kind_counts_only_its_settings_and_figures(tmp_path):
    """The bands + DOS figure of two selected folders lives in the bands folder: whether it was
    plotted before is not whether the bands were."""
    plots = tmp_path / "plots"
    plots.mkdir()
    (plots / "bands.plot").write_text("x")
    (plots / "p-03_bands-bands.png").write_bytes(b"")
    assert was_plotted(tmp_path) and not was_plotted(tmp_path, "bands_dos")
    (plots / "bands_dos.plot").write_text("x")
    assert was_plotted(tmp_path, "bands_dos")
    for name in ("p-03_bands-bands_dos.svg", "p-03_bands-bands_dos_2.png", "bands_dos.pdf"):
        other = tmp_path / name
        (other / "plots").mkdir(parents=True)
        (other / "plots" / name).write_bytes(b"")
        assert was_plotted(other, "bands_dos"), name
        assert not was_plotted(other, "bands"), name
