"""Spec 34 R1, R2, R5: the gap method of the band structure (legend and footer)."""

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands import BandsDataset, BandsModule
from qe_studio.core.calculations.bands.data import ChannelEdges, band_edges
from qe_studio.core.calculations.bands.gap import (
    CLOSED_HOMO_LUMO_NOTE,
    NO_HOMO_LUMO_NOTE,
    NO_WINDOW_GAP_NOTE,
    WINDOW_GAP_MIN_EV,
    GapEntry,
    gap_entries,
    legend_gap_notes,
    window_gap,
)
from qe_studio.core.calculations.bands.params import BandsParams
from qe_studio.core.calculations.bands_dos.params import BandsDosParams
from qe_studio.core.calculations.params import GAP_METHODS, gap_method_in_force
from qe_studio.core.calculations.pdos.params import PdosParams
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.bands_x import BandData
from qe_studio.core.qe.pw_output import PwOutput
from spin_helpers import SPIN_BANDS
from test_bands_gap_fermi import CBM, ENERGIES, VBM
from test_legend_gap_bands import gap_texts
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

FERMI = -2.8805  # E_F of the user's run (Documentation/Exemplo-bands-010-mehg-O1)
K = np.linspace(0, 1, 9)


def odd_count_energies() -> np.ndarray:
    """Like the user's run: two flat bands 0.072 eV apart at E_F, then an empty 3.764 eV."""
    rows = [
        np.linspace(-4.0, -2.0, len(K)),
        np.linspace(-1.5, -0.3, len(K)),
        np.full(len(K), -0.054),
        np.linspace(0.018, 0.432, len(K)),
        np.linspace(4.196, 5.0, len(K)),
        np.linspace(5.5, 7.0, len(K)),
    ]
    return np.array(rows) + FERMI


def dataset_of(energies: np.ndarray, pw: PwOutput, **kwargs) -> BandsDataset:
    dataset = BandsDataset(
        folder=FIXTURES / "si_bands",
        bands=BandData(np.linspace(0, 1, energies.shape[1]), energies),
        source="gnu",
        fermi=pw.fermi,
        fermi_kind=pw.fermi_kind,
        ticks=[],
        labels=[],
        tick_source="nenhum",
        homo_lumo=pw.homo_lumo,
        **kwargs,
    )
    band_edges(dataset, pw)
    return dataset


def odd_count() -> BandsDataset:
    """495 electrons with smearing: the count fills no whole bands (``fermi_edges``)."""
    return dataset_of(
        odd_count_energies(), PwOutput(fermi=FERMI, fermi_kind="fermi", n_electrons=5)
    )


def params_of(dataset: BandsDataset, method: str, **changes):
    module = BandsModule()
    params = module.default_params(CONFIG, dataset)
    params.show_legend, params.legend_gap, params.gap_method = True, True, method
    for name, value in changes.items():
        setattr(params, name, value)
    return module, params


def drawn(dataset: BandsDataset, method: str, **changes):
    module, params = params_of(dataset, method, **changes)
    figure, info = render(module, dataset, params, LIGHT)
    return gap_texts(figure), info


# -- R1: the field and the method in force -------------------------------------------------------
@pytest.mark.parametrize("params", [BandsParams, PdosParams, BandsDosParams])
def test_the_default_is_auto(params):
    assert params().gap_method == "auto"


@pytest.mark.parametrize("kind", ["bands", "pdos"])
def test_restoring_the_defaults_gives_auto(kind):
    module = next(m for m in REGISTRY if m.kind == kind)
    _, dataset, _ = load(FIXTURES / ("si_bands" if kind == "bands" else "al_pdos_flat"))
    assert module.default_params(CONFIG, dataset).gap_method == "auto"


def test_the_schema_field_is_a_choice_that_needs_the_legend_gap():
    module, dataset, _params = load(FIXTURES / "si_bands")
    schema = [f.name for f in module.param_schema(dataset)]
    assert schema.index("gap_method") == schema.index("legend_gap") + 1
    (field,) = [f for f in module.param_schema(dataset) if f.name == "gap_method"]
    assert (field.section, field.kind, field.requires) == ("legend", "choice", "legend_gap")
    assert [value for value, _ in field.choices] == ["auto", "homo_lumo", "janela"]
    assert [value for value, _ in GAP_METHODS] == ["auto", "homo_lumo", "janela"]


def test_the_method_applies_only_with_the_gap_in_the_legend():
    _module, params = params_of(odd_count(), "janela")
    assert gap_method_in_force(params) == "janela"
    params.legend_gap = False
    assert gap_method_in_force(params) == "auto"
    params.legend_gap, params.gap_method = True, "outro"
    assert gap_method_in_force(params) == "auto"


def test_without_the_gap_in_the_legend_the_footer_is_the_auto_one():
    dataset = odd_count()
    module, params = params_of(dataset, "janela", legend_gap=False)
    _figure, info = render(module, dataset, params, LIGHT)
    assert info.summary == BandsModule.summary(dataset)
    assert "E_gap (no caminho) = 0.072 eV" in info.summary


# -- auto is what there was ----------------------------------------------------------------------
@pytest.mark.parametrize("folder", ["si_bands", "al_bands", "qe731_ni_spin_bands"])
def test_auto_is_the_gap_of_before(folder):
    module, dataset, params = load(FIXTURES / folder)
    params.show_legend, params.legend_gap = True, True
    assert params.gap_method == "auto"
    assert gap_entries(dataset, params) == gap_entries(dataset)
    _figure, info = render(module, dataset, params, LIGHT)
    assert info.summary == BandsModule.summary(dataset)


# -- window_gap ---------------------------------------------------------------------------------
def test_window_gap_of_an_insulator_is_cbm_minus_vbm():
    assert window_gap(ENERGIES, 0.0, -5.0, 5.0) == (VBM, CBM)
    assert window_gap(ENERGIES, 0.0, 5.0, -5.0) == (VBM, CBM)  # the window may come flipped


def test_window_gap_is_relative_to_the_reference():
    assert window_gap(ENERGIES, 2.0, -7.0, 3.0) == (VBM - 2.0, CBM - 2.0)


@pytest.mark.parametrize("window", [(-0.4, 0.9), (1.1, 1.4), (10.0, 20.0)])
def test_a_window_inside_the_gap_or_with_one_level_has_none(window):
    assert window_gap(ENERGIES, 0.0, *window) is None


def test_spacings_under_the_minimum_are_no_gap():
    dense = np.arange(0, 2, WINDOW_GAP_MIN_EV / 2).reshape(1, -1)
    assert window_gap(dense, 0.0, -1.0, 3.0) is None
    assert window_gap(np.array([[0.0, WINDOW_GAP_MIN_EV]]), 0.0, -1.0, 1.0) == pytest.approx(
        (0.0, WINDOW_GAP_MIN_EV)
    )


# -- janela on the odd count of the user's run ------------------------------------------------
def test_the_odd_count_gets_the_wide_empty_interval_not_the_flat_bands():
    dataset = odd_count()
    assert dataset.gap == pytest.approx(0.072) and dataset.gap_note  # auto: fermi_edges
    texts, info = drawn(dataset, "janela", emin=-2.0, emax=8.0)
    assert gap_entries(dataset, params_of(dataset, "janela", emin=-2.0, emax=8.0)[1]) == [
        GapEntry(None, pytest.approx(3.764))
    ]
    assert texts == ["$E_{gap}$ = 3.764 eV"]
    assert "E_gap (na janela) = 3.764 eV" in info.summary
    assert info.notes == ()  # the note on the counted gap is about auto only


def test_auto_keeps_the_note_of_the_odd_count():
    texts, info = drawn(odd_count(), "auto", emin=-2.0, emax=8.0)
    assert texts == ["$E_{gap}$ = 0.072 eV"]
    assert info.notes == (odd_count().gap_note,)


def test_a_window_narrower_than_the_void_has_no_gap_and_the_note():
    texts, info = drawn(odd_count(), "janela", emin=1.0, emax=4.0)
    assert texts == []
    assert NO_WINDOW_GAP_NOTE in info.notes
    assert "sem gap (na janela)" in info.summary


def test_the_reference_does_not_change_the_window_gap():
    dataset = odd_count()
    module, params = params_of(dataset, "janela", emin=-2.0, emax=8.0)
    before = gap_entries(dataset, params)
    params.reference, old = "absolute", params.reference
    module.param_changed(dataset, params, "reference", old)  # keeps the visible window
    assert params.emin == pytest.approx(-2.0 + FERMI)
    assert gap_entries(dataset, params) == [GapEntry(None, pytest.approx(before[0].value))]


# -- homo_lumo -----------------------------------------------------------------------------------
def test_the_printed_pair_of_pw_output():
    assert PwOutput(fermi=6.3, fermi_kind="homo_lumo", lumo=6.8).homo_lumo == (6.3, 6.8)
    assert PwOutput(fermi=6.3, fermi_kind="fermi").homo_lumo is None
    assert PwOutput(fermi=6.3, fermi_kind="homo").homo_lumo is None


def test_homo_lumo_is_the_printed_pair_not_the_path():
    module, dataset, params = load(FIXTURES / "si_bands")
    assert dataset.homo_lumo == (6.3143, 6.8182)
    params.show_legend, params.legend_gap, params.gap_method = True, True, "homo_lumo"
    assert gap_entries(dataset, params) == [GapEntry(None, pytest.approx(0.5039))]
    figure, info = render(module, dataset, params, LIGHT)
    assert gap_texts(figure) == ["$E_{gap}$ = 0.504 eV"]
    assert "E_gap (HOMO/LUMO) = 0.504 eV" in info.summary


def test_homo_lumo_of_a_synthetic_run():
    pw = PwOutput(fermi=VBM, fermi_kind="homo_lumo", lumo=VBM + 1.2, n_electrons=4)
    texts, info = drawn(dataset_of(ENERGIES, pw), "homo_lumo")
    assert texts == ["$E_{gap}$ = 1.200 eV"] and info.notes == ()


def test_without_the_printed_pair_there_is_no_gap_and_the_note():
    texts, info = drawn(odd_count(), "homo_lumo")
    assert texts == []
    assert NO_HOMO_LUMO_NOTE in info.notes
    assert "sem gap (HOMO/LUMO)" in info.summary


def test_a_closed_printed_pair_is_no_gap():
    pw = PwOutput(fermi=VBM, fermi_kind="homo_lumo", lumo=VBM + 0.0005, n_electrons=4)
    texts, info = drawn(dataset_of(ENERGIES, pw), "homo_lumo")
    assert texts == [] and CLOSED_HOMO_LUMO_NOTE in info.notes


def test_notes_only_with_a_visible_legend():
    dataset = odd_count()
    _module, params = params_of(dataset, "homo_lumo", show_legend=False)
    assert legend_gap_notes(dataset, params) == ()


# -- spin ----------------------------------------------------------------------------------------
UP = np.array([[-2.0, -1.0], [1.0, 2.0]])  # window gap 2.0 (from -1 to 1)
DOWN = np.array([[-1.2, -0.5], [0.5, 1.2]])  # window gap 1.0 (from -0.5 to 0.5)


def spin_dataset(down: np.ndarray | None = DOWN, **kwargs) -> BandsDataset:
    k = np.linspace(0, 1, 2)
    return BandsDataset(
        folder=SPIN_BANDS,
        bands=BandData(k, UP),
        source="gnu",
        fermi=0.0,
        fermi_kind="fermi",
        ticks=[],
        labels=[],
        tick_source="nenhum",
        bands_down=None if down is None else BandData(k, down),
        **kwargs,
    )


def test_janela_per_channel_and_global():
    dataset = spin_dataset()
    _module, params = params_of(dataset, "janela")
    assert gap_entries(dataset, params) == [
        GapEntry("up", pytest.approx(2.0)),
        GapEntry("down", pytest.approx(1.0)),
        GapEntry("global", pytest.approx(1.0)),  # max(-1, -0.5) to min(1, 0.5)
    ]
    texts, info = drawn(dataset, "janela")
    assert texts == [
        "$E_{gap}$ ↑ = 2.000 eV",
        "$E_{gap}$ ↓ = 1.000 eV",
        "$E_{gap}$ global = 1.000 eV",
    ]
    assert "gap ↑ (na janela) 2.000 eV" in info.summary
    assert "gap global (na janela) 1.000 eV" in info.summary


def test_janela_with_one_channel_without_gap_has_no_global():
    dataset = spin_dataset()
    dense = np.arange(-6, 6, 0.01).reshape(2, -1)  # spacings of 0.01 eV: no gap in ↓
    dataset.bands_down = BandData(np.linspace(0, 1, dense.shape[1]), dense)
    _module, params = params_of(dataset, "janela")
    assert gap_entries(dataset, params) == [GapEntry("up", pytest.approx(2.0))]


def test_janela_of_a_run_with_the_up_channel_only():
    dataset = spin_dataset(None, edges={"up": ChannelEdges(0.0, -1.0, 1.0)})
    _module, params = params_of(dataset, "janela")
    assert gap_entries(dataset, params) == [GapEntry("up", pytest.approx(2.0))]


def test_homo_lumo_with_spin_is_one_entry():
    dataset = spin_dataset(homo_lumo=(-0.5, 0.7))
    texts, info = drawn(dataset, "homo_lumo")
    assert texts == ["$E_{gap}$ = 1.200 eV"]
    assert "spin polarizado · E_gap (HOMO/LUMO) = 1.200 eV" in info.summary


# -- R5: kept in bands.plot ----------------------------------------------------------------------
def test_the_method_is_saved_and_restored(tmp_path):
    module, dataset, params = load(FIXTURES / "si_bands")
    params.legend_gap, params.gap_method = True, "janela"
    write_plot_file(tmp_path, "bands", params)
    values, warnings = read_plot_file(tmp_path, "bands")
    assert warnings == [] and values is not None and values["gap_method"] == "janela"
    fresh = module.default_params(CONFIG, dataset)
    assert apply_stored(fresh, values, module.param_schema(dataset)) == []
    assert fresh.gap_method == "janela"


def test_an_unknown_stored_method_falls_back_to_auto():
    module, dataset, _params = load(FIXTURES / "si_bands")
    fresh = module.default_params(CONFIG, dataset)
    apply_stored(fresh, {"gap_method": "maior"}, module.param_schema(dataset))
    assert fresh.gap_method == "auto"
