import shutil
from pathlib import Path

import pytest

from qe_studio.core.calculations import Method
from qe_studio.core.detection import detect_folder
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES, copy_fixture


def detect(folder, **kwargs):
    return detect_folder(Path(folder), sniff=SniffCache().sniff, **kwargs)


def names(result, role):
    return [p.name for p in result.files.get(role, [])]


def test_al_bands_by_content():
    (result,) = detect(FIXTURES / "al_bands")
    assert result.badge == "BANDS" and result.complete
    assert result.method is Method.CONTENT  # tutorial names: al.scf.out, al.band.in
    assert names(result, "scf_out") == ["al.scf.out"]
    assert names(result, "bands_in") == ["al.band.in"]
    assert names(result, "bandsx_out") == ["bands.out"]
    assert names(result, "bands_out") == ["al.band.out"]
    assert names(result, "gnu") == ["bands.dat.gnu"]
    assert not result.warnings


def test_prd_named_bands_folder(tmp_path):
    folder = tmp_path / "03_bands"
    folder.mkdir()
    src = FIXTURES / "al_bands"
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
    ]:
        shutil.copy(src / old, folder / new)
    (result,) = detect(folder)
    assert result.method is Method.NAME
    assert names(result, "bandsx_out") == ["bands_pp.out"]
    assert names(result, "bands_out") == ["bands.out"]


def test_pdos_prd_layout_by_name(al_pdos_orbitals):
    (result,) = detect(al_pdos_orbitals)
    assert result.badge == "PDOS" and result.complete
    assert result.method is Method.NAME
    assert len(result.files["pdos_atm"]) == 2
    assert all(p.parent.name == "orbitals" for p in result.files["pdos_atm"])
    assert names(result, "pdos_tot") == ["pdos.dat.pdos_tot"]


def test_pdos_flat_layout_by_content():
    (result,) = detect(FIXTURES / "al_pdos_flat")
    assert result.complete and result.method is Method.CONTENT
    assert names(result, "projwfc_out") == ["al.projwfc.out"]


def test_pdos_spin_names():
    (result,) = detect(FIXTURES / "qe731_ni_spin_pdos")
    assert names(result, "nscf_out") == ["ni.nscf.out"]
    assert names(result, "projwfc_out") == ["ni.pdos.out"]


def test_relax():
    (result,) = detect(FIXTURES / "si_relax")
    assert result.badge == "RELAX" and result.complete and result.plottable


def test_scf_from_sibling_folder(tmp_path):
    scf_dir = tmp_path / "02_scf"
    bands_dir = tmp_path / "03_bands"
    scf_dir.mkdir()
    bands_dir.mkdir()
    shutil.copy(FIXTURES / "al_bands/al.scf.out", scf_dir / "scf.out")
    for name in ("al.band.in", "bands.out", "bands.dat.gnu"):
        shutil.copy(FIXTURES / "al_bands" / name, bands_dir / name)
    (result,) = detect(bands_dir)
    assert result.complete
    assert result.file("scf_out") == scf_dir / "scf.out"
    assert result.methods["scf_out"] is Method.INFERRED
    assert result.method is Method.INFERRED
    (scf,) = detect(scf_dir)
    assert scf.badge == "SCF"


def test_missing_scf_is_reported(tmp_path):
    folder = tmp_path / "bands"
    folder.mkdir()
    shutil.copy(FIXTURES / "al_bands/bands.dat.gnu", folder)
    (result,) = detect(folder)
    assert not result.complete
    assert result.missing == ["scf_out"]
    assert any("sem rótulos" in w for w in result.warnings)


def test_kpoint_mismatch_warns(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    (folder / "al.band.out").unlink()
    text = (folder / "al.band.in").read_text().replace("00.000 0.000 00.000 30  !G", "0 0 0 31 !G")
    (folder / "al.band.in").write_text(text)
    (result,) = detect(folder)
    assert any("91 pontos k" in w and "92" in w for w in result.warnings)


def test_empty_and_calc_folders(tmp_path):
    assert detect(tmp_path) == []
    shutil.copy(FIXTURES / "al_bands/bands.out", tmp_path / "some.log.out")
    (result,) = detect(tmp_path)
    assert result.badge in {"BANDS", "CALC"}
    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(FIXTURES / "al_pdos_flat/al.projwfc.in", other)
    (other / "dos.out").write_text("     Program DOS v.7.1 starts\n   JOB DONE.\n")
    (calc,) = detect(other)
    assert calc.badge == "CALC"


def test_each_file_is_sniffed_once_per_detection(tmp_path):
    """Spec 14 R3: one sniff per file, whichever modules ask, neighbour folders included."""
    (tmp_path / "02_scf").mkdir()
    shutil.copy(FIXTURES / "al_pdos_flat/al.scf.out", tmp_path / "02_scf/scf.out")
    folder = tmp_path / "03_calc"
    folder.mkdir()
    for src in (FIXTURES / "al_bands").iterdir():
        if src.name != "al.scf.out":
            shutil.copy(src, folder / src.name)
    for src in (FIXTURES / "al_pdos_flat").iterdir():
        if src.name != "al.scf.out":
            shutil.copy(src, folder / src.name)
    cache = SniffCache()
    calls: dict[Path, int] = {}

    def counting(path):
        calls[path] = calls.get(path, 0) + 1
        return cache.sniff(path)

    results = detect_folder(folder, sniff=counting)
    assert sorted(r.badge for r in results) == ["BANDS", "PDOS"]
    assert all(r.methods["scf_out"] is Method.INFERRED for r in results)
    assert calls[tmp_path / "02_scf/scf.out"] == 1  # both modules looked for it there
    assert max(calls.values()) == 1
    assert set(calls) >= set(folder.iterdir())


def test_multiple_pdos_sets_warn(al_pdos_orbitals):
    for path in (al_pdos_orbitals / "orbitals").iterdir():
        shutil.copy(path, al_pdos_orbitals / "orbitals" / path.name.replace("pdos.dat", "old"))
    (result,) = detect(al_pdos_orbitals)
    assert len(result.files["pdos_atm"]) == 2
    assert any("conjuntos de PDOS" in w for w in result.warnings)


@pytest.mark.parametrize("name", ["tmp", "x.save", "plots"])
def test_ignored_subfolders_are_not_scanned(tmp_path, name):
    sub = tmp_path / name
    sub.mkdir()
    shutil.copy(FIXTURES / "al_pdos_flat/pdos.dat.pdos_tot", sub)
    assert detect(tmp_path) == []
