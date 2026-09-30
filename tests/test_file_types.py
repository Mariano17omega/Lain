from pathlib import Path

import pytest

from qe_studio.ui.file_types import file_visual, human_size, viewer_kind


@pytest.mark.parametrize(
    ("name", "icon"),
    [
        ("bands.in", "description"),
        ("scf.out", "terminal"),
        ("bands.dat.gnu", "analytics"),
        ("pdos.dat.pdos_atm#1(Al)_wfc#1(s)", "bar_chart"),
        ("bands.png", "image"),
        ("bands.svg", "polyline"),
        ("bands.pdf", "picture_as_pdf"),
        ("job.qsub", "code"),
        ("bands.plot", "tune"),
        ("whatever", "draft"),
    ],
)
def test_file_visual(name, icon):
    assert file_visual(Path(name))[0] == icon


def test_folder_visual():
    assert file_visual(Path("x"), is_dir=True) == ("folder", "icon_folder")


def test_viewer_kind(tmp_path):
    text = tmp_path / "band"
    text.write_text(" &plot nbnd= 1, nks= 1 /\n")
    binary = tmp_path / "al.wfc1"
    binary.write_bytes(b"\x00\x01")
    assert viewer_kind(Path("a.out")) == "text"
    assert viewer_kind(Path("a.png")) == "image"
    assert viewer_kind(Path("a.svg")) == "svg"
    assert viewer_kind(Path("a.pdf")) == "external"
    assert viewer_kind(Path("bands.plot")) == "text"
    assert viewer_kind(text) == "text"
    assert viewer_kind(binary) == "external"


def test_human_size():
    assert human_size(512) == "512 B"
    assert human_size(2400) == "2.3 KB"
    assert human_size(3 * 1024**2) == "3.0 MB"
