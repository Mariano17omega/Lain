"""Latency of the figures the window draws (spec 27-8 R1, report T2): a PDOS of many atoms and bands +
DOS, which the GUI thread draws, and a 6×6 grid, which a worker draws (R2 step 3).

Run with ``uv run pytest -m perf -s tests/test_perf_grid.py`` to see the timings; the baseline is in
the notes of ``specs/spec_27-8-*.md``. The simple figures time what ``plot_grid_helpers.draw`` does
(the module's render and the Agg ``canvas.draw()``) on a session built beforehand, the median of
``RUNS``. A grid is timed as the longest stall of the GUI thread (a timer that should tick every
``TICK_MS``) while its tab draws it again, and as the time until the new picture is shown.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer

from atoms_helpers import pdos_folder
from plot_grid_helpers import BANDS, BANDS_DOS, PDOS, RELAX, SCF, draw, grid_of, session_of, settled
from qe_studio.core.plotting.grid import PlotRef
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.plot_view import PlotView
from test_perf_detection import report, timed

# Seconds. The report asks for action when a grid takes over ~1 s of the GUI thread; the simple figures
# keep the PRD §7 target. Absolute budgets with margin for slower machines (the CI perf job never
# blocks). The grid's are the longest stall of the GUI thread and the time to the new picture: the
# worker takes about 2.4 s (the baseline before it was drawn on the GUI thread), the GUI none of it.
BUDGET = {
    "grid_stall": 0.25,
    "grid_latency": 6.0,
    "pdos_100_atoms": 0.5,
    "bands_dos": 0.5,
}
RUNS = 3
TICK_MS = 5
SIDE = 6  # the biggest grid: 6×6 (spec 23)
MIXED = [BANDS, PDOS, RELAX, SCF, BANDS_DOS]


def _grid(refs: list[PlotRef], tmp: Path):
    cells = [
        (row, col, refs[(row * SIDE + col) % len(refs)], f"{row},{col}")
        for row in range(SIDE)
        for col in range(SIDE)
    ]
    return grid_of(cells, tmp, rows=SIDE, cols=SIDE)


def _median(session) -> float:
    return statistics.median(timed(lambda: draw(session)) for _ in range(RUNS))


@pytest.fixture(scope="module")
def grid_mixed(tmp_path_factory):
    return _grid(MIXED, tmp_path_factory.mktemp("perf_grid_mixed"))


@pytest.fixture(scope="module")
def grid_pdos(tmp_path_factory):
    return _grid([PDOS], tmp_path_factory.mktemp("perf_grid_pdos"))


@pytest.fixture(scope="module")
def pdos_100(tmp_path_factory):
    root = tmp_path_factory.mktemp("perf_pdos_100")
    folder = pdos_folder(root, species=("Al",) * 100)
    return session_of(PlotRef(folder, "pdos"), root)


@pytest.fixture(scope="module")
def bands_dos(tmp_path_factory):
    return session_of(BANDS_DOS, tmp_path_factory.mktemp("perf_bands_dos"))


def _redraw(qtbot, session) -> tuple[float, float]:
    """(longest stall of the GUI thread, seconds until the picture is shown) of a shown grid tab
    drawing again."""
    view = PlotView(ThemeManager("dark"), session)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    view.show()
    settled(qtbot, view, timeout=60_000)  # the first drawing, and the resize that follows the show
    last = time.perf_counter()
    stalls = []

    def tick() -> None:
        nonlocal last
        now = time.perf_counter()
        stalls.append(now - last)
        last = now

    timer = QTimer()
    timer.setInterval(TICK_MS)
    timer.timeout.connect(tick)
    timer.start()
    start = last = time.perf_counter()
    with qtbot.waitSignal(view.rendered, timeout=60_000):
        view.render()
    latency = time.perf_counter() - start
    timer.stop()
    view.cancel_load()
    return max(stalls), latency


@pytest.mark.perf
@pytest.mark.parametrize("fixture", ["grid_mixed", "grid_pdos"])
def test_a_6x6_grid_never_stalls_the_gui(qtbot, request, fixture):
    stall, latency = _redraw(qtbot, request.getfixturevalue(fixture))
    report(f"{fixture} gui stall", stall)
    report(f"{fixture} until shown", latency)
    assert stall < BUDGET["grid_stall"]
    assert latency < BUDGET["grid_latency"]


@pytest.mark.perf
def test_pdos_of_100_atoms(pdos_100):
    seconds = _median(pdos_100)
    report("pdos 100 atoms", seconds)
    assert seconds < BUDGET["pdos_100_atoms"]


@pytest.mark.perf
def test_bands_with_dos(bands_dos):
    seconds = _median(bands_dos)
    report("bands + dos", seconds)
    assert seconds < BUDGET["bands_dos"]
