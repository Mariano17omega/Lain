"""Spec 37 R1: a long file name wraps over the card instead of eliding.

The numbers come from the font metrics (``per_line``), never from constants: the offscreen
platform may not have the vendored mono font, and the tests must hold at any width.
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PyQt6.QtCore import QPoint, QSize
from PyQt6.QtWidgets import QStyleOptionViewItem

from grid_helpers import index_of, show_folder
from qe_studio.core.filtering import CategoryFilter
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.file_card import (
    CARD_MARGIN,
    MAX_NAME_LINES,
    card_size,
    name_height,
    name_lines,
    name_metrics,
    name_width,
    row_height,
    wrap_name,
)


@pytest.fixture
def scale_one(qapp):
    """The card at scale 1, whatever an earlier test left (the scale is global)."""
    manager = ThemeManager("dark")
    yield manager
    manager.set_font_scale(1.0)


def per_line() -> int:
    """How many "x" fit one line of a card's name (measured: the advance of one is rounded)."""
    metrics, width = name_metrics(), name_width()
    count = 1
    while metrics.horizontalAdvance("x" * (count + 1)) <= width:
        count += 1
    return count


def name_of(lines: int) -> str:
    """A name of no separators that needs exactly ``lines`` lines (the last one half full)."""
    return "x" * ((lines - 1) * per_line() + per_line() // 2)


@pytest.fixture
def folders(demo_project):
    """Folders of files named by how many lines they need (made before the window opens)."""
    made = {}
    for label, names in {
        "curtos": ["a.in", "b.out", "scf.out"],
        "quatro": ["a.in", name_of(4)],
        "enorme": ["a.in", "x" * 200],
    }.items():
        folder = demo_project / f"nomes_{label}"
        folder.mkdir()
        for name in names:
            (folder / name).write_text("")
        made[label] = folder
    return made


def settled(qtbot, window, lines: int) -> None:
    files = window.files
    qtbot.waitUntil(
        lambda: files.name_lines == lines and files.view.gridSize() == card_size(lines),
        timeout=5000,
    )


# -- the pure part ----------------------------------------------------------------------------
def test_short_names_are_one_line(scale_one):
    metrics = name_metrics()
    assert wrap_name("scf.out", name_width(), metrics) == ["scf.out"]
    assert name_lines(["a", "scf.out", "bands.in"], name_width(), metrics) == 1
    assert name_lines([], name_width(), metrics) == 1


def test_a_line_breaks_after_a_separator_when_it_can(scale_one):
    metrics = name_metrics()
    name = "ilita-" + "x" * (per_line() - 8) + "-" + "y" * per_line()
    lines = wrap_name(name, name_width(), metrics)
    assert lines[0].endswith("-") and len(lines[0]) <= per_line()
    assert "".join(lines) == name
    assert all(metrics.horizontalAdvance(line) <= name_width() for line in lines)


@pytest.mark.parametrize("separator", ["-", " ", ".", "_"])
def test_each_separator_is_a_place_to_break(scale_one, separator):
    first = per_line() - 3
    name = "x" * first + separator + "y" * (per_line() - 2)
    lines = wrap_name(name, name_width(), name_metrics())
    assert lines == ["x" * first + separator, "y" * (per_line() - 2)]


def test_a_word_wider_than_the_line_breaks_anywhere(scale_one):
    lines = wrap_name("x" * (3 * per_line()), name_width(), name_metrics())
    assert [len(line) for line in lines] == [per_line()] * 3


def test_a_separator_too_early_does_not_waste_the_line(scale_one):
    name = "x-" + "y" * (2 * per_line())  # the "-" would leave a two character line
    lines = wrap_name(name, name_width(), name_metrics())
    assert lines[0] != "x-" and len(lines[0]) >= per_line() - 2


def test_only_past_the_limit_the_last_line_is_elided(scale_one):
    metrics = name_metrics()
    exact = "x" * (MAX_NAME_LINES * per_line())
    assert "…" not in "".join(wrap_name(exact, name_width(), metrics))
    over = exact + "x"
    lines = wrap_name(over, name_width(), metrics)
    assert len(lines) == MAX_NAME_LINES and lines[-1].endswith("…")
    assert all(metrics.horizontalAdvance(line) <= name_width() for line in lines)
    assert name_lines([over, "x" * 200], name_width(), metrics) == MAX_NAME_LINES


def test_the_card_grows_one_name_line_at_a_time(scale_one):
    assert card_size(1) == card_size()
    for lines in range(2, MAX_NAME_LINES + 1):
        assert card_size(lines).height() - card_size(lines - 1).height() == name_height()
    assert card_size(MAX_NAME_LINES + 3) == card_size(MAX_NAME_LINES)  # never taller than that
    assert card_size(0) == card_size()


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(st.text(alphabet="ab-_. ", min_size=0, max_size=300), st.integers(1, MAX_NAME_LINES))
def test_wrapped_lines_always_fit_and_lose_nothing_but_the_end(scale_one, text, max_lines):
    metrics = name_metrics()
    lines = wrap_name(text, name_width(), metrics, max_lines)
    assert 1 <= len(lines) <= max_lines
    assert all(metrics.horizontalAdvance(line) <= name_width() for line in lines)
    joined = "".join(lines)
    if joined != text:  # cut: only the last line was elided, the rest is the text's start
        assert lines[-1].endswith("…")
        assert text.startswith("".join(lines[:-1]))


# -- in the window ----------------------------------------------------------------------------
def test_a_folder_of_short_names_keeps_the_card_it_had(qtbot, folders, main_window):
    window = main_window
    show_folder(qtbot, window, folders["curtos"])
    settled(qtbot, window, 1)
    assert window.files.view.gridSize() == card_size()
    option, index = QStyleOptionViewItem(), index_of(window.files, "scf.out")
    delegate = window.files.view.itemDelegate()
    assert delegate.sizeHint(option, index) == card_size() - QSize(CARD_MARGIN, CARD_MARGIN)


def test_a_long_name_wraps_in_whole_and_the_card_grows(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["quatro"])
    settled(qtbot, window, 4)
    name = name_of(4)
    lines = wrap_name(name, name_width(), name_metrics(), files.name_lines)
    assert len(lines) == 4 and "".join(lines) == name  # all of it, no "…"
    delegate = files.view.itemDelegate()
    index = index_of(files, name)
    assert delegate.sizeHint(QStyleOptionViewItem(), index).height() == (
        files.view.gridSize().height() - CARD_MARGIN  # the same card, less its margin
    )
    assert delegate._tooltip_at(QPoint(5, 5), files.view.visualRect(index), index) == ""


def test_past_six_lines_the_name_is_cut_and_the_tooltip_has_all_of_it(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["enorme"])
    settled(qtbot, window, MAX_NAME_LINES)
    name = "x" * 200
    lines = wrap_name(name, name_width(), name_metrics(), files.name_lines)
    assert len(lines) == MAX_NAME_LINES and lines[-1].endswith("…")
    index = index_of(files, name)
    tip = files.view.itemDelegate()._tooltip_at(QPoint(5, 5), files.view.visualRect(index), index)
    assert tip == name
    short = index_of(files, "a.in")  # a name that fits has nothing to add
    rect = files.view.visualRect(short)
    assert files.view.itemDelegate()._tooltip_at(QPoint(5, 5), rect, short) == ""


def test_the_card_goes_back_when_the_long_name_is_in_another_folder(qtbot, folders, main_window):
    window = main_window
    show_folder(qtbot, window, folders["quatro"])
    settled(qtbot, window, 4)
    show_folder(qtbot, window, folders["curtos"])
    settled(qtbot, window, 1)
    show_folder(qtbot, window, folders["enorme"])
    settled(qtbot, window, MAX_NAME_LINES)


def test_a_filter_follows_what_is_listed(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["quatro"])
    settled(qtbot, window, 4)
    bar = files.filter_bar
    bar.open()
    bar.field.setText("a.in")
    bar.flush()
    settled(qtbot, window, 1)  # the long name is filtered out
    bar.field.setText("")
    bar.flush()
    settled(qtbot, window, 4)
    assert files.proxy.category == CategoryFilter()


def test_files_that_arrive_later_make_the_card_taller(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["curtos"])
    settled(qtbot, window, 1)
    (folders["curtos"] / name_of(3)).write_text("")  # the model reads and watches in its thread
    settled(qtbot, window, 3)
    assert files.view.gridSize().height() == card_size(3).height()


def test_the_scale_measures_again(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["quatro"])
    settled(qtbot, window, 4)
    before = files.view.gridSize()
    try:
        window.theme.set_font_scale(1.6)
        expected = name_lines([name_of(4)], name_width(), name_metrics())
        assert files.name_lines == expected
        assert files.view.gridSize() == card_size(expected)
        assert files.view.gridSize().height() > before.height()
    finally:
        window.theme.set_font_scale(1.0)
    settled(qtbot, window, 4)


def test_list_mode_is_as_it_was(qtbot, folders, main_window):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, folders["enorme"])
    settled(qtbot, window, MAX_NAME_LINES)
    files.set_grid_mode(False)
    assert files.view.gridSize().isEmpty()
    index = index_of(files, "x" * 200)
    delegate = files.view.itemDelegate()
    assert delegate.sizeHint(QStyleOptionViewItem(), index).height() == row_height()
    rect = files.view.visualRect(index)  # the row elides: the tooltip has the whole name
    assert delegate._tooltip_at(QPoint(40, 5), rect, index) == "x" * 200
    files.set_grid_mode(True)
    settled(qtbot, window, MAX_NAME_LINES)
