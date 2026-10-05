import errno
import os
import sys

import pytest

from qe_studio.core import file_ops
from qe_studio.core.file_ops import overlaps, rename_error, rename_item


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Digite um nome."),
        ("   ", "Digite um nome."),
        ("a/b", "O nome não pode conter “/”."),
        (".", "Nome inválido."),
        ("..", "Nome inválido."),
        ("b.txt", "Já existe “b.txt” nesta pasta."),
        ("a.txt", None),  # unchanged: nothing to do
        ("c.txt", None),
    ],
)
def test_rename_error(tmp_path, name, message):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    assert rename_error(tmp_path / "a.txt", name) == message


def test_rename_file_and_folder(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    assert rename_item(tmp_path / "a.txt", "c.txt") == tmp_path / "c.txt"
    assert (tmp_path / "c.txt").read_text() == "a" and not (tmp_path / "a.txt").exists()
    (tmp_path / "run" / "sub").mkdir(parents=True)
    rename_item(tmp_path / "run", "run-01")
    assert (tmp_path / "run-01" / "sub").is_dir()


def test_rename_never_overwrites(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    with pytest.raises(FileExistsError):
        rename_item(tmp_path / "a.txt", "b.txt")
    assert (tmp_path / "a.txt").read_text() == "a" and (tmp_path / "b.txt").read_text() == "b"
    (tmp_path / "folder").mkdir()
    with pytest.raises(FileExistsError):
        rename_item(tmp_path / "a.txt", "folder")
    with pytest.raises(OSError, match="Nome inválido"):
        rename_item(tmp_path / "a.txt", "..")


def refuse_noreplace(monkeypatch, code=errno.ENOSYS):
    """The kernel (or filesystem) knows no RENAME_NOREPLACE: the portable branches run."""

    def unsupported(src, dst):
        raise OSError(code, os.strerror(code), str(dst))

    monkeypatch.setattr(file_ops, "_renameat2", unsupported)


@pytest.fixture(params=["renameat2", "link", "no-hard-links"])
def how(request, monkeypatch):
    """The three ways ``rename_item`` can move a file: the kernel's, ``link`` + ``unlink`` and,
    where hard links do not exist, the check followed by ``rename``."""
    if request.param != "renameat2":
        refuse_noreplace(monkeypatch)
    if request.param == "no-hard-links":

        def no_link(*_a, **_k):
            raise OSError(errno.EPERM, "Operation not permitted")

        monkeypatch.setattr(os, "link", no_link)
    return request.param


def create_after_the_check(monkeypatch, target, make):
    """Someone creates ``target`` right after ``rename_error`` looked: the window of spec 27-3 S3."""
    real = file_ops.rename_error

    def checked(path, name):
        error = real(path, name)
        make(target)
        return error

    monkeypatch.setattr(file_ops, "rename_error", checked)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rename replaces; Windows refuses")
def test_a_file_created_between_the_check_and_the_move_is_not_overwritten(
    tmp_path, monkeypatch, how
):
    (tmp_path / "a.txt").write_text("a")
    target = tmp_path / "b.txt"
    create_after_the_check(monkeypatch, target, lambda t: t.write_text("theirs"))
    if how == "no-hard-links":
        pytest.skip("the residual window of the last resort is documented, not closed")
    with pytest.raises(FileExistsError, match="Já existe “b.txt” nesta pasta"):
        rename_item(tmp_path / "a.txt", "b.txt")
    assert target.read_text() == "theirs" and (tmp_path / "a.txt").read_text() == "a"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rename replaces; Windows refuses")
def test_a_folder_created_between_the_check_and_the_move_is_not_overwritten(tmp_path, monkeypatch):
    """An empty directory is what POSIX ``rename`` would replace: the kernel branch refuses it."""
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "scf.in").write_text("x")
    target = tmp_path / "run2"
    create_after_the_check(monkeypatch, target, lambda t: t.mkdir())
    if not hasattr(file_ops.ctypes.CDLL(None), "renameat2"):
        pytest.skip("no renameat2 in this libc")
    with pytest.raises(FileExistsError):
        rename_item(tmp_path / "run", "run2")
    assert (tmp_path / "run" / "scf.in").is_file() and list(target.iterdir()) == []


def test_every_branch_renames_files_and_folders(tmp_path, how):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "run" / "sub").mkdir(parents=True)
    assert rename_item(tmp_path / "a.txt", "c.txt") == tmp_path / "c.txt"
    assert (tmp_path / "c.txt").read_text() == "a" and not (tmp_path / "a.txt").exists()
    rename_item(tmp_path / "run", "run-01")
    assert (tmp_path / "run-01" / "sub").is_dir() and not (tmp_path / "run").exists()


def test_every_branch_refuses_a_name_taken_before_the_call(tmp_path, how):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    with pytest.raises(FileExistsError):
        rename_item(tmp_path / "a.txt", "b.txt")
    assert (tmp_path / "b.txt").read_text() == "b"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_a_symlink_stays_a_symlink(tmp_path, how):
    (tmp_path / "real.txt").write_text("r")
    (tmp_path / "link").symlink_to("real.txt")
    rename_item(tmp_path / "link", "link2")
    moved = tmp_path / "link2"
    assert moved.is_symlink() and os.readlink(moved) == "real.txt"
    assert not (tmp_path / "link").is_symlink()


def test_unlink_failing_after_the_link_keeps_the_old_name(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("a")
    refuse_noreplace(monkeypatch)

    def no_unlink(path, *a, **k):
        if os.fspath(path).endswith("a.txt"):
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_unlink(path, *a, **k)

    real_unlink = os.unlink
    monkeypatch.setattr(os, "unlink", no_unlink)
    with pytest.raises(PermissionError):
        rename_item(tmp_path / "a.txt", "c.txt")
    assert (tmp_path / "a.txt").read_text() == "a" and not (tmp_path / "c.txt").exists()


def test_a_case_only_rename_of_the_same_item_still_works(tmp_path, monkeypatch):
    """On a case-insensitive disk ``a.txt`` and ``A.txt`` are one item: plain rename, since the
    kernel's refusal of an existing name would turn it down."""
    (tmp_path / "a.txt").write_text("a")
    moved = []
    monkeypatch.setattr(file_ops, "_rename_noreplace", lambda s, d: moved.append("noreplace"))
    monkeypatch.setattr(file_ops, "_taken", lambda path, target: False)
    monkeypatch.setattr(file_ops, "_same_item", lambda path, target: True)
    assert rename_item(tmp_path / "a.txt", "A.txt") == tmp_path / "A.txt"
    assert moved == [] and (tmp_path / "A.txt").exists()


def test_a_different_item_under_the_new_name_is_not_the_same_item(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    assert not file_ops._same_item(tmp_path / "a.txt", tmp_path / "b.txt")
    assert not file_ops._same_item(tmp_path / "a.txt", tmp_path / "missing")


def test_overlaps(tmp_path):
    folder = tmp_path / "proj" / "scf"
    assert overlaps(folder, tmp_path) and overlaps(tmp_path, folder) and overlaps(folder, folder)
    assert overlaps(folder, folder / "tmp" / "x")
    assert not overlaps(folder, tmp_path / "proj" / "bands")
    assert not overlaps(folder, tmp_path / "proj" / "scf2")
