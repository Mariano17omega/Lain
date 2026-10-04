"""Spec 23 R0, R2: drawing into a ``SubFigure``, the grid figure, its parameters and its export."""

import copy

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from plot_grid_helpers import (
    BANDS,
    BANDS_DOS,
    PDOS,
    RELAX,
    SCF,
    draw,
    grid_of,
    session_of,
    stores,
)
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.calculations.params import CommonParams
from qe_studio.core.detection import FolderTarget, ManualTarget, PairTarget, ref_target
from qe_studio.core.plotting.draw import finish, finish_joined, finish_side
from qe_studio.core.plotting.export import export_figure, plan_export
from qe_studio.core.plotting.grid import PlotRef
from qe_studio.core.plotting.plot_file import plot_file_path
from qe_studio.core.plotting.style import LIGHT

from conftest import FIXTURES


def cells_of(figure: Figure):
    """The cell ``SubFigure``s of a grid figure, row-major."""
    return list(figure.subfigs)


# -- R0: the drawing helpers in a SubFigure ---------------------------------------------------------
def test_finishing_a_subfigure_does_not_raise_and_leaves_its_layout_alone():
    figure = Figure(figsize=(6, 3))
    FigureCanvasAgg(figure)
    one, two, three = figure.subfigures(1, 3)
    params = CommonParams(title="t", show_legend=True)
    ax = one.add_subplot()
    ax.plot([0, 1], label="a")
    before = ax.get_position().bounds
    finish(one, ax, params)
    assert ax.get_position().bounds == before  # no tight_layout in a cell
    bare = CommonParams(title="t")  # no legend: the panels below are empty
    finish_side(two, list(two.subplots(1, 2)), bare)
    joined = list(three.subplots(1, 2, gridspec_kw={"wspace": 0}))
    finish_joined(three, joined[1], bare)


# -- R2: every kind of plot in a cell -------------------------------------------------------------
@pytest.mark.parametrize("ref", [BANDS, PDOS, RELAX, SCF, BANDS_DOS], ids=lambda r: r.kind)
def test_a_cell_has_the_axes_of_the_plot_alone(ref, tmp_path):
    alone = len(draw(session_of(ref, tmp_path)).axes)
    grid = grid_of([(0, 1, ref, "")], tmp_path)
    figure = draw(grid)
    empty, cell = cells_of(figure)
    assert len(cell.axes) == alone and not empty.axes


def test_every_cell_fits_its_decorations_inside(tmp_path):
    grid = grid_of(
        [(0, 0, BANDS, "Bandas"), (0, 1, PDOS, ""), (1, 0, RELAX, "Relax"), (1, 1, BANDS_DOS, "")],
        tmp_path,
        rows=2,
    )
    figure = draw(grid)
    for cell in cells_of(figure):
        box = cell.bbox
        for ax in cell.axes:
            tight = ax.get_tightbbox(for_layout_only=True)
            assert tight.x0 >= box.x0 - 1 and tight.x1 <= box.x1 + 1
            assert tight.y0 >= box.y0 - 1 and tight.y1 <= box.y1 + 1
        for text in cell.texts:
            extent = text.get_window_extent()
            assert extent.y1 <= box.y1 + 1 and all(  # the title sits above the axes
                extent.y0 >= ax.get_window_extent().y1 for ax in cell.axes
            )


def test_bands_and_dos_stay_joined_in_a_cell(tmp_path):
    grid = grid_of([(0, 0, BANDS_DOS, "")], tmp_path, cols=1)
    figure = draw(grid)
    bands, dos = figure.axes
    left, right = bands.get_window_extent(), dos.get_window_extent()
    assert right.x0 == pytest.approx(left.x1, abs=1e-6)
    ratio = grid.dataset.cells[0].session.params.dos_width_ratio
    assert right.width / left.width == pytest.approx(ratio, rel=0.02)


def test_the_cell_title_takes_the_place_of_the_plots(tmp_path):
    grid = grid_of([(0, 0, BANDS, "Minha célula"), (0, 1, PDOS, "")], tmp_path)
    for data in grid.dataset.cells:
        data.session.params.title = "Do gráfico"
    figure = draw(grid)
    with_title, without = cells_of(figure)
    assert [t.get_text() for t in with_title.texts] == ["Minha célula"]
    assert with_title.axes[0].get_title() == ""
    assert without.axes[0].get_title() == "Do gráfico" and not without.texts
    assert grid.dataset.cells[0].session.params.title == "Do gráfico"  # drawn from a copy

    grid.params.show_titles = False
    figure = draw(grid)
    assert not cells_of(figure)[0].texts
    assert cells_of(figure)[0].axes[0].get_title() == "Do gráfico"


def test_a_cell_that_did_not_load_says_why(tmp_path):
    grid = grid_of([(0, 0, BANDS, ""), (0, 1, None, "")], tmp_path)
    figure = draw(grid)
    failed = cells_of(figure)[1]
    assert not failed.axes
    (text,) = failed.texts
    assert text.get_text().startswith("Plot indisponível: Pasta não encontrada")
    assert grid.info.notes == (f"Célula (1, 2): Pasta não encontrada: {tmp_path / 'gone'}",)
    assert grid.info.summary == "Grid 1×2 · 1 gráfico"


def test_axes_route_to_their_cell_with_their_own_index(tmp_path):
    grid = grid_of([(0, 0, BANDS, ""), (0, 1, RELAX, "")], tmp_path)
    figure = draw(grid)
    bands, relax = (data.session for data in grid.dataset.cells)
    assert [(owner, index) for owner, index in grid.routes(figure)] == [
        (bands, 0),
        (relax, 0),
        (relax, 1),
    ]


def test_a_plot_routes_its_axes_to_itself(tmp_path):
    session = session_of(RELAX, tmp_path)
    figure = draw(session)
    assert session.routes(figure) == [(session, 0), (session, 1)]


# -- the grid's session and parameters ------------------------------------------------------------
def test_the_grid_session_is_named_and_shows_every_folder(tmp_path):
    grid = grid_of([(0, 0, BANDS, ""), (0, 1, BANDS_DOS, "")], tmp_path, name="Al")
    assert grid.key == "plot:grid:Al" and grid.title == "Grid · Al"
    assert grid.paths == (BANDS.path, BANDS_DOS.path, BANDS_DOS.partner)
    assert grid.composite and grid.folder == tmp_path
    assert grid.params.figure_size == (2 * grid.params.cell_width, grid.params.cell_height)


def test_the_cell_size_makes_the_figure_size(tmp_path):
    grid = grid_of([(0, 0, BANDS, "")], tmp_path, rows=2, cols=3)
    params = grid.params
    params.cell_width = 4.0
    grid.module.param_changed(grid.dataset, params, "cell_width", 6.0)
    assert params.figure_size == (12.0, 2 * params.cell_height)


def test_grid_settings_are_kept_with_the_grid_never_in_a_plot_file(tmp_path):
    bag = stores(tmp_path)
    grid = grid_of([(0, 0, BANDS, "")], tmp_path, stores=bag, name="Al")
    assert bag.grids is not None
    bag.grids.save(grid.dataset.spec)
    grid.params.cell_width, grid.params.background = 4.0, "#000000"
    assert grid.persist("cell_width", bag) and grid.persist("background", bag)
    assert not plot_file_path(tmp_path, "grid").exists()
    assert bag.grids.params("Al")["cell_width"] == 4.0
    assert "name" not in bag.grids.params("Al")  # derived from the definition
    again = grid_of([(0, 0, BANDS, "")], tmp_path, rows=2, stores=bag, name="Al")
    assert again.params.cell_width == 4.0 and again.params.background == "#000000"
    assert again.params.figure_size == (8.0, 2 * again.params.cell_height)
    assert again.defaults.cell_width == 4.0


def test_a_copied_session_is_independent(tmp_path):
    session = session_of(BANDS, tmp_path)
    session.params.emin = -3.0
    twin = session.copy()
    twin.params.emin = -1.0
    assert session.params.emin == -3.0 and twin.defaults == session.defaults
    assert twin.dataset is session.dataset and twin.ref == session.ref == BANDS


# -- reloading a cell's plot ----------------------------------------------------------------------
def test_refs_become_the_targets_that_plot_them_again(tmp_path):
    assert isinstance(ref_target(BANDS, None), FolderTarget)  # type: ignore[arg-type]
    assert isinstance(ref_target(BANDS_DOS, None), PairTarget)  # type: ignore[arg-type]
    scf = ref_target(SCF, None)  # type: ignore[arg-type]
    assert isinstance(scf, ManualTarget) and scf.plot_target == SCF.path
    with pytest.raises(LoadError, match="Arquivo não encontrado"):
        ref_target(PlotRef(tmp_path / "x.out", "scf"), None)  # type: ignore[arg-type]


def test_a_gone_folder_or_kind_is_a_load_error(tmp_path):
    from plot_grid_helpers import SNIFF

    with pytest.raises(LoadError, match="Pasta não encontrada"):
        FolderTarget(tmp_path / "gone", "bands", SNIFF).build()
    with pytest.raises(LoadError, match="Nenhum cálculo de"):
        FolderTarget(FIXTURES / "si_relax", "bands", SNIFF).build()


# -- export ---------------------------------------------------------------------------------------
def test_the_grid_is_exported_into_the_project_plots(tmp_path):
    grid = grid_of([(0, 0, BANDS, "A"), (0, 1, RELAX, "B")], tmp_path, name="Al")
    params = copy.deepcopy(grid.params)
    written = export_figure(
        grid.module, grid.dataset, params, LIGHT, tmp_path, "grid_Al", ["png"], dpi=50
    )
    assert written == [tmp_path / "plots" / "grid_Al.png"] and written[0].stat().st_size > 0
    params.export_svg = params.export_pdf = False
    grid.params = params
    plan = plan_export(grid)
    assert plan.folder == tmp_path and plan.stem == "grid_Al"
    assert plan.existing == written and plan.new_stem == "grid_Al_2"
