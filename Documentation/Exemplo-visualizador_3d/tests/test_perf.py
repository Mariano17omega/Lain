"""Frame-time measurements (run with: uv run pytest -m perf -s)."""

import statistics
import time

import numpy as np
import pytest
from helpers import make_structure
from PyQt6.QtCore import QSize

from viewer3d.core.bonds import bonds_for
from viewer3d.core.replicate import build_scene
from viewer3d.ui.canvas import Canvas

D = 1.42  # C-C distance, Å: honeycomb sheets give exactly 1.5 bonds per atom
LAYER = 3.4
# atoms -> (cells along x, cells along y, layers); 4 atoms per rectangular cell
TILING = {100: (5, 5, 1), 500: (5, 5, 5), 2000: (10, 10, 5), 5000: (25, 10, 5), 10000: (25, 20, 5)}
BASIS = np.array([[0, 0], [0.5 * D, 0.866025 * D], [1.5 * D, 0.866025 * D], [2 * D, 0]])


def honeycomb_stack(n_atoms):
    nx, ny, nz = TILING[n_atoms]
    lx, ly = 3 * D, 3**0.5 * D
    cart = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                for bx, by in BASIS:
                    cart.append((i * lx + bx, j * ly + by, k * LAYER + 0.0))
    cell = np.diag([nx * lx, ny * ly, nz * LAYER])
    cart = np.array(cart)
    return make_structure(cell, cart @ np.linalg.inv(cell), ["C"] * len(cart))


def frame_ms(canvas, draft, repeats=5):
    size = QSize(1000, 800)
    canvas.render_image(size, draft=draft)  # warm-up: fills brush caches
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        canvas.render_image(size, draft=draft)
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


@pytest.mark.perf
@pytest.mark.parametrize("n_atoms", list(TILING))
def test_frame_times(n_atoms, qapp):
    structure = honeycomb_stack(n_atoms)
    assert len(structure) == n_atoms
    t0 = time.perf_counter()
    bonds = bonds_for(structure)
    t_bonds = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    build_scene(structure, bonds, (1, 1, 1))
    t_scene = (time.perf_counter() - t0) * 1000
    ratio = len(bonds) / n_atoms
    assert ratio == pytest.approx(1.5, abs=0.05)

    canvas = Canvas()
    canvas.resize(1000, 800)
    canvas.set_structure(structure)
    row = {"n": n_atoms, "bonds": len(bonds), "t_bonds": t_bonds, "t_scene": t_scene}
    for show in (True, False):
        canvas.options.show_bonds = show
        canvas.refresh_options()
        tag = "b" if show else "nb"
        row[f"full_{tag}"] = frame_ms(canvas, draft=False)
        row[f"prims_{tag}"] = canvas.stats.primitives
        row[f"draft_{tag}"] = frame_ms(canvas, draft=True)
    print(
        "\nPERF N={n:>6}  bonds={bonds:>6}  prims(b)={prims_b:>6}  "
        "bonds_ms={t_bonds:7.1f}  scene_ms={t_scene:7.1f}  "
        "full+bonds={full_b:7.1f}  draft+bonds={draft_b:7.1f}  "
        "full-nobonds={full_nb:7.1f}  draft-nobonds={draft_nb:7.1f}".format(**row)
    )
