"""E_F in the middle of the gap of an insulator, and only of one (spec 91)."""

from pathlib import Path

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands import BandsDataset, BandsModule
from qe_studio.core.calculations.bands.data import band_edges
from qe_studio.core.calculations.params import MID_GAP_TOOLTIP
from qe_studio.core.calculations.pdos import PdosDataset
from qe_studio.core.calculations.pdos.gap import pdos_gap, pdos_midgap
from qe_studio.core.calculations.pdos.params import reference
from qe_studio.core.plotting.plot_file import apply_stored
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.bands_x import BandData
from qe_studio.core.qe.projwfc import Channel, PdosData, PdosSeries, empty_regions, region_above
from qe_studio.core.qe.pw_output import PwOutput
from spin_helpers import SPIN_BANDS
from test_bands_dos_render import AL_PDOS, combined, fermi_lines
from test_bands_gap_fermi import CBM, ODD, VBM
from test_bands_gap_fermi import dataset_of as bands_of
from test_legend_gap_pdos import ENERGY, STEP, bands_dos, gapped, pw
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

SI_BANDS = FIXTURES / "si_bands"
MIDDLE = (VBM + CBM) / 2


def module_of(kind: str):
    return next(m for m in REGISTRY if m.kind == kind)


def rendered_bands(dataset: BandsDataset, **changes):
    module = BandsModule()
    params = module.default_params(CONFIG, dataset)
    for name, value in changes.items():
        setattr(params, name, value)
    return render(module, dataset, params, LIGHT), params


# -- bands: an insulator --------------------------------------------------------------------------
def test_the_fermi_line_of_silicon_is_in_the_middle_of_its_gap():
    module, dataset, params = load(SI_BANDS)
    assert dataset.fermi == 6.3143  # what pw.x printed stays
    middle = (dataset.vbm + dataset.cbm) / 2
    assert dataset.fermi_level == pytest.approx(middle)
    assert dataset.reference("fermi") == dataset.reference("midgap") == pytest.approx(middle)
    figure, info = render(module, dataset, params, LIGHT)
    assert [list(ln.get_ydata()) for ln in fermi_lines(figure.axes[0], params.fermi_color)] == [
        [0, 0]
    ]
    assert info.summary.startswith("HOMO = 6.3143 eV · E_F = 6.5411 eV (meio do gap) · E_gap")


def test_another_reference_moves_the_axis_and_not_the_level():
    module, dataset, params = load(SI_BANDS)
    params.reference = "vbm"
    figure, _info = render(module, dataset, params, LIGHT)
    (line,) = fermi_lines(figure.axes[0], params.fermi_color)
    assert line.get_ydata()[0] == pytest.approx(dataset.gap / 2)


@pytest.mark.parametrize("kind", ["homo", "homo_lumo"])
def test_fixed_occupations_move_the_homo_and_keep_it_in_the_footer(kind):
    dataset = bands_of(VBM, kind)
    assert dataset.fermi_level == pytest.approx(MIDDLE)
    (_figure, info), _params = rendered_bands(dataset)
    assert f"HOMO = {VBM:.4f} eV · E_F = {MIDDLE:.4f} eV (meio do gap)" in info.summary


@pytest.mark.parametrize("fermi", [VBM, -0.4, 0.9, CBM])
def test_smearing_inside_the_gap_also_goes_to_the_middle(fermi):
    dataset = bands_of(fermi, "fermi")
    assert dataset.fermi_level == pytest.approx(MIDDLE)
    (_figure, info), _params = rendered_bands(dataset)
    assert info.summary.startswith(f"E_F = {MIDDLE:.4f} eV (meio do gap)")
    assert f"{fermi:.4f}" not in info.summary  # one E_F in the footer, the one drawn


def test_the_absolute_window_is_centred_on_the_level():
    dataset = bands_of(VBM, "homo_lumo")
    config = CONFIG.model_copy(deep=True)
    config.plot.shift_to_fermi = False
    params = BandsModule().default_params(config, dataset)
    assert (params.emin, params.emax) == pytest.approx((MIDDLE - 5, MIDDLE + 5))


def test_the_csv_follows_the_level():
    module, dataset, params = load(SI_BANDS)
    table = module.table(dataset, params)
    np.testing.assert_allclose(
        table.columns[1].values, dataset.bands.energies[0] - dataset.fermi_level
    )


def test_the_reference_field_explains_the_rule():
    _module, dataset, _params = load(SI_BANDS)
    field = next(f for f in BandsModule().param_schema(dataset) if f.name == "reference")
    assert field.tooltip == MID_GAP_TOOLTIP


# -- bands: what is not an insulator keeps the printed value ----------------------------------------
@pytest.mark.parametrize(
    ("fermi", "kind", "electrons"),
    [
        (-1.0, "fermi", 4.0),  # E_F inside a band: a metal with pockets off the path
        (0.0, "fermi", ODD),  # an odd count: bands around E_F, no insulating gap
        (VBM, "homo", 8.0),  # every band filled: no band above to measure a gap to
        (0.25, "fermi", None),  # no electron count: no verdict
    ],
)
def test_a_gap_not_proven_keeps_the_printed_level(fermi, kind, electrons):
    dataset = bands_of(fermi, kind, electrons)
    assert dataset.fermi_level == dataset.reference("fermi") == fermi
    (_figure, info), _params = rendered_bands(dataset)
    assert "meio do gap" not in info.summary


def test_without_e_f_there_is_no_level():
    dataset = bands_of(None, None)
    assert dataset.gap is not None and dataset.fermi_level is None
    assert dataset.reference("fermi") == 0.0


@pytest.mark.parametrize("folder", ["al_bands", SPIN_BANDS.name])
def test_a_metal_does_not_change(folder):
    _module, dataset, _params = load(FIXTURES / folder)
    assert dataset.fermi_level == dataset.fermi


# -- bands: spin ----------------------------------------------------------------------------------
UP = np.array([[-2.0, -1.0], [1.0, 2.0]])
DOWN = np.array([[-1.5, -0.8], [1.4, 2.2]])
CROSSING = np.array([[-1.5, 0.8], [1.4, 2.2]])  # its first band crosses E_F = 0.5


def spin_dataset(
    down: np.ndarray | None, fermi: float = 0.5, pair=None, electrons: float | None = 2.0
) -> BandsDataset:
    x = np.array([0.0, 1.0])
    kind = "spin_fermi" if pair else "fermi"
    dataset = BandsDataset(
        folder=Path("."),
        bands=BandData(x, UP),
        source="gnu",
        fermi=fermi,
        fermi_kind=kind,
        ticks=[],
        labels=[],
        tick_source="nenhum",
        bands_down=None if down is None else BandData(x, down),
        fermi_up_down=pair,
    )
    band_edges(
        dataset,
        PwOutput(
            fermi=fermi,
            fermi_kind=kind,
            fermi_up_down=pair,
            spin_polarized=True,
            n_electrons=electrons,
        ),
    )
    return dataset


def test_both_channels_with_a_gap_use_the_global_one():
    dataset = spin_dataset(DOWN)  # VBM −0.8 (↓), CBM 1.0 (↑)
    assert dataset.fermi_level == pytest.approx(0.1)
    (figure, info), params = rendered_bands(dataset)
    assert [ln.get_ydata()[0] for ln in fermi_lines(figure.axes[0], params.fermi_color)] == [0]
    assert "E_F = 0.1000 eV (meio do gap)" in info.summary


def test_a_half_metal_keeps_e_f():
    assert spin_dataset(CROSSING).fermi_level == 0.5


def test_only_the_up_channel_is_no_proof():
    assert spin_dataset(None).fermi_level == 0.5


def test_two_fermi_energies_are_kept():
    dataset = spin_dataset(DOWN, 0.4, (0.3, 0.5))
    assert dataset.gap is not None and dataset.fermi_level == dataset.reference("fermi") == 0.4
    (figure, _info), params = rendered_bands(dataset)
    lines = fermi_lines(figure.axes[0], params.fermi_color)
    assert [ln.get_ydata()[0] for ln in lines] == pytest.approx([-0.1, 0.1])


# -- the empty region above a level ---------------------------------------------------------------
TWO_GAPS = ((-1.5, -0.5), (0.0, 1.2))


def regions_of(data: PdosData):
    return empty_regions(data.energy, data.total)


@pytest.mark.parametrize("level", [0.6, 0.0, -0.3])  # inside it, at its edge, under it
def test_the_first_region_at_or_above_the_level(level):
    region = region_above(regions_of(gapped(up=TWO_GAPS)), level)
    assert (region.low, region.high) == pytest.approx((0.0, 1.2))


def test_a_region_below_the_level_is_skipped():
    assert region_above(regions_of(gapped()), 1.5) is None


def test_a_region_too_far_above_the_homo_is_not_taken():
    assert pdos_midgap(pw(-2.0, "homo"), None, gapped()) is None


# -- PDOS -----------------------------------------------------------------------------------------
def pdos_of(data: PdosData, scf: PwOutput | None, nscf: PwOutput | None = None) -> PdosDataset:
    return PdosDataset(
        Path("."),
        data,
        scf.fermi if scf else None,
        nscf.fermi if nscf else None,
        channels_scf=scf.fermi_up_down if scf else None,
        gap=pdos_gap(scf, nscf, data),
        proven_midgap=pdos_midgap(scf, nscf, data),
        kind_scf=scf.fermi_kind if scf else None,
        kind_nscf=nscf.fermi_kind if nscf else None,
    )


def test_a_printed_pair_gives_its_middle():
    dataset = pdos_of(gapped(), pw(0.0, "homo_lumo", 1.2))
    assert dataset.fermi_level("scf") == pytest.approx(0.6)
    params = module_of("pdos").default_params(CONFIG, dataset)
    assert reference(dataset, params) == pytest.approx(0.6)
    assert render(module_of("pdos"), dataset, params)[1].summary.startswith(
        "HOMO = 0.0000 eV (SCF) · E_F = 0.6000 eV (meio do gap)"
    )


def test_the_pair_of_the_nscf_comes_first():
    midgap = pdos_midgap(pw(0.0, "homo_lumo", 1.2), pw(0.1, "homo_lumo", 1.0), gapped())
    assert midgap == pytest.approx(0.55)


def test_a_pair_that_does_not_open_is_a_metal():
    assert pdos_midgap(pw(0.6, "homo_lumo", 0.6), None, gapped()) is None


@pytest.mark.parametrize("homo", [0.0, -0.2])  # at the edge, or under it on a coarser SCF grid
def test_fixed_occupations_without_a_lumo_take_the_region_above_the_homo(homo):
    midgap = pdos_midgap(pw(homo, "homo"), None, gapped(up=TWO_GAPS))
    assert midgap == pytest.approx(0.6, abs=STEP)


def test_smearing_inside_the_region_goes_to_its_middle():
    assert pdos_midgap(pw(0.3), None, gapped()) == pytest.approx(0.6, abs=STEP)


def test_either_run_proves_it():
    # A tetrahedra NSCF puts E_F at the top of the valence, inside the broadened curve.
    assert pdos_midgap(pw(0.3), pw(-0.1), gapped()) == pytest.approx(0.6, abs=STEP)


@pytest.mark.parametrize("fermi", [-0.5, 1.5])
def test_a_metal_near_an_empty_region_does_not_move(fermi):
    dataset = pdos_of(gapped(), pw(fermi))
    assert dataset.gap is not None  # the legend's reading takes a region up to 1 eV away
    assert dataset.proven_midgap is None and dataset.fermi_level("scf") == fermi


def test_no_total_curve_and_no_e_f_give_no_middle():
    data = gapped()
    assert pdos_midgap(pw(0.3), None, PdosData(data.energy, data.series, None)) is None
    assert pdos_midgap(None, None, data) is None


def test_two_fermi_energies_are_kept_in_the_pdos():
    run = PwOutput(fermi=0.6, fermi_kind="spin_fermi", fermi_up_down=(0.5, 0.7))
    assert pdos_midgap(run, None, gapped()) is None
    dataset = PdosDataset(
        Path("."), gapped(), 0.6, None, channels_scf=(0.5, 0.7), proven_midgap=0.9
    )
    assert dataset.fermi_level("scf") == 0.6


def test_the_occupied_states_are_filled_up_to_the_middle():
    dataset = pdos_of(gapped(), pw(0.0, "homo_lumo", 1.2))
    module = module_of("pdos")
    params = module.default_params(CONFIG, dataset)
    params.shift_to_fermi = False
    figure = render(module, dataset, params)[0]
    filled = max(p.vertices[:, 0].max() for c in figure.axes[0].collections for p in c.get_paths())
    assert filled == pytest.approx(0.6, abs=STEP)


def test_the_source_of_e_f_is_offered_only_when_it_matters():
    module = module_of("pdos")
    names = {f.name for f in module.param_schema(pdos_of(gapped(), pw(0.0, "homo_lumo", 1.2)))}
    assert "fermi_source" not in names
    fields = {f.name: f for f in module.param_schema(pdos_of(gapped(), pw(-0.5)))}
    assert "fermi_source" in fields
    assert fields["shift_to_fermi"].tooltip == MID_GAP_TOOLTIP


# -- bands + DOS ----------------------------------------------------------------------------------
def test_the_dos_panel_follows_the_level_of_the_bands():
    module, dataset, params = combined(SI_BANDS, AL_PDOS)
    middle = dataset.bands.fermi_level
    color = params.fermi_color
    figure, info = render(module, dataset, params)
    for ax in figure.axes:
        assert [list(line.get_ydata()) for line in fermi_lines(ax, color)] == [[0, 0]]
    total = next(line for line in figure.axes[1].get_lines() if line.get_label() == "Total")
    np.testing.assert_allclose(total.get_ydata(), dataset.dos.data.energy - middle)
    assert any("1.744 eV" in note for note in info.notes)  # the check compares what pw.x printed


# -- the review of spec 91: what must not count as an insulator, and one gap for the whole plot -----
LOW_METAL_PEAK = 400.0


def low_dos_metal() -> PdosData:
    """A metal with 0.2 states/eV around E_F and a sharp semicore peak far below it."""
    dos = bands_dos((-0.5, 0.45))
    dos[dos == 0.0] = 0.2
    dos[ENERGY < -8.0] = LOW_METAL_PEAK
    channel = Channel(dos)
    return PdosData(ENERGY, (PdosSeries(1, "K", 1, "s", None, channel),), channel)


def test_a_coarse_scf_pair_is_checked_against_the_curve():
    data = gapped(up=((0.0, 0.5),))  # the projected grid finds the CBM at 0.5
    scf, nscf = pw(0.0, "homo_lumo", 2.0), pw(0.0)
    assert pdos_midgap(scf, nscf, data) == pytest.approx(0.25, abs=STEP)
    gap = pdos_gap(scf, nscf, data)
    assert gap is not None and gap.source == "dos"
    assert gap.value == pytest.approx(0.5, abs=2 * STEP)


def test_a_scf_pair_the_curve_agrees_with_is_kept():
    scf, nscf = pw(0.1, "homo_lumo", 0.9), pw(0.0)
    assert pdos_midgap(scf, nscf, gapped()) == pytest.approx(0.5)
    gap = pdos_gap(scf, nscf, gapped())
    assert gap is not None and gap.source == "homo_lumo" and gap.value == pytest.approx(0.8)


def test_real_states_above_the_homo_are_not_a_tail():
    assert pdos_midgap(pw(0.0, "homo"), None, gapped(up=((0.4, 0.9),))) is None


def test_a_low_dos_metal_with_a_sharp_peak_does_not_move():
    assert pdos_midgap(pw(0.3), None, low_dos_metal()) is None


@pytest.mark.parametrize(
    ("electrons", "spin", "proven"),
    [(7.0, False, False), (7.5, True, False), (8.0, False, True), (7.0, True, True)],
)
def test_the_count_can_veto_a_gap_read_off_the_curve(electrons, spin, proven):
    run = PwOutput(fermi=0.3, fermi_kind="fermi", n_electrons=electrons, spin_polarized=spin)
    assert (pdos_midgap(run, None, gapped()) is not None) is proven


@pytest.mark.parametrize("scf_homo", [0.0, 0.45])  # the SCF alone could prove the second one
def test_an_nscf_e_f_inside_a_band_says_metal(scf_homo):
    data = gapped(up=((0.5, 1.2),))
    assert pdos_midgap(pw(scf_homo, "homo"), pw(0.2), data) is None


def test_the_legend_and_e_f_name_the_same_region():
    data = gapped(up=((-1.0, -0.1), (0.0, 0.3)))
    assert pdos_midgap(pw(0.15), None, data) == pytest.approx(0.15, abs=STEP)
    gap = pdos_gap(pw(0.15), None, data)
    assert gap is not None and gap.value == pytest.approx(0.3, abs=2 * STEP)


def test_the_source_is_offered_when_one_run_keeps_two_fermi_energies():
    scf = PwOutput(fermi=0.4, fermi_kind="spin_fermi", fermi_up_down=(0.3, 0.5))
    dataset = pdos_of(gapped(), scf, pw(0.3))
    assert dataset.fermi_level("scf") != dataset.fermi_level("nscf")
    assert "fermi_source" in {f.name for f in module_of("pdos").param_schema(dataset)}


def test_the_pdos_footer_keeps_the_homo_of_fixed_occupations():
    dataset = pdos_of(gapped(), pw(0.0, "homo_lumo", 1.2))
    module = module_of("pdos")
    summary = render(module, dataset, module.default_params(CONFIG, dataset))[1].summary
    assert summary.startswith("HOMO = 0.0000 eV (SCF) · E_F = 0.6000 eV (meio do gap)")


def test_the_pdos_footer_of_smearing_has_no_homo():
    dataset = pdos_of(gapped(), pw(0.3))
    module = module_of("pdos")
    summary = render(module, dataset, module.default_params(CONFIG, dataset))[1].summary
    assert summary.startswith("E_F = ") and "(meio do gap)" in summary and "HOMO" not in summary


def test_a_stored_source_is_validated_when_the_field_is_not_offered():
    dataset = pdos_of(gapped(), pw(0.0, "homo_lumo", 1.2))
    module = module_of("pdos")
    params = module.default_params(CONFIG, dataset)
    assert apply_stored(params, {"fermi_source": "bogus"}, module.param_schema(dataset)) == [
        "fermi_source"
    ]
    assert params.fermi_source == "scf"


def test_the_reference_label_says_what_e_f_is():
    def label_of(dataset):
        field = next(f for f in BandsModule().param_schema(dataset) if f.name == "reference")
        return dict(field.choices)["fermi"]

    assert label_of(load(SI_BANDS)[1]) == "E_F (meio do gap)"
    assert label_of(load(FIXTURES / "al_bands")[1]) == "E_F (SCF)"


def test_a_spin_gap_needs_the_electrons_to_fill_it():
    assert spin_dataset(DOWN, electrons=3.0).fermi_level == 0.5  # 1 + 1 valence bands, 3 electrons
    assert spin_dataset(DOWN, electrons=None).fermi_level == 0.5
    assert spin_dataset(DOWN, electrons=2.0).fermi_level == pytest.approx(0.1)
