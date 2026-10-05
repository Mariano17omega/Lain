"""Relax figures against data captured from the code (spec 27-7 R2.5).

``relax_golden.json`` holds the artists of the fixtures that are not a vc-relax, captured before
the vc-relax panels were added: ``both`` / ``energy`` / ``force`` must keep drawing the same. The
vc-relax entries were captured when the enthalpy, pressure and volume panels were written.
``figure_structure`` has no bars, so ``relax_structure`` adds them. Regenerate an entry (``capture``)
only when a figure is *meant* to change.
"""

import json
from pathlib import Path

import pytest
from matplotlib.colors import to_hex

from figure_structure import figure_structure
from qe_studio.core.plotting.style import LIGHT
from test_plotting import load, render

from conftest import FIXTURES

GOLDEN_FILE = Path(__file__).with_name("relax_golden.json")

CASES = {
    "si_relax_both": ("si_relax", {}),
    "si_relax_both_linear": ("si_relax", {"scale": "linear"}),
    "si_relax_energy": ("si_relax", {"panels": "energy"}),
    "si_relax_force": ("si_relax", {"panels": "force"}),
    "si_relax_force_linear": ("si_relax", {"panels": "force", "scale": "linear"}),
    "si_relax_no_thresholds": ("si_relax", {"show_thresholds": False}),
    "kao_slab_relax_both": ("kao_slab_relax", {}),
    "kao_supercell_relax_both": ("kao_supercell_relax", {}),
    # vc-relax: captured with the enthalpy, pressure and volume panels (spec 27-7)
    "kao_vc_relax_both": ("kao_vc_relax", {}),
    "kao_vc_relax_all": ("kao_vc_relax", {"panels": "all"}),
    "kao_vc_relax_all_linear": (
        "kao_vc_relax",
        {"panels": "all", "scale": "linear", "show_thresholds": False},
    ),
}


def relax_structure(figure) -> list[dict]:
    """``figure_structure`` plus the bars and the placeholder texts of each axes."""
    out = figure_structure(figure)
    for ax, entry in zip(figure.axes, out, strict=True):
        entry["bars"] = [
            {
                "x": round(float(p.get_x()), 4),
                "w": round(float(p.get_width()), 4),
                "h": float(f"{p.get_height():.6e}"),
                "color": to_hex(p.get_facecolor()),
            }
            for p in ax.patches
        ]
        entry["texts"] = [t.get_text() for t in ax.texts]
        entry["axis_on"] = ax.axison
        entry["yscale"] = ax.get_yscale()
    return out


def capture(key: str) -> dict:
    """What ``GOLDEN[key]`` holds, as JSON data."""
    folder, settings = CASES[key]
    module, dataset, params = load(FIXTURES / folder)
    for name, value in settings.items():
        setattr(params, name, value)
    figure, info = render(module, dataset, params, LIGHT)
    data = {
        "structure": relax_structure(figure),
        "info": {
            "xlim": [round(float(v), 4) for v in info.xlim],
            "ylim": [round(float(v), 4) for v in info.ylim],
            "summary": info.summary,
            "notes": list(info.notes),
        },
    }
    return json.loads(json.dumps(data))  # tuples → lists, like the file


GOLDEN = json.loads(GOLDEN_FILE.read_text()) if GOLDEN_FILE.exists() else {}


@pytest.mark.parametrize("key", list(CASES))
def test_relax_figure_is_unchanged(key):
    assert key in GOLDEN, f"no golden for {key}: run capture({key!r}) and store it"
    assert capture(key) == GOLDEN[key]
