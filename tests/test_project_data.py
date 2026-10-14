"""Where the settings of a root live (spec 48 R1): ``locate``, ``describe`` and ``StoreFile``."""

import contextlib
import json
import os
from pathlib import Path

import pytest

from qe_studio.core.appdirs import data_dir
from qe_studio.core.project_data import (
    FALLBACK_DIR,
    PROJECT_DATA_DIR,
    StoreFile,
    describe,
    fallback_folder,
    locate,
)

as_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions"
)


@contextlib.contextmanager
def read_only(folder: Path):
    """``folder`` without write permission while the block runs (tmp_path must be removable)."""
    folder.chmod(0o555)
    try:
        yield folder
    finally:
        folder.chmod(0o755)


def test_a_writable_root_without_the_folder_gets_it_but_nothing_is_made(tmp_path):
    location = locate(tmp_path)
    assert location.folder == tmp_path / PROJECT_DATA_DIR
    assert not location.fallback and location.notice is None
    assert not (tmp_path / PROJECT_DATA_DIR).exists()
    assert list(tmp_path.iterdir()) == []


def test_an_existing_writable_folder_is_used(tmp_path):
    (tmp_path / PROJECT_DATA_DIR).mkdir()
    location = locate(tmp_path)
    assert location.folder == tmp_path / PROJECT_DATA_DIR and not location.fallback


def test_a_file_named_like_the_folder_falls_back_and_says_so(tmp_path):
    (tmp_path / PROJECT_DATA_DIR).write_text("not a folder")
    location = locate(tmp_path)
    assert location.fallback and location.folder == fallback_folder(tmp_path)
    assert location.notice is not None
    assert "não é uma pasta" in location.notice
    assert str(tmp_path) in location.notice and str(location.folder) in location.notice


def test_a_broken_symlink_falls_back(tmp_path):
    (tmp_path / PROJECT_DATA_DIR).symlink_to(tmp_path / "gone")
    location = locate(tmp_path)
    assert location.fallback and "não é uma pasta" in (location.notice or "")


@as_root
def test_a_read_only_root_falls_back_and_says_so(tmp_path):
    root = tmp_path / "raiz"
    root.mkdir()
    with read_only(root):
        location = locate(root)
    assert location.fallback and location.folder == fallback_folder(root)
    assert location.notice is not None
    assert "não é gravável" in location.notice
    assert str(root) in location.notice and str(location.folder) in location.notice
    assert not (root / PROJECT_DATA_DIR).exists()


@as_root
def test_a_read_only_settings_folder_falls_back(tmp_path):
    folder = tmp_path / PROJECT_DATA_DIR
    folder.mkdir()
    with read_only(folder):
        location = locate(tmp_path)
    assert location.fallback and "não é gravável" in (location.notice or "")


def test_a_root_that_is_not_a_folder_falls_back_without_a_notice(tmp_path):
    location = locate(tmp_path / "missing")
    assert location.fallback and location.notice is None
    assert location.folder.parent == data_dir() / FALLBACK_DIR
    assert not location.folder.exists()


def test_each_root_has_its_own_stable_fallback(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert fallback_folder(a) != fallback_folder(b)
    assert fallback_folder(a) == fallback_folder(a) == fallback_folder(tmp_path / "x" / ".." / "a")
    assert len(fallback_folder(a).name) == 16


def test_describe_is_the_folder_or_nenhuma(tmp_path):
    assert describe(tmp_path) == str(tmp_path / PROJECT_DATA_DIR)
    assert describe(tmp_path / "missing") == "nenhuma"


# -- StoreFile ---------------------------------------------------------------------------------
def test_a_store_file_with_a_path_is_fixed(tmp_path):
    file = StoreFile("x.json", tmp_path / "mine.json")
    assert not file.follow(tmp_path)
    assert file.path == tmp_path / "mine.json" and file.legacy is None


def test_a_store_file_follows_the_root(tmp_path):
    file = StoreFile("x.json", None)
    assert file.path == data_dir() / "x.json" and file.legacy is None  # before any root
    assert file.follow(tmp_path)
    assert file.path == tmp_path / PROJECT_DATA_DIR / "x.json"
    assert file.legacy == data_dir() / "x.json"
    assert not file.follow(tmp_path)  # the same folder: nothing to forget
    assert not file.follow(None)


def test_the_legacy_file_is_read_but_never_set_aside(tmp_path):
    file = StoreFile("x.json", None)
    file.follow(tmp_path)
    assert file.read_legacy() is None  # none there
    data_dir().mkdir(parents=True, exist_ok=True)
    (data_dir() / "x.json").write_text(json.dumps({"a": 1}))
    assert file.read_legacy() == {"a": 1}
    (data_dir() / "x.json").write_text("{broken")
    assert file.read_legacy() is None
    assert sorted(p.name for p in data_dir().iterdir()) == ["x.json"]
