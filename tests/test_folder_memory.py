"""``FolderMemory``: manual mappings and k-point labels per folder, keyed relative to the project
root (spec 14 R7)."""

import json
import shutil
from pathlib import Path

from qe_studio.core.calculations import Method, module_for
from qe_studio.core.detection import detect_folder, manual_result
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES


def detect(folder, **kwargs):
    return detect_folder(Path(folder), sniff=SniffCache().sniff, **kwargs)


def stored(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bands_folder(folder: Path) -> Path:
    folder.mkdir(parents=True)
    for name in ("al.scf.out", "bands.dat.gnu"):
        shutil.copy(FIXTURES / "al_bands" / name, folder / name)
    return folder


def test_manual_mapping_memory(tmp_path):
    folder = bands_folder(tmp_path / "odd")
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


def test_keys_and_files_are_relative_to_the_root(tmp_path):
    root = tmp_path / "projeto"
    folder = bands_folder(root / "03_bands")
    scf = root / "02_scf" / "scf.out"
    scf.parent.mkdir()
    shutil.copy(FIXTURES / "al_bands/al.scf.out", scf)
    memory = FolderMemory(tmp_path / "folders.json", root=root)
    memory.set_mapping(folder, "bands", {"scf_out": [scf], "gnu": [folder / "bands.dat.gnu"]})
    memory.set_labels(root, ["G"])
    data = stored(tmp_path / "folders.json")
    assert data["version"] == 2
    assert data["folders"]["03_bands"]["mappings"]["bands"] == {
        "scf_out": ["../02_scf/scf.out"],
        "gnu": ["bands.dat.gnu"],
    }
    assert data["folders"]["."]["labels"] == ["G"]


def test_a_copy_of_the_project_keeps_mappings_and_labels(tmp_path):
    """Decision 4: the same relative keys under another ``local_root``."""
    root = tmp_path / "projeto"
    folder = bands_folder(root / "a" / "b")
    memory = FolderMemory(tmp_path / "folders.json", root=root)
    memory.set_mapping(folder, "bands", {"gnu": [folder / "bands.dat.gnu"]})
    memory.set_labels(folder, ["L", "G"])
    copy = tmp_path / "outra_maquina"
    shutil.copytree(root, copy)
    shutil.rmtree(root)

    elsewhere = FolderMemory(tmp_path / "folders.json", root=copy)
    assert elsewhere.mapping(copy / "a" / "b", "bands") == {
        "gnu": [copy / "a" / "b" / "bands.dat.gnu"]
    }
    assert elsewhere.labels(copy / "a" / "b") == ["L", "G"]
    memory.set_root(copy)  # a config reload pointing to the copy
    assert memory.labels(copy / "a" / "b") == ["L", "G"]


def test_folders_outside_the_root_keep_absolute_keys(tmp_path):
    root, outside = tmp_path / "projeto", bands_folder(tmp_path / "fora")
    root.mkdir()
    memory = FolderMemory(tmp_path / "folders.json", root=root)
    memory.set_mapping(outside, "bands", {"gnu": [outside / "bands.dat.gnu"]})
    key = f"abs:{outside.resolve()}"
    assert stored(tmp_path / "folders.json")["folders"][key]["mappings"]["bands"] == {
        "gnu": ["bands.dat.gnu"]
    }
    assert FolderMemory(tmp_path / "folders.json", root=root).mapping(outside, "bands") == {
        "gnu": [outside / "bands.dat.gnu"]
    }
    memory.set_root(tmp_path)  # now inside the root: re-keyed
    assert set(stored(tmp_path / "folders.json")["folders"]) == {"fora"}
    assert memory.mapping(outside, "bands") == {"gnu": [outside / "bands.dat.gnu"]}


def test_a_folder_named_version_is_just_a_folder(tmp_path):
    root = tmp_path / "projeto"
    (root / "version").mkdir(parents=True)
    FolderMemory(tmp_path / "folders.json", root=root).set_labels(root / "version", ["X"])
    assert FolderMemory(tmp_path / "folders.json", root=root).labels(root / "version") == ["X"]


def test_old_absolute_keys_migrate_once(tmp_path):
    root = tmp_path / "projeto"
    folder = bands_folder(root / "03_bands")
    outside = bands_folder(tmp_path / "fora")
    path = tmp_path / "folders.json"
    old = {
        str(folder.resolve()): {
            "mappings": {"bands": {"gnu": [str(folder / "bands.dat.gnu")]}},
            "labels": ["L", "G"],
        },
        str(outside.resolve()): {"labels": ["X"]},
    }
    path.write_text(json.dumps(old), encoding="utf-8")

    memory = FolderMemory(path, root=root)
    assert memory.mapping(folder, "bands") == {"gnu": [folder / "bands.dat.gnu"]}
    assert memory.labels(folder) == ["L", "G"]
    assert memory.labels(outside) == ["X"]
    data = stored(path)  # rewritten on the first read
    assert data["version"] == 2
    assert data["folders"]["03_bands"] == {
        "mappings": {"bands": {"gnu": ["bands.dat.gnu"]}},
        "labels": ["L", "G"],
    }
    assert data["folders"][f"abs:{outside.resolve()}"] == {"labels": ["X"]}
    before = path.read_text(encoding="utf-8")
    assert FolderMemory(path, root=root).labels(folder) == ["L", "G"]
    assert path.read_text(encoding="utf-8") == before  # version 2: nothing to migrate


def test_rename_with_relative_keys(tmp_path):
    root = tmp_path / "projeto"
    run, scf = bands_folder(root / "run" / "sub"), root / "02_scf" / "scf.out"
    scf.parent.mkdir()
    scf.write_text("")
    memory = FolderMemory(tmp_path / "folders.json", root=root)
    memory.set_mapping(run, "bands", {"scf_out": [scf], "gnu": [run / "bands.dat.gnu"]})
    memory.set_labels(root / "run", ["G", "X"])

    (root / "run").rename(root / "renamed")
    memory.rename(root / "run", root / "renamed")
    (root / "02_scf").rename(root / "01_scf")
    memory.rename(root / "02_scf", root / "01_scf")

    reloaded = FolderMemory(tmp_path / "folders.json", root=root)
    assert reloaded.labels(root / "renamed") == ["G", "X"]
    assert reloaded.labels(root / "run") is None
    sub = root / "renamed" / "sub"
    assert reloaded.mapping(sub, "bands") == {
        "scf_out": [root / "01_scf" / "scf.out"],
        "gnu": [sub / "bands.dat.gnu"],
    }
    assert set(stored(tmp_path / "folders.json")["folders"]) == {"renamed", "renamed/sub"}


def test_corrupt_file_is_set_aside(tmp_path):
    path = tmp_path / "folders.json"
    path.write_text('{"/a": {"labels": ["G"]', encoding="utf-8")
    memory = FolderMemory(path, root=tmp_path)
    warning = memory.load_warning()
    assert warning is not None and "corrompido" in warning
    (copy,) = tmp_path.glob("folders.json.corrompido-*")
    assert copy.read_text(encoding="utf-8") == '{"/a": {"labels": ["G"]'
    assert str(copy) in warning
    assert memory.labels(tmp_path) is None  # starts empty

    memory.set_labels(tmp_path, ["X"])  # a new file; the copy stays as it was
    assert stored(path)["folders"]["."] == {"labels": ["X"]}
    assert copy.read_text(encoding="utf-8") == '{"/a": {"labels": ["G"]'
    assert FolderMemory(path, root=tmp_path).load_warning() is None


def test_unexpected_json_is_set_aside_too(tmp_path):
    for n, content in enumerate(("[1, 2]", '{"version": 7, "folders": {}}')):
        path = tmp_path / f"m{n}.json"
        path.write_text(content, encoding="utf-8")
        assert "corrompido" in (FolderMemory(path).load_warning() or "")
        assert len(list(tmp_path.glob(f"m{n}.json.corrompido-*"))) == 1
        assert not path.exists()


def test_missing_file_is_silently_empty(tmp_path):
    memory = FolderMemory(tmp_path / "folders.json", root=tmp_path)
    assert memory.load_warning() is None
    assert memory.labels(tmp_path) is None
    assert not (tmp_path / "folders.json").exists()
