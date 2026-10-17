"""Spec 50 R2: the red "ERRO" tag of a tree folder with a CRASH file or a job log with content."""

from collections import Counter

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor

from grid_helpers import tree_names
from qe_studio.ui.painting import badge_layout
from qe_studio.ui.widgets.common import viewport_of

FOLDERS = ["01_relax", "02_scf", "03_bands", "04_pdos"]
PREFIX = "Erro de simulação"


@pytest.fixture
def failed(demo_project):
    """03_bands has a CRASH, 02_scf a job.o with content; the other two do not fail: 04_pdos has an
    empty job.o and 01_relax only a job.e. Ask for it before the window: files exist at the start."""
    (demo_project / "03_bands" / "CRASH").write_text("")
    (demo_project / "02_scf" / "job.o1").write_text("mpirun noticed that process exited")
    (demo_project / "04_pdos" / "job.o2").write_text("")
    (demo_project / "01_relax" / "job.e3").write_text("warning")
    return demo_project


def detected(qtbot, window, project):
    qtbot.waitUntil(lambda: tree_names(window) == FOLDERS, timeout=5000)
    for name in FOLDERS:
        window.service.detect_now(project / name)
    qtbot.wait(50)  # the repaint the detections ask for


def row(window, folder):
    tree = window.explorer.tree
    index = window.explorer.proxy.index_for(folder)
    return index, tree.visualRect(index)


def tip(window, folder) -> str:
    """The tooltip over the rightmost badge of the folder's row."""
    index, rect = row(window, folder)
    delegate = window.explorer.tree.itemDelegate()
    return delegate._tooltip_at(QPoint(rect.right() - 12, rect.center().y()), rect, index)


def is_red(color) -> bool:
    """The background of the error badge in both themes (62, 28, 39 / 254, 242, 242): red above
    green and blue, green not above blue. The other badges' backgrounds fail one of the three."""
    return (
        color.red() - color.green() >= 10
        and color.red() - color.blue() >= 10
        and color.green() - color.blue() <= 6
    )


def tagged(window, folder) -> bool:
    """Is the badge at the right edge of the folder's row the red one? The commonest color inside
    the place of an ERRO badge is the badge's background (text and border are fewer pixels)."""
    _index, rect = row(window, folder)
    box = badge_layout([("ERRO", None)], rect.right() - 6, rect.center().y() + 0.5)[0][0].toRect()
    image = viewport_of(window.explorer.tree).grab().toImage()
    colors = Counter(
        image.pixelColor(x, y).rgb()
        for x in range(box.left() + 2, box.right() - 1)
        for y in range(box.top() + 2, box.bottom() - 1)
    )
    return is_red(QColor(colors.most_common(1)[0][0]))


def test_the_tooltip_names_the_file_that_caused_the_error(qtbot, failed, main_window):
    detected(qtbot, main_window, failed)
    assert tip(main_window, failed / "03_bands") == f"{PREFIX}: arquivo CRASH"
    assert tip(main_window, failed / "02_scf") == f"{PREFIX}: job.o1 não está vazio"


def test_a_clean_folder_an_empty_log_and_a_stderr_log_have_no_tag(qtbot, failed, main_window):
    detected(qtbot, main_window, failed)
    for name in ("04_pdos", "01_relax"):
        assert main_window.service.peek_error(failed / name) is None
        assert not tip(main_window, failed / name).startswith(PREFIX)


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_the_tag_is_painted_red_on_the_failed_folders_only(qtbot, failed, main_window, mode):
    main_window.theme.set_mode(mode)
    detected(qtbot, main_window, failed)
    for name in ("03_bands", "02_scf"):
        assert tagged(main_window, failed / name), name
    for name in ("04_pdos", "01_relax"):
        assert not tagged(main_window, failed / name), name


def test_the_tag_goes_after_the_file_is_deleted_and_the_folder_refreshed(
    qtbot, failed, main_window
):
    window = main_window
    detected(qtbot, window, failed)
    bands = failed / "03_bands"
    assert window.service.peek_error(bands) is not None
    (bands / "CRASH").unlink()
    window.refresh_folder(bands)  # what a pull or F5 does
    qtbot.waitUntil(lambda: window.service.peek_results(bands) is not None, timeout=5000)
    assert window.service.peek_error(bands) is None
    assert not tagged(window, bands)


def test_a_job_log_pulled_into_a_folder_turns_the_tag_on(qtbot, failed, main_window):
    window = main_window
    detected(qtbot, window, failed)
    pdos = failed / "04_pdos"
    assert window.service.peek_error(pdos) is None
    (pdos / "job.o2").write_text("Segmentation fault")  # the cluster's log, now downloaded
    window.refresh_folder(pdos)
    qtbot.waitUntil(lambda: window.service.peek_error(pdos) is not None, timeout=5000)
    assert tip(window, pdos) == f"{PREFIX}: job.o2 não está vazio"
    qtbot.waitUntil(lambda: tagged(window, pdos), timeout=5000)


def test_the_whole_refresh_reads_the_folders_again(qtbot, failed, main_window):
    window = main_window
    detected(qtbot, window, failed)
    (failed / "01_relax" / "CRASH").write_text("")
    assert window.service.peek_error(failed / "01_relax") is None  # not before F5
    window.refresh()
    qtbot.waitUntil(
        lambda: window.service.peek_error(failed / "01_relax") is not None, timeout=5000
    )


def test_the_tag_comes_with_a_folder_that_has_no_calculation(qtbot, failed, main_window):
    """A job that died before writing any output: no BANDS badge, but ERRO."""
    window = main_window
    empty = failed / "05_caiu"
    empty.mkdir()
    (empty / "job.o9").write_text("Segmentation fault")
    window.refresh()
    qtbot.waitUntil(lambda: empty.name in tree_names(window), timeout=5000)
    window.service.detect_now(empty)
    assert window.service.peek_results(empty) == []
    qtbot.wait(50)
    assert tip(window, empty) == f"{PREFIX}: job.o9 não está vazio"
    assert tagged(window, empty)
