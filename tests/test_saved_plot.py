"""``was_plotted``: what the sidebar "Plot" takes as "plotted before"."""

from __future__ import annotations

from qe_studio.core.plotting.saved import was_plotted


def test_a_new_folder_was_not_plotted(tmp_path):
    (tmp_path / "scf.in").write_text("x")
    assert not was_plotted(tmp_path) and not was_plotted(tmp_path / "missing")


def test_a_plot_file_or_an_exported_figure_counts(tmp_path):
    (tmp_path / "bands.plot").write_text("x")
    assert was_plotted(tmp_path)
    other = tmp_path / "other"
    (other / "plots").mkdir(parents=True)
    (other / "plots" / "other-bands.png").write_bytes(b"")
    assert was_plotted(other)


def test_the_3d_window_and_grids_are_not_plots_of_the_folder(tmp_path):
    (tmp_path / "view3d.plot").write_text("x")
    (tmp_path / "plots").mkdir()
    for name in ("a-scf-3d.png", "a-scf-3d_2.png", "grid_um.png"):
        (tmp_path / "plots" / name).write_bytes(b"")
    assert not was_plotted(tmp_path)
