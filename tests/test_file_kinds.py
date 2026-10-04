from pathlib import Path

import pytest

from qe_studio.core.file_kinds import human_size, is_job_log, status_label, viewer_kind
from qe_studio.core.sniff import FileKind, FileSniff
from qe_studio.ui.file_types import file_visual, level_token


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
        ("job.o12345", "assignment_late"),
        ("job.e12345", "assignment_late"),
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
    assert viewer_kind(Path("job.o123")) == "text"
    assert viewer_kind(text) == "text"
    assert viewer_kind(binary) == "external"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("job.o123", True),
        ("run.O99", True),
        ("job.o123.4", True),
        ("job.o123-4", True),
        ("job.e123", True),
        ("scf.out", False),
        ("a.o", False),
        ("job.o", False),
        ("foo.obj", False),
        ("bands.dat", False),
    ],
)
def test_is_job_log(name, expected):
    assert is_job_log(Path(name)) is expected


def test_status_label():
    log = Path("job.o1")
    assert status_label(log, 0, None) == ("SEM ERROS", "success")
    assert status_label(log, 12, None) == ("ERRO", "error")
    # pw.x writing to the queue log: its own state wins over "content = error".
    done = FileSniff(log, FileKind.PW_OUT, job_done=True)
    assert status_label(log, 4096, done) == ("OK", "success")
    cut = FileSniff(log, FileKind.PW_OUT, job_done=False)
    assert status_label(log, 4096, cut) == ("INCOMPLETO", "warning")
    warned = FileSniff(Path("scf.out"), FileKind.PW_OUT, job_done=True, warnings=("x",))
    assert status_label(Path("scf.out"), 10, warned) == ("AVISO", "warning")
    assert status_label(Path("scf.out"), 10, None) is None
    assert status_label(log, 12, FileSniff(log, FileKind.UNKNOWN)) == ("ERRO", "error")


def test_human_size():
    assert human_size(512) == "512 B"
    assert human_size(2400) == "2.3 KB"
    assert human_size(3 * 1024**2) == "3.0 MB"


def test_levels_map_to_theme_tokens():
    assert [level_token(level) for level in ("success", "warning", "error")] == [
        "success",
        "warning",
        "error",
    ]
    assert level_token("other") == "text_dim"
