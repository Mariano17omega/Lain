"""Opt-in smoke test over the user's own simulation folders.

QE_STUDIO_REAL_DATA=/runs/a:/runs/b uv run pytest -m realdata
"""

import os
from pathlib import Path

import pytest

from qe_studio.core.detection import detect_folder
from qe_studio.core.sniff import sniff

pytestmark = pytest.mark.realdata


def real_folders():
    roots = [Path(p) for p in os.environ.get("QE_STUDIO_REAL_DATA", "").split(os.pathsep) if p]
    for root in roots:
        for folder, dirs, _files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {"tmp", "plots"} and not d.endswith(".save")]
            yield Path(folder)


def test_detection_never_crashes():
    folders = list(real_folders())
    if not folders:
        pytest.skip("QE_STUDIO_REAL_DATA not set")
    for folder in folders:
        detect_folder(folder)


def test_plottable_folders_load_and_render(tmp_path):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from qe_studio.core.calculations.base import LoadError
    from qe_studio.core.config import AppConfig
    from qe_studio.core.plotting.style import DARK

    folders = list(real_folders())
    if not folders:
        pytest.skip("QE_STUDIO_REAL_DATA not set")
    rendered, refused = 0, []
    for folder in folders:
        for result in detect_folder(folder):
            if not result.plottable:
                continue
            try:
                dataset = result.module.load(result, sniff)
            except LoadError as exc:
                refused.append(f"{folder}: {exc}")
                continue
            figure = Figure()
            FigureCanvasAgg(figure)
            params = result.module.default_params(AppConfig(), dataset)
            result.module.render(figure, dataset, params, DARK)
            figure.canvas.draw()
            rendered += 1
    print(f"\nrendered {rendered}; refused {len(refused)}", *refused, sep="\n  ")
    assert rendered
