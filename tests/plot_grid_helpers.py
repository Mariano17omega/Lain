"""Sessions of real fixture plots and grids made of them (spec 23 tests). Not ``grid_helpers.py``:
that one is the file grid's."""

from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations.base import Stores
from qe_studio.core.calculations.grid import GridCellData
from qe_studio.core.compounds import CompoundStore
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import ref_target
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting.grid import GridCell, GridSpec, PlotRef
from qe_studio.core.plotting.grid_session import build_grid_session
from qe_studio.core.plotting.session import build_session, load_plot
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES

CONFIG = AppConfig()
SNIFF = SniffCache().sniff

BANDS = PlotRef(FIXTURES / "al_bands", "bands")
PDOS = PlotRef(FIXTURES / "al_pdos_flat", "pdos")
RELAX = PlotRef(FIXTURES / "si_relax", "relax")
SCF = PlotRef(FIXTURES / "al_bands" / "al.scf.out", "scf")
BANDS_DOS = PlotRef(FIXTURES / "al_bands", "bands_dos", FIXTURES / "al_pdos_flat")


def memory(tmp: Path) -> FolderMemory:
    return FolderMemory(tmp / "folders.json")


def session_of(ref: PlotRef, tmp: Path):
    result, dataset = load_plot(ref_target(ref, SNIFF), SNIFF)
    session, _warnings = build_session(result, dataset, CONFIG, (None, []), memory(tmp))
    return session


def grid_of(
    cells: list[tuple[int, int, PlotRef | None, str]],
    tmp: Path,
    rows=1,
    cols=2,
    name="g",
    stores: Stores | None = None,
):
    """The grid session of ``cells`` (row, col, ref, title); a ref None is a cell that failed."""
    data = []
    for row, col, ref, title in cells:
        cell = GridCell(row, col, ref or PlotRef(tmp / "gone", "bands"), title)
        if ref is None:
            data.append(GridCellData(cell, None, f"Pasta não encontrada: {tmp / 'gone'}"))
        else:
            data.append(GridCellData(cell, session_of(ref, tmp)))
    spec = GridSpec(name, rows, cols, [d.cell for d in data])
    return build_grid_session(spec, data, tmp, CONFIG, memory(tmp), stores)


def stores(tmp: Path) -> Stores:
    from qe_studio.core.grid_store import GridStore

    return Stores(CompoundStore(tmp / "compounds.json"), GridStore(tmp / "grids.json", tmp))


def draw(session, dpi: float = 72) -> Figure:
    figure = Figure(figsize=session.params.figure_size, dpi=dpi)
    FigureCanvasAgg(figure)
    session.render(figure, session.style)
    figure.canvas.draw()
    return figure
