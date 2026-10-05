"""The loaders stop at ``cancel.check()`` (spec 27-4 R1.3): each raises ``Cancelled`` when the
task running it was cancelled, and does what it did before when nothing cancels it."""

import threading

import pytest

from qe_studio.core import cancel, textfile
from qe_studio.core.qe import projwfc
from qe_studio.core.qe.bands_x import read_filband, read_gnu
from qe_studio.core.qe.relax import read_relax
from qe_studio.core.qe.summary import summarize, summarize_lines
from qe_studio.core.tasks import run_task
from qe_studio.core.text_preview import read_preview
from synthetic import make_huge_relax

from conftest import FIXTURES

AL_GNU = FIXTURES / "al_bands/bands.dat.gnu"
AL_FILBAND = FIXTURES / "al_bands/bands.dat"


class FlaggedToken:
    cancelled = True


@pytest.fixture
def relax_output(tmp_path):
    path = make_huge_relax(tmp_path / "big.rel.out", mb=2)
    assert path.read_text().count("\n") > 2 * cancel.CHECK_EVERY_LINES
    return path


@pytest.fixture
def big_text(tmp_path):
    path = tmp_path / "big.out"
    path.write_text("a line of the output\n" * 200_000)  # 4.2 MB, above the 4 MB "large" mark
    return path


def pdos_files():
    return sorted((FIXTURES / "al_pdos_flat").glob("*pdos_atm*"))


# Every loader with what it needs; the first four are the ones of the spec's list of loops.
LOADERS = {
    "summarize": lambda tmp: summarize(tmp["relax"]),
    "summarize_lines": lambda tmp: summarize_lines(["line\n"] * 25_000),
    "parse_relax": lambda tmp: read_relax(tmp["relax"]),
    "load_pdos": lambda tmp: projwfc.load_pdos(pdos_files()),
    "read_gnu": lambda tmp: read_gnu(AL_GNU),
    "read_filband": lambda tmp: read_filband(AL_FILBAND.read_text()),
    "read_preview_full": lambda tmp: read_preview(tmp["text"], full=True),
    "read_slice_full": lambda tmp: textfile.read_slice(tmp["text"], full=True),
}


@pytest.fixture
def paths(relax_output, big_text):
    return {"relax": relax_output, "text": big_text}


@pytest.mark.parametrize("name", LOADERS)
def test_a_cancelled_task_stops_every_loader(name, paths):
    with cancel.bind(FlaggedToken()), pytest.raises(cancel.Cancelled):
        LOADERS[name](paths)


@pytest.mark.parametrize("name", LOADERS)
def test_without_a_task_every_loader_runs_as_before(name, paths):
    assert LOADERS[name](paths) is not None


def test_read_slice_whole_file_is_what_read_text_gives(big_text, tmp_path):
    assert textfile.read_slice(big_text, full=True).text == big_text.read_text()
    odd = tmp_path / "odd.txt"
    odd.write_bytes(b"caf\xc3\xa9 \xff bytes\n" * 100_001)  # not a multiple of the chunk, bad UTF-8
    assert textfile.read_slice(odd, full=True).text == odd.read_bytes().decode("utf-8", "replace")
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    assert textfile.read_slice(empty, full=True).text == ""


def cancelled_midway(fn, qtbot):
    """Run ``fn`` in a task, cancel it once it has started (and is held at a gate), then let it
    go. Returns what the callbacks got and what ``fn`` raised."""
    gate, got, raised = threading.Event(), [], []

    def work():
        gate.wait(5)
        try:
            return fn()
        except cancel.Cancelled:
            raised.append(True)
            raise

    handle = run_task(
        work, on_done=lambda r: got.append(("done", r)), on_error=lambda e: got.append(("error", e))
    )
    qtbot.waitUntil(lambda: handle.started, timeout=5000)
    handle.cancel()
    gate.set()
    assert handle.wait(5)
    qtbot.wait(50)
    return got, raised


@pytest.mark.parametrize("name", ["summarize", "load_pdos", "read_gnu", "read_preview_full"])
def test_a_loader_cancelled_in_a_task_reports_nothing(name, paths, qtbot):
    got, raised = cancelled_midway(lambda: LOADERS[name](paths), qtbot)
    assert raised == [True] and got == []
