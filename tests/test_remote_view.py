"""The cluster's files as cards or rows, in the order the user picks (spec 67): the local panel's
"Grade", "Lista" and "Ordenar", and one choice for both panels."""

from pathlib import PurePosixPath

import pytest
from PyQt6.QtCore import QItemSelectionModel, QModelIndex
from PyQt6.QtWidgets import QListView, QStyleOptionViewItem

from qe_studio.core.file_kinds import human_size
from qe_studio.core.remote.listing import RemoteEntry
from qe_studio.core.sync.preview import format_mtime
from qe_studio.ui.widgets.common import selection_of
from qe_studio.ui.widgets.file_card import CARD_MARGIN, card_size
from qe_studio.ui.widgets.fs_model import SORT_DATE, SORT_NAME, SORT_SIZE
from qe_studio.ui.widgets.remote_card import remote_meta

from remote_helpers import REMOTE, T0, FakeListing, remote_window, turn_on

SUB = f"{REMOTE}/run2"
FOLDER_A, FOLDER_B = RemoteEntry("run2", True, 4096, T0), RemoteEntry("run10", True, 4096, T0 + 500)
SMALL = RemoteEntry("a.out", False, 50, T0 + 300)
BIG = RemoteEntry("big.dat", False, 5_000_000, T0 + 100)
MID = RemoteEntry("mid.dat", False, 2_000, T0 + 900)
LISTING = [FOLDER_A, FOLDER_B, SMALL, BIG, MID]

ICON, LIST = QListView.ViewMode.IconMode, QListView.ViewMode.ListMode


@pytest.fixture
def fake():
    return FakeListing({REMOTE: LISTING, SUB: [SMALL, BIG]})


@pytest.fixture
def window(window_factory, demo_project, monkeypatch, fake):
    return remote_window(window_factory, demo_project, monkeypatch, fake)


def shown(window) -> list[str]:
    model = window.remote.file_panel.model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def index_of(panel, name: str) -> QModelIndex:
    return panel.model.index(panel.model.row_of(name), 0)


def selected_names(panel) -> list[str]:
    return [PurePosixPath(item.path).name for item in panel.selected_paths()]


# -- the buttons -----------------------------------------------------------------------------------
def test_the_header_has_the_view_buttons_and_the_cluster_opens_as_a_grid(qtbot, window):
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    controls = panel.controls
    assert controls.grid_button.toolTip() == "Grade"
    assert controls.list_button.toolTip() == "Lista"
    assert controls.sort_button.toolTip() == "Ordenar"
    assert [action.text() for action in controls.sort_actions.values()] == [
        "Nome",
        "Tamanho",
        "Data",
    ]
    assert controls.grid_button.isChecked() and not controls.list_button.isChecked()
    assert panel.view.viewMode() == ICON


def test_list_and_grid_switch_how_the_entries_are_shown(qtbot, window):
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    controls, names = panel.controls, shown(window)
    controls.list_button.click()
    assert not panel.grid_mode and panel.view.viewMode() == LIST
    assert controls.list_button.isChecked() and not controls.grid_button.isChecked()
    controls.list_button.click()  # the checked one stays checked
    assert controls.list_button.isChecked() and panel.view.viewMode() == LIST
    controls.grid_button.click()
    assert panel.grid_mode and panel.view.viewMode() == ICON
    assert shown(window) == names


# -- one choice for the local files and the cluster's -------------------------------------------
def test_the_choice_is_the_local_files_too_in_both_directions(qtbot, window):
    turn_on(qtbot, window)
    remote, local = window.remote.file_panel, window.files
    remote.controls.list_button.click()
    assert not local.grid_mode and local.list_button.isChecked()
    assert local.view.viewMode() == LIST
    local.grid_button.click()
    assert remote.grid_mode and remote.controls.grid_button.isChecked()
    assert remote.view.viewMode() == ICON

    remote.controls.sort_actions[SORT_SIZE].trigger()
    assert local.sort_column == SORT_SIZE and local._sort_actions[SORT_SIZE].isChecked()
    local.set_sort(SORT_DATE)
    assert remote.sort_column == SORT_DATE and remote.controls.sort_actions[SORT_DATE].isChecked()
    assert local.proxy.sort_column == SORT_DATE  # the local files are sorted too


def test_the_cluster_opens_as_the_local_files_are(qtbot, window):
    window.files.set_grid_mode(False)
    window.files.set_sort(SORT_SIZE)
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    assert not panel.grid_mode and panel.view.viewMode() == LIST
    assert panel.controls.sort_actions[SORT_SIZE].isChecked()
    assert shown(window) == ["run2", "run10", "big.dat", "mid.dat", "a.out"]


# -- the order ---------------------------------------------------------------------------------------
def test_sorting_keeps_the_folders_first_and_the_selection(qtbot, window):
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    selection = selection_of(panel.view)
    for name in ("a.out", "big.dat"):
        selection.select(
            index_of(panel, name),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
    assert shown(window) == ["run2", "run10", "a.out", "big.dat", "mid.dat"]
    panel.controls.set_sort(SORT_SIZE)
    assert shown(window) == ["run2", "run10", "big.dat", "mid.dat", "a.out"]
    assert selected_names(panel) == ["big.dat", "a.out"]
    panel.controls.set_sort(SORT_DATE)
    assert shown(window) == ["run10", "run2", "mid.dat", "a.out", "big.dat"]  # the newest first
    assert selected_names(panel) == ["a.out", "big.dat"]
    panel.controls.set_sort(SORT_NAME)
    assert shown(window) == ["run2", "run10", "a.out", "big.dat", "mid.dat"]
    assert panel.header.count.text() == "(5)"


def test_the_folder_above_is_first_in_any_order(qtbot, window):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.remote.open(SUB)
    panel = window.remote.file_panel
    for column in (SORT_SIZE, SORT_DATE, SORT_NAME):
        panel.controls.set_sort(column)
        assert shown(window)[0] == ".."
    assert panel.header.count.text() == "(2)"  # ".." is not counted


def test_sorting_while_the_folder_loads_leaves_the_spinner(qtbot, window, fake):
    fake.hold()
    window.activity.remote.click()
    panel = window.remote.file_panel
    panel.controls.set_sort(SORT_SIZE)
    assert panel.loading and shown(window) == []
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        fake.release()
    assert not panel.loading
    assert shown(window) == ["run2", "run10", "big.dat", "mid.dat", "a.out"]


# -- what a card and a row say -----------------------------------------------------------------
def test_the_line_under_a_name_is_the_kind_or_the_size_and_a_row_ends_with_the_date():
    assert remote_meta(FOLDER_A, grid=True) == "pasta"
    assert remote_meta(BIG, grid=True) == human_size(BIG.size)
    assert remote_meta(FOLDER_A, grid=False) == format_mtime(FOLDER_A.mtime)
    assert remote_meta(BIG, grid=False) == f"{human_size(BIG.size)} · {format_mtime(BIG.mtime)}"


def test_cards_and_rows_describe_each_entry(qtbot, window):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.remote.open(SUB)
    panel = window.remote.file_panel
    delegate = panel.view.itemDelegate()
    up = delegate.describe(panel.model.index(0, 0))
    assert (up.title, up.meta, up.meta_token, up.is_dir) == ("..", "pasta acima", "text_meta", True)
    card = delegate.describe(index_of(panel, "big.dat"))
    assert (card.title, card.meta, card.is_dir) == ("big.dat", human_size(BIG.size), False)
    assert card.meta_token == "text_meta"
    panel.controls.set_grid_mode(False)
    assert delegate.describe(index_of(panel, "big.dat")).meta == remote_meta(BIG, grid=False)


def test_a_long_name_makes_the_cards_taller(qtbot, window, fake):
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    assert panel.name_lines == 1 and panel.view.gridSize() == card_size()
    fake.folders[REMOTE] = [*LISTING, RemoteEntry("x" * 60, False, 1, T0)]
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.refresh()
    assert panel.name_lines > 1
    assert panel.view.gridSize() == card_size(panel.name_lines)
    size = panel.view.itemDelegate().sizeHint(QStyleOptionViewItem(), index_of(panel, "a.out"))
    assert size.height() == panel.view.gridSize().height() - CARD_MARGIN
