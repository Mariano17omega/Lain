"""The CSV of the plotted data (spec 32 R4): the format, each module's columns, and that they are
what the figure draws."""

import dataclasses

import numpy as np
import pytest

from atoms_helpers import pdos_folder
from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands.table import bands_table
from qe_studio.core.calculations.bands_dos.params import bands_view, dos_view
from qe_studio.core.calculations.pdos.render import series_label
from qe_studio.core.plotting.export import export_files, table_path, write_table
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.plotting.table import BOM, Column, PlotTable, cell, to_csv
from qe_studio.core.qe import projwfc
from qe_studio.core.qe.bands_x import BandData
from spin_helpers import SPIN_BANDS, SPIN_PDOS
from test_bands_dos_render import AL_BANDS, AL_PDOS, combined
from test_plotting import load, render

from conftest import FIXTURES

MODES = ["mirror", "overlay", "up", "down", "sum"]


def names(table: PlotTable) -> list[str]:
    return [column.name for column in table.columns]


# -- the format --------------------------------------------------------------------------------------
def test_csv_has_a_row_of_names_semicolons_and_decimal_commas():
    table = PlotTable.of(
        [
            Column("x (eV)", np.array([0.5, 1.0, -2.25])),
            Column('y; "q"', np.array([1.5e-07, np.nan, np.inf])),
            Column("curta", np.array([3.0])),
        ]
    )
    assert to_csv(table).split("\n") == [
        'x (eV);"y; ""q""";curta',
        "0,5;1,5e-07;3",
        "1;;",  # NaN and the end of a short column are empty cells
        "-2,25;;",
        "",
    ]


def test_a_number_keeps_ten_digits_and_drops_the_rounding_noise_of_a_subtraction():
    assert cell(8.0584 - 12.7941) == "-4,7357"  # -4.7357000000000005 as a float
    assert cell(1 / 3) == "0,3333333333" and cell(-4.123456789012) == "-4,123456789"
    assert cell(1.62e-07) == "1,62e-07" and cell(5.0) == "5" and cell(123456.789) == "123456,789"
    assert cell(np.float32(0.5)) == "0,5" and cell(float("-inf")) == "" and cell(float("nan")) == ""


def test_an_empty_table_is_just_the_names():
    assert to_csv(PlotTable.of([Column("a", np.array([])), Column("b", np.array([]))])) == "a;b\n"


def test_the_file_is_utf8_with_a_byte_order_mark_and_written_whole(tmp_path):
    path = tmp_path / "plots" / "x.csv"
    write_table(path, PlotTable.of([Column("k (2π/alat)", np.array([0.25]))]))
    raw = path.read_bytes()
    assert raw.startswith(BOM.encode()) and raw.decode("utf-8-sig") == "k (2π/alat)\n0,25\n"
    assert not list(path.parent.glob(".*tmp"))


# -- bands -------------------------------------------------------------------------------------------
def test_bands_have_k_then_one_column_per_band_from_the_reference():
    module, dataset, params = load(FIXTURES / "al_bands")
    table = module.table(dataset, params)
    bands = dataset.bands
    assert names(table)[:3] == ["k (2π/alat)", "Banda 1 (E−E_F, eV)", "Banda 2 (E−E_F, eV)"]
    assert len(table.columns) == 1 + bands.n_bands
    np.testing.assert_array_equal(table.columns[0].values, bands.x)
    np.testing.assert_allclose(table.columns[1].values, bands.energies[0] - dataset.fermi)
    params.reference = "absolute"
    table = module.table(dataset, params)
    assert names(table)[1] == "Banda 1 (E, eV)"
    np.testing.assert_array_equal(table.columns[1].values, bands.energies[0])


def test_a_spin_run_has_a_column_per_band_and_channel_shown():
    module, dataset, params = load(SPIN_BANDS)
    n = dataset.bands.n_bands
    both = module.table(dataset, params)
    assert len(both.columns) == 1 + 2 * n  # one k: the two channels share their path
    assert (
        names(both)[1] == "Banda 1 ↑ (E−E_F, eV)" and names(both)[n + 1] == "Banda 1 ↓ (E−E_F, eV)"
    )
    params.spin_channels = "up"
    assert [c for c in names(module.table(dataset, params)) if "↓" in c] == []
    params.spin_channels = "down"
    down = module.table(dataset, params)
    assert names(down)[0] == "k (2π/alat)" and len(down.columns) == 1 + dataset.bands_down.n_bands
    assert all("↓" in c for c in names(down)[1:])


def test_the_down_channel_gets_its_own_k_only_when_its_path_differs():
    module, dataset, params = load(SPIN_BANDS)
    shifted = BandData(dataset.bands_down.x + 0.1, dataset.bands_down.energies)
    table = bands_table(dataclasses.replace(dataset, bands_down=shifted), params)
    n = dataset.bands.n_bands
    assert names(table)[n + 1] == "k ↓ (2π/alat)"
    np.testing.assert_array_equal(table.columns[n + 1].values, shifted.x)
    assert len(table.columns) == 2 + 2 * n


# -- PDOS --------------------------------------------------------------------------------------------
def test_pdos_has_the_energy_then_the_total_and_every_series_drawn():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    table = module.table(dataset, params)
    assert names(table)[0] == "E − E_F (eV)"
    np.testing.assert_allclose(table.columns[0].values, dataset.data.energy - dataset.fermi("scf"))
    assert names(table)[1].startswith("Total") and names(table)[1].endswith("(estados/eV)")
    expected = [series_label(key) for key in projwfc.aggregate(dataset.data, params.grouping)]
    drawn = [n.removesuffix(" (estados/eV)") for n in names(table)[2:]]
    assert drawn == expected and len(drawn) > 1


def test_the_options_that_change_the_figure_change_the_columns():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    full = names(module.table(dataset, params))
    params.show_total = False
    assert len(names(module.table(dataset, params))) == len(full) - 1
    params.hidden_series = [full[2].removesuffix(" (estados/eV)")]
    assert full[2] not in names(module.table(dataset, params))
    params.shift_to_fermi = False
    table = module.table(dataset, params)
    assert names(table)[0] == "E (eV)"
    np.testing.assert_array_equal(table.columns[0].values, dataset.data.energy)


def test_the_atoms_of_a_selection_are_summed_in_the_total(tmp_path):
    folder = pdos_folder(tmp_path, ("Al", "Al", "Al"))
    module, dataset, params = load(folder)
    everything = module.table(dataset, params)
    params.atoms = [3]
    table = module.table(dataset, params)
    assert "Soma dos átomos selecionados (estados/eV)" in names(table)
    ratio = table.columns[2].values / everything.columns[2].values
    assert np.nanmax(np.abs(ratio - 1)) > 0.5  # atom 3 alone is not the sum of the three


@pytest.mark.parametrize("mode", MODES)
def test_the_spin_modes_name_their_channels(mode):
    module, dataset, params = load(SPIN_PDOS)
    params.spin_mode = mode
    column_names = names(module.table(dataset, params))[1:]
    ups = [n for n in column_names if " ↑ (" in n]
    downs = [n for n in column_names if " ↓ (" in n]
    sums = [n for n in column_names if " ↑+↓ (" in n]
    mirrored = [n for n in column_names if n.endswith("espelhado)")]
    count = len(column_names)
    expected = {
        "mirror": (count // 2, count // 2, 0, count // 2),
        "overlay": (count // 2, count // 2, 0, 0),
        "up": (count, 0, 0, 0),
        "down": (0, count, 0, 0),
        "sum": (0, 0, count, 0),
    }[mode]
    assert (len(ups), len(downs), len(sums), len(mirrored)) == expected


def test_a_pdos_without_spin_has_plain_names():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    assert not any("↑" in n or "↓" in n for n in names(module.table(dataset, params)))


# -- bands + DOS -------------------------------------------------------------------------------------
def test_bands_dos_is_the_bands_block_then_the_dos_block_from_the_bands_reference():
    module, dataset, params = combined()
    table = module.table(dataset, params)
    first = bands_table(dataset.bands, bands_view(params))
    assert names(table)[: len(first.columns)] == names(first)
    energy = table.columns[len(first.columns)]
    assert energy.name == "E − E_F (eV)"
    np.testing.assert_allclose(energy.values, dataset.dos.data.energy - dataset.bands.fermi)
    assert table.rows == max(len(c.values) for c in table.columns)
    params.reference = "absolute"
    assert module.table(dataset, params).columns[len(first.columns)].name == "E (eV)"


# -- the table is what the figure draws --------------------------------------------------------------
def assert_bands_are_columns(axes, table: PlotTable) -> None:
    """Every band the axes draw (the segments of their line collections, whatever the group they
    were colored in) is a ``Banda`` column of the table, and the other way round."""
    drawn = sorted(
        tuple(np.round(segment[:, 1], 9))
        for ax in axes
        for collection in ax.collections
        for segment in collection.get_segments()
    )
    columns = sorted(
        tuple(np.round(c.values, 9)) for c in table.columns if c.name.startswith("Banda")
    )
    assert drawn and columns == drawn


@pytest.mark.parametrize("folder", [FIXTURES / "al_bands", FIXTURES / "si_bands", SPIN_BANDS])
@pytest.mark.parametrize("reference", ["fermi", "vbm", "absolute"])
def test_the_band_columns_are_the_drawn_bands(folder, reference):
    module, dataset, params = load(folder)
    params.reference = reference
    figure, _info = render(module, dataset, params, LIGHT)
    assert_bands_are_columns(figure.axes, module.table(dataset, params))


@pytest.mark.parametrize("layout", ["overlay", "side"])
@pytest.mark.parametrize("channels", ["both", "up", "down"])
def test_the_spin_channels_of_the_table_are_those_of_the_figure(layout, channels):
    module, dataset, params = load(SPIN_BANDS)
    params.spin_layout, params.spin_channels = layout, channels
    figure, _info = render(module, dataset, params, LIGHT)
    assert_bands_are_columns(figure.axes, module.table(dataset, params))


def drawn_curves(ax, vertical: bool) -> list[np.ndarray]:
    return [np.asarray(line.get_xdata() if vertical else line.get_ydata()) for line in ax.lines]


def assert_curves_are_columns(ax, table: PlotTable, vertical: bool, start: int = 1) -> None:
    curves = drawn_curves(ax, vertical)
    columns = table.columns[start:]
    assert len(curves) >= len(columns) > 0  # the Fermi / zero lines come after the data
    for curve, column in zip(curves, columns, strict=False):
        np.testing.assert_allclose(column.values, curve, err_msg=column.name)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("vertical", [False, True])
def test_the_pdos_columns_are_the_drawn_curves_of_every_spin_mode(mode, vertical):
    module, dataset, params = load(SPIN_PDOS)
    params.spin_mode = mode
    params.orientation = "vertical" if vertical else "horizontal"
    figure, _info = render(module, dataset, params, LIGHT)
    assert_curves_are_columns(figure.axes[0], module.table(dataset, params), vertical)


def test_the_pdos_columns_follow_the_options_of_the_figure(tmp_path):
    module, dataset, params = load(pdos_folder(tmp_path, ("Al", "Al", "Al")))
    for change in (
        {},
        {"show_total": False},
        {"atoms": [2, 3]},
        {"grouping": "species"},
        {"shift_to_fermi": False},
    ):
        for name, value in change.items():
            setattr(params, name, value)
        figure, _info = render(module, dataset, params, LIGHT)
        table = module.table(dataset, params)
        assert_curves_are_columns(figure.axes[0], table, vertical=False)
        np.testing.assert_allclose(  # the x of every curve is the energy column
            figure.axes[0].lines[0].get_xdata(), table.columns[0].values
        )
    params.hidden_series = [series_label(("Al", "s"))]
    figure, _info = render(module, dataset, params, LIGHT)
    assert_curves_are_columns(figure.axes[0], module.table(dataset, params), vertical=False)


@pytest.mark.parametrize(
    ("bands", "dos"), [(AL_BANDS, AL_PDOS), (SPIN_BANDS, SPIN_PDOS)], ids=["no spin", "spin"]
)
def test_the_two_blocks_of_bands_dos_are_the_two_axes(bands, dos):
    module, dataset, params = combined(bands, dos)
    figure, _info = render(module, dataset, params, LIGHT)
    table = module.table(dataset, params)
    bands_axes, dos_axes = figure.axes
    split = len(bands_table(dataset.bands, bands_view(params)).columns)
    assert_bands_are_columns([bands_axes], PlotTable(table.columns[:split]))
    assert_curves_are_columns(dos_axes, PlotTable(table.columns[split:]), vertical=True)
    assert dos_view(params).orientation == "vertical"


# -- who has a table, and what an export writes ------------------------------------------------------
def test_only_bands_pdos_and_bands_dos_have_a_table():
    assert {m.kind for m in REGISTRY if m.has_table} == {"bands", "pdos", "bands_dos"}
    for module in REGISTRY:
        if not module.has_table:
            assert module.table(None, None) is None  # type: ignore[arg-type]


def test_export_files_writes_the_csv_after_the_figures(tmp_path):
    module, dataset, params = load(FIXTURES / "al_bands")
    written = export_files(module, dataset, params, LIGHT, tmp_path, "p-b-bands", ["png"], 50)
    assert written == [tmp_path / "plots" / "p-b-bands.png", table_path(tmp_path, "p-b-bands")]
    lines = written[1].read_bytes().decode("utf-8-sig").split("\n")
    assert lines[0].startswith("k (2π/alat);Banda 1 (E−E_F, eV);") and ";" in lines[1]
    assert "," in lines[1] and "." not in lines[1]  # decimal commas only
    assert not list((tmp_path / "plots").glob(".*tmp"))


def test_a_module_without_a_table_writes_no_csv(tmp_path):
    module, dataset, params = load(FIXTURES / "si_relax")
    written = export_files(module, dataset, params, LIGHT, tmp_path, "r-relax", ["png"], 50)
    assert [p.name for p in written] == ["r-relax.png"]
    assert not list((tmp_path / "plots").glob("*.csv"))
