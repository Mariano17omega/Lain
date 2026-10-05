"""The gap of a band run without spin only when E_F backs it, and always "no caminho" (spec 27-6 R1)."""

import numpy as np
import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands import BandsDataset, BandsModule
from qe_studio.core.calculations.bands.data import (
    EDGE_TOL,
    GAP_NO_FERMI_NOTE,
    GAP_OFF_PATH_NOTE,
    band_edges,
)
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.bands_x import BandData
from qe_studio.core.qe.pw_output import FermiKind, PwOutput
from test_bands_dos_render import AL_FERMI, combined, with_parts
from test_plotting import CONFIG, load, render

from conftest import FIXTURES

# Two filled bands up to -0.5 eV, the next ones from 1.0 eV: a path gap of 1.5 eV for 4 electrons.
ENERGIES = np.array([[-4.0, -3.0, -3.5], [-2.0, -0.5, -1.0], [1.0, 2.0, 1.5], [3.0, 4.0, 3.5]])
VBM, CBM = -0.5, 1.0


def dataset_of(fermi: float | None, kind: FermiKind | None) -> BandsDataset:
    """The synthetic bands with the edges ``pw.x`` output would give them."""
    dataset = BandsDataset(
        folder=FIXTURES / "si_bands",
        bands=BandData(np.linspace(0, 1, ENERGIES.shape[1]), ENERGIES),
        source="gnu",
        fermi=fermi,
        fermi_kind=kind,
        ticks=[],
        labels=[],
        tick_source="nenhum",
    )
    band_edges(dataset, PwOutput(fermi=fermi, fermi_kind=kind, n_electrons=4.0))
    return dataset


def rendered(dataset: BandsDataset):
    module = BandsModule()
    params = module.default_params(CONFIG, dataset)
    return render(module, dataset, params, LIGHT)[1]


# -- (a) fixed occupations: as before ------------------------------------------------------------
def test_an_insulator_with_fixed_occupations_keeps_its_gap():
    _module, dataset, _params = load(FIXTURES / "si_bands")
    assert dataset.fermi_kind == "homo_lumo" and dataset.gap_note is None
    assert dataset.gap == pytest.approx(0.454, abs=0.01)
    assert rendered(dataset).notes == ()


@pytest.mark.parametrize("kind", ["homo", "homo_lumo"])
def test_fixed_occupations_are_not_checked_against_e_f(kind):
    dataset = dataset_of(5.0, kind)  # a HOMO far from the counted edges changes nothing
    assert dataset.gap == pytest.approx(CBM - VBM) and dataset.gap_note is None


# -- (b) a metal whose filled bands do not touch on the path -------------------------------------
@pytest.mark.parametrize("fermi", [-1.0, 1.5, VBM - 2 * EDGE_TOL, CBM + 2 * EDGE_TOL])
def test_e_f_inside_a_band_leaves_no_gap_and_a_note(fermi):
    dataset = dataset_of(fermi, "fermi")
    assert dataset.gap is None and dataset.vbm is None and dataset.cbm is None
    assert dataset.n_occupied is None
    assert (
        dataset.gap_note
        == GAP_OFF_PATH_NOTE
        == "gap indeterminado: E_F fora de [VBM, CBM] no caminho"
    )
    info = rendered(dataset)
    assert info.notes == (GAP_OFF_PATH_NOTE,)
    assert "E_gap" not in info.summary and "metálico" not in info.summary
    assert dataset.reference("vbm") == fermi  # no VBM: the reference falls back to E_F


def test_the_note_is_never_drawn_on_the_figure():
    dataset = dataset_of(-1.0, "fermi")
    module = BandsModule()
    params = module.default_params(CONFIG, dataset)
    params.show_legend, params.legend_gap = True, True
    figure, _info = render(module, dataset, params, LIGHT)
    texts = [t.get_text() for t in figure.findobj(match=lambda a: hasattr(a, "get_text"))]
    assert not any("indeterminado" in t or "E_{gap}" in t for t in texts)


# -- (c) an insulator with smearing ---------------------------------------------------------------
@pytest.mark.parametrize("fermi", [0.25, VBM, CBM, VBM - EDGE_TOL / 2, CBM + EDGE_TOL / 2])
def test_e_f_in_the_gap_keeps_the_counted_gap(fermi):
    dataset = dataset_of(fermi, "fermi")
    assert (dataset.vbm, dataset.cbm, dataset.n_occupied) == (VBM, CBM, 2)
    assert dataset.gap == pytest.approx(1.5) and dataset.gap_note is None
    info = rendered(dataset)
    assert "E_gap (no caminho) = 1.500 eV" in info.summary and info.notes == ()


def test_without_e_f_the_count_still_gives_the_gap_with_a_note():
    dataset = dataset_of(None, None)
    assert dataset.gap == pytest.approx(1.5)
    assert dataset.gap_note == GAP_NO_FERMI_NOTE
    assert rendered(dataset).notes == ("E_F não encontrado: gap pela contagem de elétrons",)


def test_a_metal_by_the_count_says_metallic_without_a_note():
    _module, dataset, _params = load(FIXTURES / "al_bands")  # 3 electrons: no band count
    info = rendered(dataset)
    assert "metálico" in info.summary and info.notes == ()


# -- bands + DOS and the field ----------------------------------------------------------------------
def test_bands_and_dos_carry_the_note_of_the_bands():
    module, dataset, params = combined()
    noted = with_parts(dataset, bands={"gap_note": GAP_OFF_PATH_NOTE}, dos={"fermi_scf": AL_FERMI})
    assert render(module, noted, params)[1].notes == (GAP_OFF_PATH_NOTE,)


def test_the_tooltip_of_the_band_gap_says_it_is_along_the_path():
    _module, bands, _params = load(FIXTURES / "al_bands")
    _module, dos, _params = load(FIXTURES / "al_pdos_flat")
    _module, pair, _params = combined()
    datasets = {"bands": bands, "pdos": dos, "bands_dos": pair}
    tooltips = {}
    for kind, dataset in datasets.items():
        module = next(m for m in REGISTRY if m.kind == kind)
        (field,) = [f for f in module.param_schema(dataset) if f.name == "legend_gap"]
        assert (field.section, field.kind) == ("Legenda", "bool")
        tooltips[kind] = field.tooltip
    path = "Gap ao longo do caminho de k; o gap indireto verdadeiro pode estar fora dele."
    assert tooltips["bands"].endswith(path) and tooltips["bands_dos"] == tooltips["bands"]
    assert "caminho" not in tooltips["pdos"]
