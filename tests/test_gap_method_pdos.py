"""Spec 34 R3: the gap method of the PDOS (legend, notes and footer)."""

from pathlib import Path

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands.gap import (
    CLOSED_HOMO_LUMO_NOTE,
    NO_HOMO_LUMO_NOTE,
    NO_WINDOW_GAP_NOTE,
    WINDOW_GAP_MIN_EV,
)
from qe_studio.core.calculations.pdos import PdosDataset
from qe_studio.core.calculations.pdos.gap import GapInfo, gap_for, pdos_gap, printed_pair
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.projwfc import Channel, PdosData, PdosSeries, dos_gap_window
from qe_studio.core.qe.pw_output import PwOutput
from qe_studio.core.sniff import sniff
from test_legend_gap_pdos import ENERGY, GAP_TEXT, STEP, bands_dos, gapped, legend_texts
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

PDOS = next(m for m in REGISTRY if m.kind == "pdos")


def window(data: PdosData, low: float, high: float) -> float | None:
    assert data.total is not None
    return dos_gap_window(data.energy, data.total, low, high, WINDOW_GAP_MIN_EV)


def dataset_of(data: PdosData, fermi=0.6, homo_lumo=None) -> PdosDataset:
    scf = PwOutput(fermi=fermi, fermi_kind="fermi")
    return PdosDataset(
        Path("."), data, fermi, None, gap=pdos_gap(scf, None, data), homo_lumo=homo_lumo
    )


def params_of(dataset: PdosDataset, method: str, **changes):
    params = PDOS.default_params(CONFIG, dataset)
    params.show_legend, params.legend_gap, params.gap_method = True, True, method
    for name, value in changes.items():
        setattr(params, name, value)
    return params


def drawn(dataset: PdosDataset, method: str, **changes):
    figure, info = render(PDOS, dataset, params_of(dataset, method, **changes), LIGHT)
    return [t for t in legend_texts(figure) if t.startswith(GAP_TEXT)], info


# -- dos_gap_window -----------------------------------------------------------------------------
def test_the_gap_inside_the_window_is_found_within_the_grid_step():
    assert window(gapped(), -2.0, 3.0) == pytest.approx(1.2, abs=STEP)
    assert window(gapped(), 3.0, -2.0) == pytest.approx(1.2, abs=STEP)  # flipped window


def test_a_metal_has_none():
    flat = Channel(np.ones_like(ENERGY))
    assert dos_gap_window(ENERGY, flat, -5.0, 5.0, WINDOW_GAP_MIN_EV) is None


def test_a_void_outside_the_window_is_not_seen():
    data = gapped(((3.0, 4.5),))
    assert window(data, -2.0, 2.0) is None
    assert window(data, -2.0, 5.0) == pytest.approx(1.5, abs=STEP)


def test_a_window_narrower_than_the_void_has_none():
    assert window(gapped(), 0.2, 1.0) is None


def test_the_widest_void_in_the_window_wins():
    data = gapped(((0.0, 1.2), (3.0, 3.5)))
    assert window(data, -2.0, 5.0) == pytest.approx(1.2, abs=STEP)
    assert window(data, 2.0, 5.0) == pytest.approx(0.5, abs=STEP)


def test_a_void_reaching_the_grid_edge_is_no_gap():
    data = gapped(((-10.5, -9.0),))
    assert window(data, -11.0, 0.0) is None


def test_a_void_under_the_minimum_width_is_no_gap():
    data = gapped(((0.0, 0.03),))
    assert window(data, -1.0, 1.0) is None


# -- gap_for: the method in force ------------------------------------------------------------------
def test_auto_is_the_gap_the_loader_found():
    dataset = dataset_of(gapped())
    assert dataset.gap is not None
    for method in ("auto", "janela"):
        assert gap_for(dataset, params_of(dataset, method, legend_gap=False)) is dataset.gap
    assert gap_for(dataset, params_of(dataset, "auto")) is dataset.gap


@pytest.mark.parametrize("fermi", [0.6, 0.0, 1.2])
def test_janela_uses_the_window_of_the_plot_around_e_f(fermi):
    dataset = dataset_of(gapped(), fermi=fermi)
    gap = gap_for(dataset, params_of(dataset, "janela", emin=-2.0, emax=2.0))
    assert gap is not None and gap.source == "dos"
    assert gap.value == pytest.approx(1.2, abs=STEP)


def test_janela_in_absolute_energies():
    dataset = dataset_of(gapped(), fermi=0.6)
    params = params_of(dataset, "janela", shift_to_fermi=False, emin=-1.0, emax=1.0)
    assert gap_for(dataset, params) is None  # the gap's top (1.2) is outside
    params.emax = 2.0
    gap = gap_for(dataset, params)
    assert gap is not None and gap.value == pytest.approx(1.2, abs=STEP)


def test_janela_without_a_void_has_the_note():
    dataset = dataset_of(gapped())
    texts, info = drawn(dataset, "janela", emin=-0.4, emax=0.4)
    assert texts == [] and NO_WINDOW_GAP_NOTE in info.notes
    assert "sem gap (na janela)" in info.summary


def test_the_atoms_chosen_do_not_change_the_gap():
    other = Channel(bands_dos((0.0, 3.0)))  # another gap in one atom's projection alone
    total = Channel(bands_dos((0.0, 1.2)))
    series = (
        PdosSeries(1, "Si", 1, "s", None, other),
        PdosSeries(2, "Si", 1, "s", None, total),
    )
    dataset = dataset_of(PdosData(ENERGY, series, total))
    every = gap_for(dataset, params_of(dataset, "janela"))
    assert every is not None
    assert gap_for(dataset, params_of(dataset, "janela", atoms=[1])) == every


# -- homo_lumo -----------------------------------------------------------------------------------
def test_homo_lumo_of_the_si_scf_run():
    scf = sniff(FIXTURES / "si_bands" / "si.scf.out").pw
    assert scf is not None
    pair = printed_pair(scf, None)
    assert pair == (6.3143, 6.8182)
    dataset = dataset_of(gapped(), homo_lumo=pair)
    gap = gap_for(dataset, params_of(dataset, "homo_lumo"))
    assert gap == GapInfo(pytest.approx(0.5039), "homo_lumo")
    texts, info = drawn(dataset, "homo_lumo")
    assert texts == [f"{GAP_TEXT} = 0.504 eV"]
    assert "E_gap (HOMO/LUMO) = 0.504 eV" in info.summary


def test_the_nscf_pair_comes_first():
    scf = PwOutput(fermi=1.0, fermi_kind="homo_lumo", lumo=2.0)
    nscf = PwOutput(fermi=1.1, fermi_kind="homo_lumo", lumo=1.6)
    assert printed_pair(scf, nscf) == (1.1, 1.6)
    assert printed_pair(scf, PwOutput(fermi=1.1, fermi_kind="fermi")) == (1.0, 2.0)


def test_homo_lumo_without_the_pair_has_no_gap_and_the_note():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    assert dataset.homo_lumo is None
    params.show_legend, params.legend_gap, params.gap_method = True, True, "homo_lumo"
    assert gap_for(dataset, params) is None
    figure, info = render(module, dataset, params, LIGHT)
    assert not [t for t in legend_texts(figure) if t.startswith(GAP_TEXT)]
    assert NO_HOMO_LUMO_NOTE in info.notes
    assert "sem gap (HOMO/LUMO)" in info.summary


def test_a_closed_pair_has_its_note():
    dataset = dataset_of(gapped(), homo_lumo=(0.6, 0.6005))
    texts, info = drawn(dataset, "homo_lumo")
    assert texts == [] and CLOSED_HOMO_LUMO_NOTE in info.notes


# -- legend and footer ---------------------------------------------------------------------------
def test_the_legend_and_the_footer_say_the_same():
    dataset = dataset_of(gapped(((0.0, 1.2), (3.0, 4.5))))
    texts, info = drawn(dataset, "janela", emin=-2.0, emax=5.0)
    assert texts == [f"{GAP_TEXT} ≈ 1.50 eV"]
    assert "E_gap (na janela) ≈ 1.50 eV" in info.summary


def test_the_auto_footer_has_no_gap_as_before():
    dataset = dataset_of(gapped())
    _texts, info = drawn(dataset, "auto")
    assert "gap" not in info.summary
    _texts, info = drawn(dataset, "janela", legend_gap=False)
    assert "gap" not in info.summary and info.notes == ()


def test_no_note_with_the_legend_hidden():
    dataset = dataset_of(gapped(), homo_lumo=None)
    _texts, info = drawn(dataset, "homo_lumo", show_legend=False)
    assert info.notes == ()
