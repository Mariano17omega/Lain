"""Spin (two channels) in the band data: eigenvalues, band edges, Fermi energies (spec 13, R2)."""

import numpy as np
import pytest

from qe_studio.core.calculations.bands.data import (
    BandsDataset,
    ChannelEdges,
    channel_edges,
    spin_band_edges,
    spin_channel_edges,
    valence_mask,
)
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.detection import manual_result
from qe_studio.core.qe.bands_x import BandData, read_gnu
from qe_studio.core.qe.pw_output import PwOutput
from qe_studio.core.sniff import sniff
from spin_helpers import (
    FIXED_FERMI,
    SPIN_BANDS,
    detect_one,
    gnu_energies,
    spin_bands_copy,
    with_fixed_magnetization,
)


def band_data(*bands: list[float]) -> BandData:
    energies = np.array(bands, dtype=float)
    return BandData(np.linspace(0, 1, energies.shape[1]), energies)


def dataset_of(up: BandData, down: BandData) -> BandsDataset:
    return BandsDataset(
        folder=SPIN_BANDS,
        bands=up,
        source="gnu",
        fermi=None,
        fermi_kind=None,
        ticks=[],
        labels=[],
        tick_source="nenhum",
        bands_down=down,
    )


# -- edges of one channel ------------------------------------------------------------------------
def test_a_channel_with_a_band_crossing_e_f_is_metallic():
    energies = np.array([[-3.0, -2.0], [-1.0, 1.0], [2.0, 3.0]])
    assert channel_edges(energies, 0.0) == ChannelEdges(0.0, metallic=True)


def test_the_gap_of_an_insulating_channel_is_computed_from_its_bands():
    # valence tops at -0.5, conduction bottoms at 1.2: gap = 1.7 whatever E_F inside the gap is
    energies = np.array([[-3.0, -2.5], [-1.0, -0.5], [1.2, 1.5], [2.0, 2.2]])
    for fermi in (0.0, 0.4, 1.1):
        edges = channel_edges(energies, fermi)
        assert (edges.vbm, edges.cbm, edges.metallic) == (-0.5, 1.2, False)
        assert edges.gap == pytest.approx(1.7)


def test_e_f_at_the_homo_is_not_a_crossing():
    energies = np.array([[-1.0, -0.4999], [1.2, 1.5]])  # top 0.1 meV above the printed HOMO
    edges = channel_edges(energies, -0.5)
    assert not edges.metallic and edges.gap == pytest.approx(1.2 - -0.4999)


def test_a_closed_gap_is_metallic_and_no_e_f_means_no_edges():
    touching = np.array([[-1.0, 0.0], [0.0005, 1.0]])
    assert channel_edges(touching, 0.0).metallic
    assert channel_edges(touching, None) == ChannelEdges(None)


def test_all_bands_on_one_side_of_e_f_have_no_gap_but_are_not_metallic():
    edges = channel_edges(np.array([[-3.0, -2.0], [-1.0, -0.5]]), 0.0)
    assert edges.gap is None and not edges.metallic and edges.vbm == -0.5 and edges.cbm is None


def test_valence_mask_follows_the_band_tops():
    energies = np.array([[-2.0, -1.0], [-1.0, 0.0005], [0.5, 2.0]])
    assert valence_mask(energies, 0.0).tolist() == [True, True, False]


# -- global edges and the Fermi energy of each channel -------------------------------------------
def test_global_gap_needs_both_channels_gapped():
    up = band_data([-3.0, -2.5], [-1.0, -0.5], [1.2, 1.5])
    down = band_data([-3.0, -2.5], [-1.0, -0.8], [0.9, 1.4])
    dataset = dataset_of(up, down)
    spin_band_edges(dataset, PwOutput(fermi=0.0, spin_polarized=True))
    assert dataset.edges["up"].gap == pytest.approx(1.7)
    assert dataset.edges["down"].gap == pytest.approx(1.7)
    assert (dataset.vbm, dataset.cbm) == (-0.5, 0.9)  # max VBM, min CBM
    assert dataset.gap == pytest.approx(1.4)


def test_a_metallic_channel_leaves_no_global_gap():
    up = band_data([-3.0, -2.5], [-1.0, -0.5], [1.2, 1.5])
    down = band_data([-3.0, -2.5], [-1.0, 1.0], [2.0, 2.4])  # half-metal: ↓ crosses E_F
    dataset = dataset_of(up, down)
    spin_band_edges(dataset, PwOutput(fermi=0.0, spin_polarized=True))
    assert dataset.edges["up"].gap is not None and dataset.edges["down"].metallic
    assert dataset.gap is None and dataset.vbm is None


def test_overlapping_channel_gaps_have_no_global_gap():
    up = band_data([-3.0, -2.5], [-1.0, 0.8], [1.2, 1.5])  # E_F↑ = 0.9: VBM↑ 0.8, CBM↑ 1.2
    down = band_data([-3.0, -2.5], [-1.0, -0.8], [0.5, 0.7])  # E_F↓ = 0.4: VBM↓ -0.8, CBM↓ 0.5
    dataset = dataset_of(up, down)
    spin_band_edges(dataset, PwOutput(fermi=0.65, fermi_up_down=(0.9, 0.4), spin_polarized=True))
    assert dataset.edges["up"].gap is not None and dataset.edges["down"].gap is not None
    assert dataset.gap is None  # CBM↓ 0.5 lies below VBM↑ 0.8


def test_each_channel_uses_its_own_e_f():
    up = band_data([-3.0, -2.5], [-1.0, 1.0], [2.0, 2.5])  # gap (1.0, 2.0), E_F↑ = 1.5
    down = band_data([-3.0, -2.5], [-1.0, 0.5], [0.7, 1.4])  # gap (0.5, 0.7), E_F↓ = 0.6
    dataset = dataset_of(up, down)
    both = PwOutput(fermi=1.05, fermi_up_down=(1.5, 0.6), spin_polarized=True)
    spin_band_edges(dataset, both)
    assert not dataset.edges["up"].metallic and not dataset.edges["down"].metallic
    assert dataset.edges["down"].fermi == 0.6
    # with the average (1.05) E_F would fall inside a ↓ band: what the separate E_F avoids
    assert channel_edges(down.energies, 1.05).metallic


# -- fixed occupations: each channel's bands are counted -----------------------------------------
def fixed_occupations(homo: float, up_down: tuple[float, float]) -> PwOutput:
    """A spin SCF with fixed occupations: pw.x prints one HOMO / LUMO for both channels."""
    return PwOutput(
        fermi=homo, fermi_kind="homo_lumo", n_electrons_up_down=up_down, spin_polarized=True
    )


def test_fixed_occupations_count_the_bands_above_the_scf_homo():
    # the SCF grid's HOMO is -1.0, but on the band path the top valence band reaches -0.95
    up = band_data([-3.0, -2.5], [-2.0, -0.95], [1.2, 1.5])
    down = band_data([-3.0, -2.5], [-1.5, -1.2], [0.9, 1.4])
    dataset = dataset_of(up, down)
    spin_band_edges(dataset, fixed_occupations(-1.0, (2.0, 2.0)))
    assert dataset.edges["up"] == ChannelEdges(-1.0, -0.95, 1.2, n_occupied=2)
    assert dataset.edges["down"].gap == pytest.approx(2.1)
    assert (dataset.vbm, dataset.cbm) == (-0.95, 0.9)
    assert channel_edges(up.energies, -1.0).metallic  # what the HOMO as E_F would say


def test_fixed_occupations_leave_empty_down_bands_below_the_homo_empty():
    up = band_data([-3.0, -2.5], [-1.0, -0.5], [1.2, 1.5])  # 2 electrons ↑: HOMO -0.5
    down = band_data([-3.0, -2.5], [-1.5, -1.0], [0.9, 1.4])  # 1 electron ↓: band 2 is empty
    dataset = dataset_of(up, down)
    spin_band_edges(dataset, fixed_occupations(-0.5, (2.0, 1.0)))
    assert dataset.edges["down"] == ChannelEdges(-0.5, -2.5, -1.5, n_occupied=1)
    assert channel_edges(down.energies, -0.5).vbm == -1.0  # the HOMO would fill band 2


def test_a_fractional_count_or_smearing_splits_the_bands_at_e_f():
    energies = np.array([[-3.0, -2.5], [-1.0, -0.5], [1.2, 1.5]])
    fractional = fixed_occupations(0.0, (1.5, 1.5))
    smearing = PwOutput(fermi=0.0, fermi_kind="fermi", n_electrons_up_down=(2.0, 2.0))
    for pw in (fractional, smearing):
        edges = spin_channel_edges(energies, 0, pw)
        assert edges.n_occupied is None and (edges.vbm, edges.cbm) == (-0.5, 1.2)


# -- the dataset of the fixtures -----------------------------------------------------------------
def test_dataset_holds_both_channels_of_the_fixture():
    result = detect_one(SPIN_BANDS)
    dataset = result.module.load(result, sniff)
    assert dataset.spin and dataset.source == "gnu"
    assert dataset.bands.energies.shape == dataset.bands_down.energies.shape == (14, 45)
    np.testing.assert_allclose(
        dataset.bands.energies, gnu_energies(SPIN_BANDS / "bands_up.dat.gnu")
    )
    np.testing.assert_allclose(
        dataset.bands_down.energies, gnu_energies(SPIN_BANDS / "bands_dw.dat.gnu")
    )
    assert dataset.fermi == 14.2704 and dataset.fermi_up_down is None
    assert dataset.magnetization == 0.71
    # Ni is a metal in both channels: no gap, no VBM/CBM references
    assert dataset.edges["up"].metallic and dataset.edges["down"].metallic
    assert dataset.gap is None and dataset.n_occupied is None
    assert (
        dataset.band_data("up") is dataset.bands and dataset.band_data("down") is dataset.bands_down
    )


def test_two_fermi_energies_give_each_channel_its_own(tmp_path):
    folder = with_fixed_magnetization(spin_bands_copy(tmp_path))
    result = detect_one(folder)
    dataset = result.module.load(result, sniff)
    assert dataset.fermi_up_down == FIXED_FERMI
    assert dataset.fermi == pytest.approx(sum(FIXED_FERMI) / 2)
    assert dataset.edges["up"].fermi == FIXED_FERMI[0]
    assert dataset.edges["down"].fermi == FIXED_FERMI[1]
    assert dataset.edges["up"].n_occupied is None  # smearing: E_F splits the bands, not a count
    assert any("duas energias de Fermi (↑/↓)" in w for w in dataset.warnings)


def test_a_run_without_spin_has_no_spin_data():
    from conftest import FIXTURES

    result = detect_one(FIXTURES / "si_bands")
    dataset = result.module.load(result, sniff)
    assert not dataset.spin and dataset.bands_down is None and dataset.edges == {}
    assert dataset.n_occupied == 4 and dataset.gap == pytest.approx(0.454, abs=0.01)


# -- reading failures and the pw.x fallback ------------------------------------------------------
def test_an_unreadable_down_channel_leaves_the_up_channel_with_a_warning(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_dw.dat",))
    broken = tmp_path / "broken.txt"
    broken.write_text("not bands\n")
    module = detect_one(folder).module
    mapping = {"gnu": [folder / "bands_up.dat.gnu"], "gnu_down": [broken]}
    result = manual_result(module, folder, mapping)
    dataset = module.load(result, sniff)
    assert dataset.bands_down is None and not dataset.spin
    assert any("canal ↓ ilegível" in w and "broken.txt" in w for w in dataset.warnings)


def test_pw_output_gives_both_channels_when_bandsx_was_not_run(tmp_path):
    folder = spin_bands_copy(
        tmp_path,
        remove=(
            "bands_up.in", "bands_dw.in", "bands_up.out", "bands_dw.out", "bands_up.dat",
            "bands_dw.dat", "bands_up.dat.gnu", "bands_dw.dat.gnu",
        ),
    )  # fmt: skip
    result = detect_one(folder)
    dataset = result.module.load(result, sniff)
    assert dataset.source == "pw" and dataset.spin
    assert any("lidos da saída do pw.x" in w for w in dataset.warnings)
    up = gnu_energies(SPIN_BANDS / "bands_up.dat.gnu")
    down = gnu_energies(SPIN_BANDS / "bands_dw.dat.gnu")
    assert dataset.bands.energies.shape == dataset.bands_down.energies.shape == up.shape
    np.testing.assert_allclose(dataset.bands.energies, up, atol=2e-3)  # pw.x prints 4 decimals
    np.testing.assert_allclose(dataset.bands_down.energies, down, atol=2e-3)
    gnu_x = read_gnu(SPIN_BANDS / "bands_up.dat.gnu").x
    np.testing.assert_allclose(dataset.bands.x, gnu_x, atol=2e-3)


def test_without_any_eigenvalue_source_loading_fails(tmp_path):
    folder = spin_bands_copy(
        tmp_path, remove=("ni.band.out", "bands_up.dat.gnu", "bands_dw.dat.gnu", "bands_up.dat", "bands_dw.dat")
    )  # fmt: skip
    result = detect_one(folder)
    with pytest.raises(LoadError):
        result.module.load(result, sniff)


def test_a_down_channel_alone_says_so_when_loading_fails(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("ni.band.out", "bands_up.dat.gnu", "bands_up.dat"))
    result = detect_one(folder)
    with pytest.raises(LoadError, match=r"só o canal ↓ \(bands_dw.dat.gnu\) foi encontrado"):
        result.module.load(result, sniff)
