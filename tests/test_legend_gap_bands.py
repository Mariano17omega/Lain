"""The energy gap as a legend entry of the band structure (spec 20, R1-R3)."""

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY, module_for_file
from qe_studio.core.calculations.bands import BandsDataset, BandsModule
from qe_studio.core.calculations.bands.data import ChannelEdges
from qe_studio.core.calculations.bands.gap import (
    NO_COUNT_NOTE,
    NO_GAP_NOTE,
    GapEntry,
    gap_entries,
    legend_gap_notes,
)
from qe_studio.core.calculations.params import COMMON_FIELDS
from qe_studio.core.detection import detect_folder, manual_result
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.bands_x import BandData
from qe_studio.core.sniff import SniffCache, sniff
from spin_helpers import SPIN_BANDS
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

GAP_TEXT = "$E_{gap}$"


def legend_texts(figure):
    legend = figure.axes[0].get_legend()
    return [] if legend is None else [t.get_text() for t in legend.get_texts()]


def gap_texts(figure):
    return [t for t in legend_texts(figure) if t.startswith(GAP_TEXT)]


def bands(folder, **changes):
    module, dataset, params = load(folder)
    params.show_legend = True
    for name, value in changes.items():
        setattr(params, name, value)
    return module, dataset, params


def synthetic(**kwargs):
    base = {
        "folder": SPIN_BANDS,
        "bands": BandData(np.linspace(0, 1, 50), np.zeros((12, 50))),
        "source": "gnu",
        "fermi": 5.1234,
        "fermi_kind": "fermi",
        "ticks": [],
        "labels": [],
        "tick_source": "nenhum",
    }
    return BandsDataset(**{**base, **kwargs})


def spin_dataset(**kwargs):
    both = {"bands_down": BandData(np.linspace(0, 1, 50), np.zeros((12, 50)))}
    return synthetic(**both, **kwargs)


def render_synthetic(dataset, **changes):
    module = BandsModule()
    params = module.default_params(CONFIG, dataset)
    params.show_legend, params.legend_gap = True, True
    for name, value in changes.items():
        setattr(params, name, value)
    return render(module, dataset, params, LIGHT)[0]


# -- a semiconductor ----------------------------------------------------------------------------
def test_off_by_default_and_the_legend_has_no_gap():
    module, dataset, params = bands(FIXTURES / "si_bands")
    assert params.legend_gap is False
    figure, _ = render(module, dataset, params, LIGHT)
    assert gap_texts(figure) == []


def test_the_gap_is_the_last_legend_entry_and_equals_the_footer():
    module, dataset, params = bands(FIXTURES / "si_bands", legend_gap=True)
    figure, info = render(module, dataset, params, LIGHT)
    assert dataset.gap is not None
    assert legend_texts(figure)[-1] == f"{GAP_TEXT} = {dataset.gap:.3f} eV"
    assert f"E_gap (no caminho) = {dataset.gap:.3f} eV" in info.summary


@pytest.mark.parametrize("reference", ["fermi", "vbm", "midgap", "absolute"])
def test_the_reference_and_the_window_do_not_change_the_gap(reference):
    module, dataset, params = bands(FIXTURES / "si_bands", legend_gap=True)
    text = f"{GAP_TEXT} = {dataset.gap:.3f} eV"
    params.reference = reference
    params.emin, params.emax = -20.0, 30.0
    assert gap_texts(render(module, dataset, params, LIGHT)[0]) == [text]
    params.emin, params.emax = 100.0, 101.0  # the gap lies outside the window
    assert gap_texts(render(module, dataset, params, LIGHT)[0]) == [text]


def test_a_hidden_legend_stays_hidden():
    module, dataset, params = bands(FIXTURES / "si_bands", legend_gap=True, show_legend=False)
    figure, _ = render(module, dataset, params, LIGHT)
    assert figure.axes[0].get_legend() is None


# -- metals --------------------------------------------------------------------------------------
@pytest.mark.parametrize("folder", ["al_bands", "qe731_ni_spin_bands"])
def test_a_metal_has_no_gap_entry(folder):
    module, dataset, params = bands(FIXTURES / folder, legend_gap=True)
    assert gap_entries(dataset) == []
    figure, _ = render(module, dataset, params, LIGHT)
    assert gap_texts(figure) == [] and legend_texts(figure)


# -- why there is no gap in the legend (the readout's ⚠ lines) ---------------------------------
@pytest.mark.parametrize("folder", ["al_bands", "qe731_ni_spin_bands"])
def test_a_metal_with_the_gap_asked_says_so_in_the_readout(folder):
    module, dataset, params = bands(FIXTURES / folder, legend_gap=True)
    _figure, info = render(module, dataset, params, LIGHT)
    assert NO_GAP_NOTE in info.notes


def test_no_note_when_the_gap_is_there_or_nothing_asked_for():
    module, dataset, params = bands(FIXTURES / "si_bands", legend_gap=True)
    assert legend_gap_notes(dataset, params) == ()
    module, dataset, params = bands(FIXTURES / "al_bands")  # not asked
    assert legend_gap_notes(dataset, params) == ()
    params.legend_gap, params.show_legend = True, False  # a hidden legend has no gap to miss
    assert legend_gap_notes(dataset, params) == ()


def test_a_gap_note_of_the_dataset_is_not_repeated():
    _module, dataset, params = bands(FIXTURES / "al_bands", legend_gap=True)
    dataset.gap_note = "gap indeterminado: E_F fora de [VBM, CBM] no caminho"
    assert legend_gap_notes(dataset, params) == ()


def test_without_the_scf_the_note_names_the_missing_electron_count():
    dataset = synthetic(fermi=None, fermi_kind=None)
    params = BandsModule().default_params(CONFIG, dataset)
    params.show_legend = params.legend_gap = True
    assert legend_gap_notes(dataset, params) == (NO_COUNT_NOTE,)


# -- spin ----------------------------------------------------------------------------------------
def two_gaps():
    edges = {"up": ChannelEdges(5.1, 3.0, 4.2), "down": ChannelEdges(5.1, 3.2, 4.0)}
    return spin_dataset(edges=edges, vbm=3.2, cbm=4.0)


@pytest.mark.parametrize("layout", ["overlay", "side"])
def test_two_gapped_channels_give_up_down_and_global(layout):
    figure = render_synthetic(two_gaps(), spin_layout=layout)
    assert gap_texts(figure) == [
        f"{GAP_TEXT} ↑ = 1.200 eV",
        f"{GAP_TEXT} ↓ = 0.800 eV",
        f"{GAP_TEXT} global = 0.800 eV",
    ]
    if layout == "side":  # the legend stays in the first panel
        assert figure.axes[1].get_legend() is None


@pytest.mark.parametrize("layout", ["overlay", "side"])
def test_a_metallic_down_channel_leaves_only_up(layout):
    edges = {"up": ChannelEdges(5.1, -1.0, 0.234), "down": ChannelEdges(5.1, metallic=True)}
    figure = render_synthetic(spin_dataset(edges=edges), spin_layout=layout)
    assert gap_texts(figure) == [f"{GAP_TEXT} ↑ = 1.234 eV"]


def test_a_run_with_only_the_up_channel_lists_only_up():
    edges = {"up": ChannelEdges(5.1, -1.0, 0.234)}
    figure = render_synthetic(synthetic(edges=edges))
    assert gap_texts(figure) == [f"{GAP_TEXT} ↑ = 1.234 eV"]


# -- gap_entries, the footer's source ------------------------------------------------------------
def test_gap_entries_of_each_kind_of_run():
    assert gap_entries(synthetic()) == []
    assert gap_entries(synthetic(vbm=1.0, cbm=2.5)) == [GapEntry(None, 1.5)]
    assert gap_entries(two_gaps()) == [
        GapEntry("up", pytest.approx(1.2)),
        GapEntry("down", pytest.approx(0.8)),
        GapEntry("global", pytest.approx(0.8)),
    ]
    only_up = synthetic(edges={"up": ChannelEdges(5.1, -1.0, 0.234)})
    assert gap_entries(only_up) == [GapEntry("up", pytest.approx(1.234))]


# -- the field -----------------------------------------------------------------------------------
def test_the_field_is_always_in_the_legend_section_of_bands_and_pdos():
    for kind in ("bands", "pdos"):
        module = next(m for m in REGISTRY if m.kind == kind)
        _, dataset, _ = load(FIXTURES / ("al_bands" if kind == "bands" else "al_pdos_flat"))
        (field,) = [f for f in module.param_schema(dataset) if f.name == "legend_gap"]
        assert (field.section, field.kind) == ("Legenda", "bool")


def test_scf_and_relax_do_not_offer_it():
    assert "legend_gap" not in {f.name for f in COMMON_FIELDS}
    (relax,) = detect_folder(FIXTURES / "si_relax", sniff=SniffCache().sniff)
    schemas = [relax.module.param_schema(relax.module.load(relax, sniff))]
    scf = FIXTURES / "si_bands" / "si.scf.out"
    module = module_for_file(sniff(scf))
    assert module is not None and module.kind == "scf"
    result = detect_one_scf(module, scf)
    schemas.append(module.param_schema(module.load(result, sniff)))
    assert all("legend_gap" not in {f.name for f in schema} for schema in schemas)


def detect_one_scf(module, path):
    return manual_result(module, path.parent, {"scf_out": [path]}, SniffCache().sniff)
