import shutil
from pathlib import Path

import pytest

from qe_studio.core.calculations import Method, module_for
from qe_studio.core.detection import FolderMemory, detect_folder, manual_result
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
    (result,) = detect(FIXTURES / "ni_pdos_spin")
    assert names(result, "nscf_out") == ["ni.dos.out"]
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


def test_manual_mapping_memory(tmp_path):
    folder = tmp_path / "odd"
    folder.mkdir()
    for name in ("al.scf.out", "bands.dat.gnu"):
        shutil.copy(FIXTURES / "al_bands" / name, folder / name)
    memory = FolderMemory(tmp_path / "memory.json")
    module = module_for("bands")
    mapping = {"scf_out": [folder / "al.scf.out"], "gnu": [folder / "bands.dat.gnu"]}
    result = manual_result(module, folder, mapping)
    assert result.complete and result.method is Method.MANUAL

    memory.set_mapping(folder, "bands", mapping)
    reloaded = FolderMemory(tmp_path / "memory.json")
    assert reloaded.mapping(folder, "bands") == mapping
    (detected,) = detect(folder, memory=reloaded)
    assert detected.methods["scf_out"] is Method.MANUAL

    reloaded.set_labels(folder, ["L", "G"])
    assert FolderMemory(tmp_path / "memory.json").labels(folder) == ["L", "G"]
    reloaded.clear_mapping(folder, "bands")
    assert reloaded.mapping(folder, "bands") is None


def test_folder_memory_follows_renames(tmp_path):
    run, sibling = tmp_path / "run", tmp_path / "run2"
    (run / "sub").mkdir(parents=True)
    sibling.mkdir()
    memory = FolderMemory(tmp_path / "memory.json")
    memory.set_mapping(run / "sub", "bands", {"gnu": [run / "sub" / "bands.dat.gnu"]})
    memory.set_labels(run, ["G", "X"])
    memory.set_labels(sibling, ["L"])  # shares the prefix "run", not the folder
    renamed = tmp_path / "renamed"
    run.rename(renamed)
    memory.rename(run, renamed)
    reloaded = FolderMemory(tmp_path / "memory.json")
    assert reloaded.labels(renamed) == ["G", "X"] and reloaded.labels(run) is None
    assert reloaded.mapping(renamed / "sub", "bands") == {
        "gnu": [renamed / "sub" / "bands.dat.gnu"]
    }
    assert reloaded.labels(sibling) == ["L"]


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
