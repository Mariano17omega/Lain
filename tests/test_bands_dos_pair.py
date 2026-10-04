"""Spec 22 R1–R2: which two folders make a bands + DOS figure, and the result that plots them."""

import shutil
from pathlib import Path

import pytest

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.bands_dos import BandsDosDataset, bands_dos_pair, pair_result
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.detection import PairTarget, detect_folder, plottable_modules
from qe_studio.core.plotting.session import load_plot, target_key
from qe_studio.core.sniff import SniffCache


def results(folder: Path):
    return detect_folder(folder, sniff=SniffCache().sniff)


@pytest.fixture
def mixed(demo_project) -> Path:
    """A folder with bands *and* a PDOS (detection says BANDS and PDOS)."""
    folder = demo_project / "05_mixed"
    shutil.copytree(demo_project / "03_bands", folder, ignore=shutil.ignore_patterns("tmp"))
    pdos = demo_project / "04_pdos"
    for name in ("nscf.out", "projwfc.out", "pdos.dat.pdos_tot"):
        shutil.copy(pdos / name, folder / name)
    shutil.copytree(pdos / "orbitals", folder / "orbitals")
    return folder


def test_a_bands_and_a_pdos_folder_pair_in_either_order(demo_project):
    bands, pdos = demo_project / "03_bands", demo_project / "04_pdos"
    for a, b in ((bands, pdos), (pdos, bands)):
        pair = bands_dos_pair(results(a), results(b))
        assert pair is not None
        assert (pair.bands.folder, pair.dos.folder) == (bands, pdos)
        assert (pair.bands.kind, pair.dos.kind) == ("bands", "pdos")


@pytest.mark.parametrize(
    "a, b",
    [
        ("03_bands", "03_bands"),
        ("04_pdos", "04_pdos"),
        ("01_relax", "04_pdos"),
        ("02_scf", "03_bands"),
    ],
)
def test_other_folders_make_no_pair(demo_project, a, b):
    assert bands_dos_pair(results(demo_project / a), results(demo_project / b)) is None


def test_a_folder_not_detected_yet_makes_no_pair(demo_project):
    assert bands_dos_pair(None, results(demo_project / "04_pdos")) is None
    assert bands_dos_pair(results(demo_project / "03_bands"), None) is None


def test_an_incomplete_pdos_makes_no_pair(demo_project):
    shutil.rmtree(demo_project / "04_pdos" / "orbitals")
    pdos = results(demo_project / "04_pdos")
    assert any(r.kind == "pdos" and not r.plottable for r in pdos)
    assert bands_dos_pair(results(demo_project / "03_bands"), pdos) is None


def test_a_folder_with_both_pairs_with_the_kind_it_misses(demo_project, mixed):
    assert {r.kind for r in results(mixed)} >= {"bands", "pdos"}
    with_bands = bands_dos_pair(results(mixed), results(demo_project / "03_bands"))
    assert with_bands is not None
    assert (with_bands.bands.folder, with_bands.dos.folder) == (demo_project / "03_bands", mixed)
    with_pdos = bands_dos_pair(results(demo_project / "04_pdos"), results(mixed))
    assert with_pdos is not None
    assert (with_pdos.bands.folder, with_pdos.dos.folder) == (mixed, demo_project / "04_pdos")


def test_two_folders_with_both_are_ambiguous(demo_project, mixed):
    other = demo_project / "06_mixed"
    shutil.copytree(mixed, other)
    assert bands_dos_pair(results(mixed), results(other)) is None


def test_the_pair_result_holds_both_parts_under_prefixed_roles(demo_project):
    bands, pdos = demo_project / "03_bands", demo_project / "04_pdos"
    pair = bands_dos_pair(results(bands), results(pdos))
    assert pair is not None
    module = module_for("bands_dos")
    result = pair_result(pair, module)
    assert result.kind == "bands_dos" and result.folder == bands and result.plottable
    assert result.parts == (pair.bands, pair.dos)
    assert result.plot_target == bands and result.plot_id == f"{bands}|{pdos}"
    assert result.files["bands.gnu"] == pair.bands.files["gnu"]
    assert result.files["dos.pdos_atm"] == pair.dos.files["pdos_atm"]
    assert all(module.role(role).label.startswith(("Bandas · ", "DOS · ")) for role in result.files)
    assert result.methods["bands.gnu"] == pair.bands.methods["gnu"]
    assert all(w.startswith(("Bandas: ", "DOS: ")) for w in result.warnings)


def test_the_pair_target_detects_and_pairs_in_the_worker(demo_project):
    bands, pdos = demo_project / "03_bands", demo_project / "04_pdos"
    cache = SniffCache()
    target = PairTarget(bands, pdos, cache.sniff)
    assert target_key(target) == f"plot:bands_dos:{bands}|{pdos}"
    assert target.kind == "bands_dos" and target.module is module_for("bands_dos")
    result, dataset = load_plot(target, cache.sniff)
    assert target_key(result) == target_key(target)
    assert isinstance(dataset, BandsDosDataset)
    assert dataset.folder == bands and dataset.bands.formula == "Al"
    assert dataset.dos.folder == pdos and dataset.bands_compound is not None


def test_the_pair_target_says_which_folder_is_gone(demo_project, tmp_path):
    bands, pdos, cache = demo_project / "03_bands", demo_project / "04_pdos", SniffCache()
    with pytest.raises(LoadError, match="Pasta da DOS não encontrada"):
        PairTarget(bands, tmp_path / "gone", cache.sniff).build()
    with pytest.raises(LoadError, match="Pasta das bandas não encontrada"):
        PairTarget(tmp_path / "gone", pdos, cache.sniff).build()


def test_the_pair_target_refuses_folders_that_no_longer_pair(demo_project):
    bands, pdos = demo_project / "03_bands", demo_project / "04_pdos"
    with pytest.raises(LoadError, match="não formam um par"):
        PairTarget(pdos, bands, SniffCache().sniff).build()  # the roles swapped


def test_the_module_is_never_detected_nor_offered_for_mapping(demo_project):
    for folder in sorted(p for p in demo_project.iterdir() if p.is_dir()):
        assert all(r.kind != "bands_dos" for r in results(folder)), folder.name
    module = module_for("bands_dos")
    assert module.plottable and not module.selectable
    assert module not in plottable_modules()
    assert {m.kind for m in plottable_modules()} == {"bands", "pdos", "relax", "scf"}
