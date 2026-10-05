"""``atomic_write_text`` (spec 27-3 R4): a unique temporary file, written to disk, then renamed."""

import os
import stat
import threading

import pytest

from qe_studio.core import appdirs
from qe_studio.core.appdirs import atomic_write_text, lock_path


def stray_temps(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_writes_and_replaces(tmp_path):
    target = tmp_path / "folders.json"
    atomic_write_text(target, "um")
    atomic_write_text(target, "dois ç")
    assert target.read_text(encoding="utf-8") == "dois ç"
    assert stray_temps(tmp_path) == []


def test_creates_the_folder(tmp_path):
    target = tmp_path / "a" / "b" / "x.json"
    atomic_write_text(target, "x")
    assert target.read_text() == "x"


def test_a_failure_in_the_replace_keeps_the_old_file_and_leaves_no_temp(tmp_path, monkeypatch):
    target = tmp_path / "x.plot"
    atomic_write_text(target, "old")

    def crash(src, dst):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="Input/output"):
        atomic_write_text(target, "new")
    assert target.read_text() == "old"
    assert stray_temps(tmp_path) == []


def test_a_failure_while_writing_leaves_no_temp(tmp_path, monkeypatch):
    target = tmp_path / "x.plot"

    def full_disk(fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", full_disk)
    with pytest.raises(OSError, match="No space"):
        atomic_write_text(target, "new")
    assert not target.exists() and stray_temps(tmp_path) == []


def test_the_text_is_flushed_to_disk_before_the_replace(tmp_path, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(
        os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1]
    )
    atomic_write_text(tmp_path / "x.json", "x")
    assert order[:2] == ["fsync", "replace"]


def test_the_temporary_name_is_not_fixed(tmp_path, monkeypatch):
    seen = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append(a.name), real_replace(a, b))[1])
    for _ in range(3):
        atomic_write_text(tmp_path / "x.json", "x")
    assert len(set(seen)) == 3 and all(n.startswith(".x.json.") for n in seen)


def test_concurrent_writers_never_share_a_temporary_file(tmp_path):
    target = tmp_path / "x.json"
    texts = ["a" * 200_000, "b" * 200_000]
    errors = []

    def writer(text):
        try:
            for _ in range(40):
                atomic_write_text(target, text)
        except Exception as exc:  # the old fixed ``.x.json.tmp`` made one of them fail
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in texts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert errors == []
    assert target.read_text() in texts  # one whole text, never a mix
    assert stray_temps(tmp_path) == []


def test_an_unusable_folder_raises_and_leaves_nothing(tmp_path):
    (tmp_path / "file").write_text("in the way")
    with pytest.raises(OSError):
        atomic_write_text(tmp_path / "file" / "x.json", "x")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_the_file_keeps_the_mode_of_the_umask_not_0600(tmp_path):
    old = os.umask(0o022)
    try:
        atomic_write_text(tmp_path / "x.plot", "x")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "x.plot").stat().st_mode) == 0o644


def test_the_lock_file_is_in_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(appdirs, "data_dir", lambda: tmp_path)
    assert lock_path() == tmp_path / "lain.lock"
