"""The energy gap of a PDOS and its legend entry (spec 20, R4)."""

import dataclasses
import shutil
from pathlib import Path

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands.data import EDGE_TOL
from qe_studio.core.calculations.pdos import PdosDataset
from qe_studio.core.calculations.pdos.gap import GapInfo, pdos_gap
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe import projwfc
from qe_studio.core.qe.projwfc import Channel, PdosData, PdosSeries, dos_gap
from qe_studio.core.qe.pw_output import PwOutput
from qe_studio.core.sniff import sniff
from spin_helpers import SPIN_PDOS
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

STEP = 0.01  # eV, the DeltaE of projwfc.x
ENERGY = np.arange(-1000, 1001) * STEP
MODES = ["mirror", "overlay", "up", "down", "sum"]
GAP_TEXT = "$E_{gap}$"


def bands_dos(*gaps: tuple[float, float]) -> np.ndarray:
    """A DOS of 1 state/eV everywhere except inside each ``(low, high)`` gap, where it is 0."""
    dos = np.ones_like(ENERGY)
    for low, high in gaps:
        dos[(ENERGY - low > STEP / 2) & (high - ENERGY > STEP / 2)] = 0.0
    return dos


def gapped(up=((0.0, 1.2),), down=None) -> PdosData:
    channel = Channel(bands_dos(*up), None if down is None else bands_dos(*down))
    series = PdosSeries(1, "Si", 1, "s", None, channel)
    return PdosData(ENERGY, (series,), channel)


def pw(fermi=0.6, kind="fermi", lumo=None) -> PwOutput:
    return PwOutput(fermi=fermi, fermi_kind=kind, lumo=lumo)


def dataset_of(data: PdosData, **pw_kwargs) -> PdosDataset:
    scf = pw(**pw_kwargs)
    return PdosDataset(Path("."), data, scf.fermi, None, gap=pdos_gap(scf, None, data))


def legend_texts(figure) -> list[str]:
    legend = figure.axes[0].get_legend()
    return [] if legend is None else [t.get_text() for t in legend.get_texts()]


# -- dos_gap: the gap read off the curve --------------------------------------------------------
def test_a_gap_with_fermi_in_the_middle_is_found_within_the_grid_step():
    value = dos_gap(ENERGY, gapped().total, 0.6)
    assert value == pytest.approx(1.2, abs=STEP)


@pytest.mark.parametrize("fermi", [0.0, 1.2, -0.2, 1.4])
def test_fermi_on_the_edge_of_the_gap_or_just_inside_a_band_still_finds_it(fermi):
    assert dos_gap(ENERGY, gapped().total, fermi) == pytest.approx(1.2, abs=STEP)


@pytest.mark.parametrize("fermi", [-3.0, 5.0, -1.5, 2.8])
def test_fermi_deep_inside_a_band_is_a_metal(fermi):
    assert dos_gap(ENERGY, gapped().total, fermi) is None


@pytest.mark.parametrize("fermi", [-0.9, -0.5, 1.8, 2.1])
def test_fermi_a_few_tenths_inside_a_band_still_finds_the_gap(fermi):
    # Smearing puts E_F in the top of the valence band (real PDOS: 0.3-0.5 eV below the gap).
    assert dos_gap(ENERGY, gapped().total, fermi) == pytest.approx(1.2, abs=STEP)


def test_the_widest_region_near_fermi_wins():
    total = gapped(up=((0.0, 0.5), (1.0, 2.5))).total  # 0.5 eV and 1.5 eV, E_F between them
    assert dos_gap(ENERGY, total, 0.75) == pytest.approx(1.5, abs=STEP)
    assert dos_gap(ENERGY, total, 0.25) == pytest.approx(1.5, abs=STEP)  # 0.75 eV from it


def test_a_region_further_than_the_search_is_ignored_for_a_nearer_one():
    total = gapped(up=((0.0, 0.5), (4.0, 6.0))).total  # the wide one is 3.5 eV from E_F
    assert dos_gap(ENERGY, total, 0.25) == pytest.approx(0.5, abs=STEP)


def test_an_edge_region_is_no_candidate_but_does_not_hide_another():
    dos = np.where(ENERGY < -9.5, 0.0, bands_dos((0.0, 1.2)))  # empty from the grid start to -9.5
    assert dos_gap(ENERGY, Channel(dos), -9.0) is None  # only the edge region is near
    assert dos_gap(ENERGY, Channel(dos), 0.6) == pytest.approx(1.2, abs=STEP)


def test_without_a_fermi_energy_there_is_no_gap():
    assert dos_gap(ENERGY, gapped().total, None) is None


def test_a_region_reaching_the_grid_edge_has_no_states_on_one_side():
    total = Channel(np.where(ENERGY < 0, 0.0, 1.0))  # nothing below 0: the grid starts empty
    assert dos_gap(ENERGY, total, -9.0) is None
    total = Channel(np.where(ENERGY > 1.2, 0.0, 1.0))  # and nothing above 1.2
    assert dos_gap(ENERGY, total, 5.0) is None


def test_an_all_zero_curve_has_no_gap():
    assert dos_gap(ENERGY, Channel(np.zeros_like(ENERGY)), 0.0) is None


def test_the_two_spin_channels_are_summed():
    spin = gapped(up=((0.0, 1.2),), down=((0.4, 1.0),)).total
    assert dos_gap(ENERGY, Channel(spin.up), 0.7) == pytest.approx(1.2, abs=STEP)
    assert dos_gap(ENERGY, spin, 0.7) == pytest.approx(0.6, abs=STEP)  # only where both are empty


def test_a_smeared_edge_narrows_the_gap_by_its_tail():
    # The faint tail of a Gaussian edge stays above the threshold for about 3 sigma: the curve says
    # less than the true 1.2 eV, which is why a gap read off a curve is shown with "≈".
    kernel = np.exp(-((np.arange(-30, 31) * STEP) ** 2) / (2 * 0.04**2))
    smeared = np.convolve(bands_dos((0.0, 1.2)), kernel / kernel.sum(), mode="same")
    value = dos_gap(ENERGY, Channel(smeared), 0.6)
    assert value is not None and 0.9 < value < 1.2


def test_metals_have_no_gap():
    for folder in (FIXTURES / "al_pdos_flat", SPIN_PDOS):
        assert load(folder)[1].gap is None


# -- pdos_gap: which source wins ----------------------------------------------------------------
def test_the_homo_and_lumo_pw_printed_are_the_exact_gap():
    scf = sniff(FIXTURES / "si_bands" / "si.scf.out").pw
    assert scf is not None and scf.fermi_kind == "homo_lumo"
    gap = pdos_gap(scf, None, gapped())
    assert gap == GapInfo(pytest.approx(6.8182 - 6.3143), "homo_lumo")


def test_the_nscf_run_wins_over_the_scf_run():
    scf, nscf = pw(1.0, "homo_lumo", 2.0), pw(1.5, "homo_lumo", 2.0)
    assert pdos_gap(scf, nscf, gapped()) == GapInfo(0.5, "homo_lumo")
    assert pdos_gap(scf, None, gapped()) == GapInfo(1.0, "homo_lumo")


def test_an_nscf_without_homo_lumo_leaves_it_to_the_scf_run():
    scf, nscf = pw(1.0, "homo_lumo", 2.0), pw(0.6)
    assert pdos_gap(scf, nscf, gapped()) == GapInfo(1.0, "homo_lumo")


def test_a_closed_homo_lumo_gap_is_a_metal_and_the_curve_is_not_asked():
    closed = pw(1.0, "homo_lumo", 1.0 + EDGE_TOL)
    assert pdos_gap(closed, None, gapped()) is None  # the curve would say 1.2 eV


def test_without_homo_lumo_the_curve_is_read_around_the_fermi_energy():
    gap = pdos_gap(pw(0.6), None, gapped())
    assert gap is not None and gap.source == "dos" and gap.value == pytest.approx(1.2, abs=STEP)
    assert pdos_gap(None, None, gapped()) is None
    assert pdos_gap(pw(0.6), None, dataclasses.replace(gapped(), total=None)) is None


def test_the_nscf_fermi_energy_places_the_search():
    assert pdos_gap(pw(-3.0), pw(0.6), gapped()).source == "dos"  # type: ignore[union-attr]
    assert pdos_gap(pw(0.6), pw(-3.0), gapped()) is None


def test_load_reads_the_exact_gap_of_the_runs_in_the_folder(tmp_path):
    folder = tmp_path / "pdos"
    shutil.copytree(FIXTURES / "al_pdos_flat", folder)
    shutil.copy(FIXTURES / "si_bands" / "si.scf.out", folder / "al.scf.out")
    (folder / "al.nscf.out").unlink()  # the SCF is then the only run
    gap = load(folder)[1].gap
    assert gap == GapInfo(pytest.approx(6.8182 - 6.3143), "homo_lumo")


# -- the legend entry ---------------------------------------------------------------------------
def render_gap(dataset, **changes):
    module = next(m for m in REGISTRY if m.kind == "pdos")
    params = module.default_params(CONFIG, dataset)
    params.legend_gap = True
    for name, value in changes.items():
        setattr(params, name, value)
    return render(module, dataset, params, LIGHT)[0]


def test_off_by_default_the_legend_has_no_gap():
    module = next(m for m in REGISTRY if m.kind == "pdos")
    dataset = dataset_of(gapped())
    params = module.default_params(CONFIG, dataset)
    assert params.legend_gap is False
    assert GAP_TEXT not in " ".join(legend_texts(render(module, dataset, params, LIGHT)[0]))


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("mode", MODES)
def test_the_entry_is_last_in_every_spin_mode_and_orientation(mode, orientation):
    data = gapped(up=((0.0, 1.2),), down=((0.0, 1.2),))
    figure = render_gap(dataset_of(data), spin_mode=mode, orientation=orientation)
    assert legend_texts(figure)[-1] == f"{GAP_TEXT} ≈ 1.20 eV"
    assert len(legend_texts(figure)) > 1  # the series are still there


def test_a_plain_pdos_gets_the_entry_after_the_series():
    figure = render_gap(dataset_of(gapped()))
    assert legend_texts(figure) == ["Total", "Si s", f"{GAP_TEXT} ≈ 1.20 eV"]


def test_the_exact_gap_has_an_equal_sign_and_three_decimals():
    figure = render_gap(dataset_of(gapped(), kind="homo_lumo", fermi=0.0, lumo=1.2345))
    assert legend_texts(figure)[-1] == f"{GAP_TEXT} = 1.234 eV"


def test_the_gap_is_the_systems_not_the_drawn_series():
    dataset = dataset_of(gapped())
    figure = render_gap(dataset, hidden_series=["Si"], show_total=False, grouping="species")
    assert legend_texts(figure) == [f"{GAP_TEXT} ≈ 1.20 eV"]


def test_the_total_of_the_projections_is_used_without_a_pdos_tot_file():
    data = dataclasses.replace(gapped(), total_is_sum=True)
    assert dataset_of(data).gap is not None


def test_a_metal_has_no_entry():
    module, dataset, params = load(FIXTURES / "al_pdos_flat")
    params.legend_gap = True
    texts = legend_texts(render(module, dataset, params, LIGHT)[0])
    assert texts and not any(t.startswith(GAP_TEXT) for t in texts)


def test_a_hidden_legend_stays_hidden():
    figure = render_gap(dataset_of(gapped()), show_legend=False)
    assert figure.axes[0].get_legend() is None


def test_projwfc_keeps_its_gap_constants_named():
    assert projwfc.GAP_DOS_REL_TOL == 1e-3 and projwfc.GAP_SEARCH_EV == 1.0
