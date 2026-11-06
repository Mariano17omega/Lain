"""Spec 46 R5.3: where the "Print" of the 3D window goes (``core/structure3d/image_file.py``, no Qt):
the name from the project root, ``plots/`` made but never its parent, and a file that exists never
overwritten."""

import pytest

from qe_studio.core.plotting.names import MAX_STEM_BYTES
from qe_studio.core.structure3d.image_file import print_stem, save_png

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(200))


def test_the_stem_is_the_folders_from_the_root_then_the_file_and_3d(tmp_path):
    root = tmp_path / "projetos"
    assert print_stem(root / "ilita" / "Analise_1" / "scf.in", root) == "ilita-Analise_1-scf-3d"
    assert (
        print_stem(root / "ilita" / "si.scf.in", root) == "ilita-si.scf-3d"
    )  # last extension only


def test_a_file_in_the_root_itself_has_no_prefix(tmp_path):
    assert print_stem(tmp_path / "scf.in", tmp_path) == "scf-3d"


def test_outside_the_root_or_without_one_the_prefix_is_the_folders_name(tmp_path):
    root = tmp_path / "projetos"
    elsewhere = tmp_path / "outro" / "Analise_1" / "scf.in"
    assert print_stem(elsewhere, root) == "Analise_1-scf-3d"
    assert print_stem(elsewhere, None) == "Analise_1-scf-3d"
    assert print_stem("scf.in", None) == "scf-3d"  # no folder at all


def test_a_long_name_is_cut_by_whole_folders_from_the_left(tmp_path):
    root = tmp_path / "raiz"
    deep = root.joinpath(*(f"{'p' * 30}{n}" for n in range(12)), "calculo")
    stem = print_stem(deep / "scf.in", root)
    assert len(stem.encode()) <= MAX_STEM_BYTES
    assert stem.endswith("-calculo-scf-3d")  # the simulation's folder and the file stay
    assert not stem.startswith(("-", "."))


def test_save_png_makes_plots_and_writes_the_bytes(tmp_path):
    target = save_png(tmp_path, "ilita-scf-3d", PNG)
    assert target == tmp_path / "plots" / "ilita-scf-3d.png"
    assert target.read_bytes() == PNG
    assert list((tmp_path / "plots").iterdir()) == [target]  # no temporary left


def test_save_png_never_overwrites_and_numbers_from_two(tmp_path):
    first = save_png(tmp_path, "scf-3d", PNG)
    second = save_png(tmp_path, "scf-3d", b"second")
    third = save_png(tmp_path, "scf-3d", b"third")
    assert [p.name for p in (first, second, third)] == [
        "scf-3d.png",
        "scf-3d_2.png",
        "scf-3d_3.png",
    ]
    assert first.read_bytes() == PNG  # the first one is as it was
    assert second.read_bytes() == b"second" and third.read_bytes() == b"third"


def test_save_png_into_an_existing_plots_folder_keeps_what_is_there(tmp_path):
    plots = tmp_path / "plots"
    plots.mkdir()
    (plots / "bands.png").write_bytes(b"a figure")
    target = save_png(tmp_path, "scf-3d", PNG)
    assert target.parent == plots and (plots / "bands.png").read_bytes() == b"a figure"


def test_a_folder_that_is_gone_is_an_error_and_is_not_recreated(tmp_path):
    gone = tmp_path / "sumiu"
    with pytest.raises(FileNotFoundError):
        save_png(gone, "scf-3d", PNG)
    assert not gone.exists()
