"""Figures of the no-spin case, and the PDOS mirror, must not change (spec 13 R3.5, R0).

The golden data was captured from the code before ``bands.py`` and ``pdos.py`` were split and before
spin was added, so these tests fail on any drift of the artists: colors, line widths, limits,
ticks, legends. Update it only when a figure is *meant* to change.
"""

import pytest

from figure_structure import figure_structure
from qe_studio.core.plotting.style import LIGHT
from test_plotting import load, render

from conftest import FIXTURES

GOLDEN = {
    "al_bands": {
        "folder": "al_bands",
        "set": {},
        "structure": [
            {
                "xlim": (0.0, 3.2802),
                "ylim": (-5.0, 5.0),
                "xlabel": "",
                "ylabel": "$E - E_F$ (eV)",
                "title": "",
                "xticklabels": ["L", "$\\Gamma$", "X", "U", "$\\Gamma$"],
                "line_collections": [
                    {
                        "segments": 1,
                        "colors": ["#2563eb"],
                        "linewidths": [1.2],
                        "linestyles": [(0.0, None)],
                    },
                    {
                        "segments": 15,
                        "colors": ["#00d2ff"],
                        "linewidths": [1.2],
                        "linestyles": [(0.0, None)],
                    },
                ],
                "lines": [
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 0,
                "legend": None,
            }
        ],
        "info": (
            (0.0, 3.2802),
            (-5.0, 5.0),
            "E_F = 8.0584 eV · metálico · 16 bandas × 91 pontos k",
        ),
    },
    "si_bands": {
        "folder": "si_bands",
        "set": {},
        "structure": [
            {
                "xlim": (0.0, 4.7462),
                "ylim": (-5.0, 5.0),
                "xlabel": "",
                "ylabel": "$E - E_F$ (eV)",
                "title": "",
                "xticklabels": ["", "", "", "", "", "", ""],
                "line_collections": [
                    {
                        "segments": 4,
                        "colors": ["#2563eb"],
                        "linewidths": [1.2],
                        "linestyles": [(0.0, None)],
                    },
                    {
                        "segments": 12,
                        "colors": ["#00d2ff"],
                        "linewidths": [1.2],
                        "linestyles": [(0.0, None)],
                    },
                ],
                "lines": [
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 0,
                "legend": None,
            }
        ],
        "info": (
            (0.0, 4.7462),
            (-5.0, 5.0),
            "HOMO = 6.3143 eV · E_gap (no caminho) = 0.454 eV · 16 bandas × 200 pontos k",
        ),
    },
    "al_pdos": {
        "folder": "al_pdos_flat",
        "set": {},
        "structure": [
            {
                "xlim": (-5.0, 5.0),
                "ylim": (0.0, 0.5929),
                "xlabel": "$E - E_F$ (eV)",
                "ylabel": "PDOS (estados/eV)",
                "title": "",
                "xticklabels": ["−6", "−4", "−2", "0", "2", "4", "6"],
                "line_collections": [],
                "lines": [
                    {"label": "Total", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "Al s", "color": "#e41a1c", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "Al p", "color": "#ec595b", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 3,
                "legend": ["Total", "Al s", "Al p"],
            }
        ],
        "info": ((-5.0, 5.0), (0.0, 0.5929), "E_F = 8.0585 eV (SCF) · 2 projeções · 1 espécies"),
    },
    "al_pdos_vertical": {
        "folder": "al_pdos_flat",
        "set": {"orientation": "vertical"},
        "structure": [
            {
                "xlim": (0.0, 0.5929),
                "ylim": (-5.0, 5.0),
                "xlabel": "PDOS (estados/eV)",
                "ylabel": "$E - E_F$ (eV)",
                "title": "",
                "xticklabels": ["0.0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6"],
                "line_collections": [],
                "lines": [
                    {"label": "Total", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "Al s", "color": "#e41a1c", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "Al p", "color": "#ec595b", "lw": 1.2, "ls": "-", "n": 2261},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 3,
                "legend": ["Total", "Al s", "Al p"],
            }
        ],
        "info": ((0.0, 0.5929), (-5.0, 5.0), "E_F = 8.0585 eV (SCF) · 2 projeções · 1 espécies"),
    },
    "ni_pdos_mirror": {
        "folder": "qe731_ni_spin_pdos",
        "set": {},
        "structure": [
            {
                "xlim": (-5.0, 5.0),
                "ylim": (-2.2248, 2.2248),
                "xlabel": "$E - E_F$ (eV)",
                "ylabel": "PDOS (estados/eV)",
                "title": "",
                "xticklabels": ["−6", "−4", "−2", "0", "2", "4", "6"],
                "line_collections": [],
                "lines": [
                    {"label": "Total", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "Ni s", "color": "#fbbf24", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#fbbf24", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "Ni d", "color": "#a855f7", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#a855f7", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 6,
                "legend": ["Total", "Ni s", "Ni d"],
            }
        ],
        "info": (
            (-5.0, 5.0),
            (-2.2248, 2.2248),
            "E_F = 14.2704 eV (SCF) · 2 projeções · 1 espécies · spin polarizado · M = 0.71 μB/célula",
        ),
    },
    "ni_pdos_mirror_vertical": {
        "folder": "qe731_ni_spin_pdos",
        "set": {"orientation": "vertical"},
        "structure": [
            {
                "xlim": (-2.2248, 2.2248),
                "ylim": (-5.0, 5.0),
                "xlabel": "PDOS (estados/eV)",
                "ylabel": "$E - E_F$ (eV)",
                "title": "",
                "xticklabels": [
                    "−2.5",
                    "−2.0",
                    "−1.5",
                    "−1.0",
                    "−0.5",
                    "0.0",
                    "0.5",
                    "1.0",
                    "1.5",
                    "2.0",
                    "2.5",
                ],
                "line_collections": [],
                "lines": [
                    {"label": "Total", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#0f172a", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "Ni s", "color": "#fbbf24", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#fbbf24", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "Ni d", "color": "#a855f7", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#a855f7", "lw": 1.2, "ls": "-", "n": 202},
                    {"label": "_", "color": "#94a3b8", "lw": 0.7, "ls": "-", "n": 2},
                    {"label": "_", "color": "#f43f5e", "lw": 0.9, "ls": "--", "n": 2},
                ],
                "fills": 6,
                "legend": ["Total", "Ni s", "Ni d"],
            }
        ],
        "info": (
            (-2.2248, 2.2248),
            (-5.0, 5.0),
            "E_F = 14.2704 eV (SCF) · 2 projeções · 1 espécies · spin polarizado · M = 0.71 μB/célula",
        ),
    },
}


@pytest.mark.parametrize("key", list(GOLDEN))
def test_figure_is_unchanged(key):
    case = GOLDEN[key]
    module, dataset, params = load(FIXTURES / case["folder"])
    for name, value in case["set"].items():
        setattr(params, name, value)
    figure, info = render(module, dataset, params, LIGHT)
    xlim, ylim, summary = case["info"]
    assert figure_structure(figure) == case["structure"]
    assert (tuple(round(v, 4) for v in info.xlim), tuple(round(v, 4) for v in info.ylim)) == (
        xlim,
        ylim,
    )
    assert info.summary == summary
