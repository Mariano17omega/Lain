import logging

import numpy as np
import pytest
import yaml

from qe_studio.core.calculations.bands import BandsParams
from qe_studio.core.calculations.params import COMMON_FIELDS
from qe_studio.core.calculations.pdos import PdosParams
from qe_studio.core.plotting.plot_file import (
    HEADER,
    apply_stored,
    delete_plot_file,
    plot_file_path,
    read_plot_file,
    write_plot_file,
)


def test_round_trip_bands(tmp_path):
    params = BandsParams(emin=-6.0, xmin=0.5, labels="W, G, X", background="#123456")
    path = write_plot_file(tmp_path, "bands", params)
    assert path == tmp_path / "bands.plot" and path.read_text().startswith(HEADER)
    stored, warnings = read_plot_file(tmp_path, "bands")
    assert warnings == []
    fresh = BandsParams()
    assert apply_stored(fresh, stored) == []
    assert fresh == params and fresh.xmax is None


def test_round_trip_pdos(tmp_path):
    params = PdosParams(
        dos_max=None,
        hidden_series=["Al s"],
        series_colors={"Al p": "#000000"},
        orbital_colors={"s": "#ff0000", "p": "#00ff00", "d": "#0000ff", "f": "#ffffff"},
    )
    write_plot_file(tmp_path, "pdos", params)
    stored, _ = read_plot_file(tmp_path, "pdos")
    fresh = PdosParams()
    apply_stored(fresh, stored)
    assert fresh == params


def test_missing_file_is_silent(tmp_path):
    assert read_plot_file(tmp_path, "bands") == (None, [])


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("lain_plot: 1\nkind: bands\nparams: {emin: [unclosed", "bands.plot inválido"),
        ("- just\n- a list\n", "bands.plot inválido"),
        ("lain_plot: 1\nkind: bands\n", "bands.plot inválido"),
        ("lain_plot: 2\nkind: bands\nparams: {emin: 1}\n", "versão de formato desconhecida"),
        ("lain_plot: 1\nkind: pdos\nparams: {emin: 1}\n", "outro tipo de gráfico"),
    ],
)
def test_unusable_files_are_ignored(tmp_path, text, fragment):
    plot_file_path(tmp_path, "bands").write_text(text)
    stored, warnings = read_plot_file(tmp_path, "bands")
    assert stored is None and len(warnings) == 1 and fragment in warnings[0]


def test_field_validation(caplog):
    params = BandsParams()
    stored = {
        "emin": -4,  # int where float is expected: accepted as float
        "emax": "7",  # wrong type
        "xmin": None,  # optional
        "reference": None,  # not optional
        "show_hs_lines": 1,  # int is not bool
        "legend_loc": "nowhere",  # not a choice
        "valence_color": "notacolor",
        "background": "black",
        "export_dpi": 600,
        "unknown_field": 1,
    }
    with caplog.at_level(logging.DEBUG, logger="qe_studio.core.plotting.plot_file"):
        ignored = apply_stored(params, stored, COMMON_FIELDS)
    assert sorted(ignored) == [
        "emax",
        "legend_loc",
        "reference",
        "show_hs_lines",
        "valence_color",
    ]
    assert params.emin == -4.0 and isinstance(params.emin, float)
    assert (params.emax, params.reference, params.show_hs_lines) == (5.0, "fermi", True)
    assert params.legend_loc == "best" and params.valence_color == "#2563eb"
    assert (params.background, params.export_dpi) == ("black", 600)
    assert "unknown_field" in caplog.text


def test_colour_collections_and_empty_colours():
    params = PdosParams()
    ignored = apply_stored(
        params,
        {
            "series_colors": {"Al s": "nope"},
            "hidden_series": ["Al s", 3],
            "total_color": "",
            "fermi_color": "",
        },
    )
    assert sorted(ignored) == ["fermi_color", "hidden_series", "series_colors"]
    assert params.total_color == "" and params.series_colors == {}


def test_file_is_readable_yaml_and_delete(tmp_path):
    write_plot_file(tmp_path, "bands", BandsParams())
    data = yaml.safe_load(plot_file_path(tmp_path, "bands").read_text())
    assert data["lain_plot"] == 1 and data["kind"] == "bands"
    assert list(data["params"])[:2] == ["title", "figure_width"]
    delete_plot_file(tmp_path, "bands")
    delete_plot_file(tmp_path, "bands")  # already gone: fine
    assert not plot_file_path(tmp_path, "bands").exists()


def test_numpy_values_are_written_as_numbers(tmp_path):
    params = BandsParams(emin=np.float64(-2.5), xmax=np.float64(1.25))
    write_plot_file(tmp_path, "bands", params)
    stored, _ = read_plot_file(tmp_path, "bands")
    assert (stored["emin"], stored["xmax"]) == (-2.5, 1.25)
