"""Folder rules of the file panels, without Qt (spec 15 R5: ``core/paths``)."""

import os

import pytest

from qe_studio.core.paths import count_entries, is_hidden, normalize_patterns


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
