"""core/folder_index (spec 18 R2.2): the palette's folder list, built off the GUI thread."""

import os
from pathlib import Path

from qe_studio.core.folder_index import list_folders


def tree(root: Path, *folders: str) -> Path:
    for folder in folders:
        (root / folder).mkdir(parents=True)
    return root


def names(root: Path, found: list[Path]) -> list[str]:
    return [p.relative_to(root).as_posix() for p in found]


def test_lists_every_folder_below_the_root_sorted(tmp_path):
    tree(tmp_path, "b/x", "a", "a/deep/er")
    (tmp_path / "file.txt").write_text("not a folder")
    found = list_folders(tmp_path, [])
    assert names(tmp_path, found) == ["a", "a/deep", "a/deep/er", "b", "b/x"]


def test_hidden_and_dotted_folders_are_skipped_with_their_children(tmp_path):
    tree(tmp_path, "run/tmp/inner", "run/out.save/x", "run/keep", ".git/objects", "run/ORBITALS/z")
    found = list_folders(tmp_path, ["tmp", "*.save", "orbitals/"])
    assert names(tmp_path, found) == ["run", "run/keep"]


def test_symlinked_folders_are_not_followed(tmp_path):
    tree(tmp_path, "real/child")
    os.symlink(tmp_path / "real", tmp_path / "link", target_is_directory=True)
    os.symlink(tmp_path, tmp_path / "real" / "loop", target_is_directory=True)
    assert names(tmp_path, list_folders(tmp_path, [])) == ["real", "real/child"]


def test_the_limit_keeps_the_shallow_folders(tmp_path):
    tree(tmp_path, "a/a1/a2", "b", "c")
    found = list_folders(tmp_path, [], limit=3)
    assert len(found) == 3
    assert names(tmp_path, found) == ["a", "b", "c"]


def test_a_cancelled_walk_returns_what_it_has(tmp_path):
    tree(tmp_path, "a", "b/c")
    assert list_folders(tmp_path, [], cancelled=lambda: True) == []


def test_a_missing_root_gives_nothing(tmp_path):
    assert list_folders(tmp_path / "gone", []) == []
