"""Folder rules of the file panels, without Qt (spec 15 R5: ``core/files/paths``)."""

import os
from pathlib import Path

import pytest

from qe_studio.core.files.paths import count_entries, is_hidden, normalize_patterns, real_path


def test_patterns_are_matched_without_case_or_trailing_slash():
    patterns = normalize_patterns(["tmp", "*.save", "Orbitals/"])
    assert patterns == ["tmp", "*.save", "orbitals"]
    assert is_hidden("TMP", patterns) and is_hidden("al.save", patterns)
    assert is_hidden("orbitals", patterns) and not is_hidden("03_bands", patterns)
    assert not is_hidden("tmp2", patterns)


def test_entry_counts_skip_hidden_names(tmp_path):
    for name in ("a.in", "b.out", ".hidden", "sub"):
        (tmp_path / name).mkdir() if name == "sub" else (tmp_path / name).write_text("")
    assert count_entries(tmp_path) == 3
    assert count_entries(tmp_path / "missing") is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_unreadable_folder_has_no_count(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        assert count_entries(locked) is None
    finally:
        locked.chmod(0o755)


def test_real_path_follows_links(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert real_path(link / "x.in") == real.resolve() / "x.in"


def test_real_path_survives_a_loop_of_links(tmp_path, monkeypatch):
    """``Path.resolve`` raises on a loop before Python 3.13: the path, normalized as text."""

    def loop(self, strict=False):
        raise RuntimeError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", loop)
    assert real_path(tmp_path / "a" / ".." / "b") == tmp_path / "b"
