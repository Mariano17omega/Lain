"""Latency of the figures that are drawn on the GUI thread (spec 27-8 R1, report T2): a 6×6 grid, a
PDOS of many atoms and bands + DOS.

Run with ``uv run pytest -m perf -s tests/test_perf_grid.py`` to see the timings; the baseline is in
the notes of ``specs/Archived/spec_27-8-*.md``. Each case times what ``plot_grid_helpers.draw`` does
(the module's render and the Agg ``canvas.draw()``) on a session built beforehand, the median of
``RUNS``.
"""

from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from atoms_helpers import pdos_folder
from plot_grid_helpers import BANDS, BANDS_DOS, PDOS, RELAX, SCF, draw, grid_of, session_of
from qe_studio.core.plotting.grid import PlotRef
from test_perf_detection import report, timed

# Seconds. The report asks for action above ~1 s for a grid; the simple figures keep the PRD §7
# target. They are absolute budgets with margin for slower machines (the CI perf job never blocks).
BUDGET = {
    "grid_mixed": 1.0,
    "grid_pdos": 1.0,
    "pdos_100_atoms": 0.5,
    "bands_dos": 0.5,
}
RUNS = 3
# The 6×6 grid is over its budget on the GUI thread (spec 27-8 R1: ~2.4 s): only R2 step 3, drawing in
# a worker, fixes it (the cheaper steps reach 2.1 s at best). ``strict``: the day it passes this
# marker must go.
GRID_OVER_BUDGET = pytest.mark.xfail(
    strict=True, reason="spec 27-8 R2 step 3 (render in a worker) is pending"
)
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


@pytest.mark.perf
@GRID_OVER_BUDGET
def test_grid_6x6_of_mixed_plots(grid_mixed):
    seconds = _median(grid_mixed)
    report("grid 6x6 mixed", seconds)
    assert seconds < BUDGET["grid_mixed"]


@pytest.mark.perf
@GRID_OVER_BUDGET
def test_grid_6x6_of_pdos(grid_pdos):
    seconds = _median(grid_pdos)
    report("grid 6x6 pdos", seconds)
    assert seconds < BUDGET["grid_pdos"]


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
