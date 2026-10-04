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


def test_make_new_dir_numbers_folders_at_the_end(tmp_path):
    from qe_studio.core.unique_names import make_new_dir, next_free_dir

    base = tmp_path / "bandas_Al.v2"
    assert next_free_dir(base) == base
    assert make_new_dir(base) == base and base.is_dir()
    assert next_free_dir(base) == tmp_path / "bandas_Al.v2_1"
    assert make_new_dir(base) == tmp_path / "bandas_Al.v2_1"
    (tmp_path / "bandas_Al.v2_2").write_text("a file takes the name too")
    assert make_new_dir(base) == tmp_path / "bandas_Al.v2_3"
    assert (tmp_path / "bandas_Al.v2_2").read_text() == "a file takes the name too"


def test_make_new_dir_moves_on_when_the_name_is_taken_meanwhile(tmp_path, monkeypatch):
    from qe_studio.core import unique_names

    base = tmp_path / "pdos_Si"
    real = unique_names.next_free_dir
    taken = []

    def racing(path):
        target = real(path)
        if not taken:  # another process creates it between the check and the mkdir
            target.mkdir()
            taken.append(target)
        return target

    monkeypatch.setattr(unique_names, "next_free_dir", racing)
    assert unique_names.make_new_dir(base) == tmp_path / "pdos_Si_1"
    assert taken == [base]
