import pytest

from qe_studio.core.file_ops import rename_error, rename_item


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
