"""Spec 24 R2: names that never overwrite (``_1``, ``_2``…)."""

import threading

from qe_studio.core.unique_names import next_free, write_new


def test_next_free_of_a_file(tmp_path):
    path = tmp_path / "scf_convergido_si.in"
    assert next_free(path) == path
    path.write_text("a")
    assert next_free(path) == tmp_path / "scf_convergido_si_1.in"
    (tmp_path / "scf_convergido_si_1.in").write_text("b")
    assert next_free(path) == tmp_path / "scf_convergido_si_2.in"
    assert next_free(path, first=5) == tmp_path / "scf_convergido_si_5.in"
    assert not (tmp_path / "scf_convergido_si_2.in").exists()  # creates nothing


def test_next_free_of_a_folder_and_a_broken_link(tmp_path):
    folder = tmp_path / "relax.v2"
    folder.mkdir()
    assert next_free(folder) == tmp_path / "relax.v2_1"
    link = tmp_path / "x.in"
    link.symlink_to(tmp_path / "missing")
    assert next_free(link) == tmp_path / "x_1.in"


def test_write_new_never_overwrites_and_keeps_line_ends(tmp_path):
    path = tmp_path / "a.in"
    assert write_new(path, "one\r\n") == path
    assert write_new(path, "two\n") == tmp_path / "a_1.in"
    assert write_new(path, "três") == tmp_path / "a_2.in"
    assert path.read_bytes() == b"one\r\n"
    assert (tmp_path / "a_1.in").read_bytes() == b"two\n"
    assert (tmp_path / "a_2.in").read_text(encoding="utf-8") == "três"


def test_concurrent_writes_get_distinct_files(tmp_path):
    path = tmp_path / "scf.in"
    written: list = []
    start = threading.Barrier(8)

    def write(n: int) -> None:
        start.wait()
        written.append((write_new(path, f"writer {n}\n" * 200), n))

    threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({target for target, _ in written}) == 8
    for target, n in written:
        assert target.read_text() == f"writer {n}\n" * 200


def test_a_failed_write_leaves_no_file(tmp_path):
    path = tmp_path / "bad.in"
    try:
        write_new(path, "\ud800")  # a lone surrogate cannot be encoded
    except UnicodeEncodeError:
        pass
    else:
        raise AssertionError("expected an encoding error")
    assert list(tmp_path.iterdir()) == []
