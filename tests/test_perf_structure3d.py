"""Frame times of the 3D view (spec 43, notes): ``uv run pytest -m perf -s tests/test_perf_structure3d.py``.

Stacked graphene sheets (1.5 bonds per atom, the proof of concept's scene), a 1000 × 800 frame,
antialiasing, ball and stick, median of 5 frames after a warm-up. Budget: 2 000 atoms ≤ 80 ms, ≤ 50 ms in
draft mode. The frame of "Print" (spec 46 R5: 2× the pixels of a 960 × 780 view, on the GUI thread; the
PNG encoding runs in a worker and is not counted): 2 000 atoms ≤ 200 ms (measured 110 ms).
"""

import statistics
import time

import numpy as np
import pytest
from PyQt6.QtCore import QSize

from qe_studio.core.structure3d.bonds import bonds_for
from qe_studio.ui.widgets.structure3d.canvas import StructureCanvas
from structure3d_helpers import make_structure

D = 1.42  # C–C, Å: honeycomb sheets give exactly 1.5 bonds per atom
LAYER = 3.4
TILING = {500: (5, 5, 5), 2000: (10, 10, 5), 5000: (25, 10, 5)}  # cells x, y, layers (4 atoms each)
BASIS = np.array([[0, 0], [0.5 * D, 0.866025 * D], [1.5 * D, 0.866025 * D], [2 * D, 0]])
BUDGET_MS = {2000: (80.0, 50.0)}  # full, draft
PRINT_VIEW = QSize(960, 780)
PRINT_SCALE = 2
PRINT_BUDGET_MS = 200.0


def honeycomb_stack(n_atoms):
    nx, ny, nz = TILING[n_atoms]
    lx, ly = 3 * D, 3**0.5 * D
    cart = [
        (i * lx + bx, j * ly + by, k * LAYER)
        for i in range(nx)
        for j in range(ny)
        for k in range(nz)
        for bx, by in BASIS
    ]
    cell = np.diag([nx * lx, ny * ly, nz * LAYER])
    cart = np.array(cart)
    return make_structure(cell, cart @ np.linalg.inv(cell), ["C"] * len(cart))


def frame_ms(canvas, draft, repeats=5):
    size = QSize(1000, 800)
    canvas.render_image(size, draft=draft)  # warm-up: fills the brush caches
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        canvas.render_image(size, draft=draft)
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


@pytest.mark.perf
@pytest.mark.parametrize("n_atoms", list(TILING))
def test_frame_times(n_atoms, qapp):
    from qe_studio.ui.theme.manager import ThemeManager

    structure = honeycomb_stack(n_atoms)
    assert len(bonds_for(structure)) / n_atoms == pytest.approx(1.5, abs=0.05)
    canvas = StructureCanvas(ThemeManager("dark"), structure)
    canvas.resize(1000, 800)
    full = frame_ms(canvas, draft=False)
    primitives = canvas.stats.primitives
    draft = frame_ms(canvas, draft=True)
    canvas.options.show_bonds = False
    canvas.refresh_options()
    bare = frame_ms(canvas, draft=False)
    print(
        f"\nPERF N={n_atoms:>5}  prims={primitives:>6}  full={full:6.1f} ms  "
        f"draft={draft:6.1f} ms  no-bonds={bare:6.1f} ms"
    )
    if n_atoms in BUDGET_MS:
        full_budget, draft_budget = BUDGET_MS[n_atoms]
        assert full <= full_budget and draft <= draft_budget


@pytest.mark.perf
def test_the_print_frame_of_2000_atoms(qapp):
    from qe_studio.ui.theme.manager import ThemeManager

    canvas = StructureCanvas(ThemeManager("dark"), honeycomb_stack(2000))
    canvas.resize(PRINT_VIEW)
    canvas.render_image(PRINT_VIEW, dpr=PRINT_SCALE)  # warm-up
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        image = canvas.render_image(PRINT_VIEW, draft=False, dpr=PRINT_SCALE)
        samples.append((time.perf_counter() - started) * 1000)
    assert (image.width(), image.height()) == (PRINT_VIEW.width() * 2, PRINT_VIEW.height() * 2)
    median = statistics.median(samples)
    print(f"\nPERF print frame, 2000 atoms, {image.width()}x{image.height()}: {median:6.1f} ms")
    assert median <= PRINT_BUDGET_MS
