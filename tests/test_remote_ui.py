"""The cluster mode in the window (spec 65 R3–R5): the button and the panels it swaps, the waiting,
the cache, the failures, F5 and the menu. ``list_remote`` is a fake (``remote_helpers``)."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from qe_studio.core.remote.listing import RemoteFailure
from qe_studio.core.sync.monitor import ConnectionState
from qe_studio.core.sync.request import SYNC_OFF, SYNC_RUNNING
from qe_studio.ui.remote_controller import CONFIG_CHANGED, LISTING, ONE_ITEM
from qe_studio.ui.widgets.remote_model import RemotePath

from remote_helpers import ACCOUNT, REMOTE, FakeListing, entries, menu_spy, remote_window, turn_on

BANDS = f"{REMOTE}/03_bands"
TOP = entries("01_relax", "02_scf", "03_bands", files=("notes.txt",))


@pytest.fixture
def fake():
    return FakeListing(
        {
            REMOTE: TOP,
            BANDS: entries("orbitals", files=("bands.out", "scf.out")),
            f"{REMOTE}/01_relax": entries(files=("relax.out",)),
            f"{REMOTE}/02_scf": entries(files=("scf.out",)),
        }
    )


@pytest.fixture
def window(window_factory, demo_project, monkeypatch, fake):
    return remote_window(window_factory, demo_project, monkeypatch, fake)


def grid_names(window) -> list[str]:
    model = window.remote.file_panel.model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def tree_names(window) -> list[str]:
    model = window.remote.tree_panel.model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


# -- R3: the button and the panels ----------------------------------------------------------------
def test_the_button_swaps_both_panels_and_back(qtbot, window, demo_project, fake):
    local = demo_project / "03_bands"
    window.explorer.select_path(local)
    window.files.select_file(local / "bands.out")
    explorer, local_page = window.left.currentWidget(), window.files.pages.currentWidget()
    assert window.activity.remote.isEnabled() and window.activity.remote.text() == "Cluster"

    turn_on(qtbot, window, BANDS)  # the cluster side of the local folder
    remote = window.remote
    assert remote.active and window.activity.remote.isChecked()
    assert window.left.currentWidget() is remote.tree_panel
    assert window.files.pages.currentWidget() is remote.file_panel
    assert grid_names(window) == ["..", "orbitals", "bands.out", "scf.out"]
    assert not window.top_bar.breadcrumb.isEnabled()
    assert not window.top_bar.back_button.isEnabled()
    assert window.status.path.full_text() == f"{ACCOUNT}:{BANDS}"
    qtbot.waitUntil(lambda: tree_names(window) == ["01_relax", "02_scf", "03_bands"])
    assert remote.tree_panel.current_dir() == BANDS  # the tree follows the grid

    window.activity.remote.click()
    assert not remote.active and not window.activity.remote.isChecked()
    assert window.left.currentWidget() is explorer
    assert window.files.pages.currentWidget() is local_page
    assert window.files.folder == local  # the local panels as they were
    assert [p.name for p in window.files.selected_paths()] == ["bands.out"]
    assert window.top_bar.breadcrumb.isEnabled()
    assert window.status.path.full_text() == "03_bands"


def test_the_menu_action_toggles_too(qtbot, window):
    action = window._actions["remote.toggle"]
    assert action.text() == "Ver arquivos do cluster"
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        action.trigger()
    assert window.remote.active
    action.trigger()
    assert not window.remote.active


def test_the_tree_button_toggles_the_cluster_tree(qtbot, window):
    turn_on(qtbot, window)
    tree = window.remote.tree_panel
    window.activity.tree.click()
    assert window.left.isHidden()
    window.activity.tree.click()
    assert not window.left.isHidden() and window.left.currentWidget() is tree
    assert window.activity.tree.isChecked()
    window.set_left_mode("params")
    window.activity.tree.click()  # the tree page: the cluster's while the mode is on
    assert window.left.currentWidget() is tree


def test_no_cluster_no_mode(main_window):
    button = main_window.activity.remote
    assert not button.isEnabled() and button.toolTip() == SYNC_OFF
    main_window.remote.toggle()
    assert not main_window.remote.active
    assert main_window.status.message.text() == SYNC_OFF


def test_reloading_the_config_turns_the_mode_off(qtbot, window, demo_project, tmp_path):
    turn_on(qtbot, window)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"paths:\n  local_root: {demo_project}\n  remote_root: {REMOTE}\n"
        "cluster:\n  host: hpc.example\n  user: usuario\n  jobs_command: ''\n",
        encoding="utf-8",
    )
    window.load_config_file(config)
    assert not window.remote.active and not window.activity.remote.isChecked()
    assert window.left.currentWidget() is window.explorer
    assert window.files.pages.currentWidget() is window.files.local_page
    toast = window.toast
    shown = [toast.current, *toast._queue] if toast.current else list(toast._queue)
    assert CONFIG_CHANGED in [notice.text for notice in shown]


def test_the_start_folder_goes_up_when_the_cluster_lacks_it(qtbot, window, demo_project, fake):
    window.explorer.select_path(demo_project / "04_pdos" / "orbitals")
    window.activity.remote.click()
    qtbot.waitUntil(lambda: grid_names(window) == ["01_relax", "02_scf", "03_bands", "notes.txt"])
    assert window.remote.current == REMOTE  # the top: no ".."
    assert {f"{REMOTE}/04_pdos/orbitals", f"{REMOTE}/04_pdos"} <= set(fake.calls)
    assert not window.remote.file_panel.failed


def test_changing_project_goes_to_its_top(qtbot, window, fake):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.project.switch("03_bands")
    assert window.remote.browser.top == BANDS and window.remote.current == BANDS
    assert grid_names(window) == ["orbitals", "bands.out", "scf.out"]  # the top: no ".."


# -- R4: waiting, cache, failures ------------------------------------------------------------------
def test_the_spinner_shows_while_the_folder_is_listed(qtbot, window, fake):
    fake.hold()
    window.activity.remote.click()
    panel = window.remote.file_panel
    assert panel.loading and window.status.busy.text() == LISTING
    assert not window.status.busy.isHidden()
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        fake.release()
    qtbot.waitUntil(lambda: window.status.busy.isHidden())
    assert not panel.loading


def test_a_cached_folder_shows_at_once_and_is_listed_again_when_old(qtbot, window, fake):
    now = [1000.0]
    window.remote._clock = lambda: now[0]
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.remote.open(BANDS)
    qtbot.waitUntil(lambda: len(window.status.busy.text()) == 0 or window.status.busy.isHidden())
    calls = len(fake.calls)
    window.remote.go_up()
    assert grid_names(window)[:3] == ["01_relax", "02_scf", "03_bands"]  # at once, no listing
    assert len(fake.calls) == calls and not window.remote.file_panel.loading

    now[0] += 61
    fake.hold()
    window.remote.open(BANDS)
    assert grid_names(window) == ["..", "orbitals", "bands.out", "scf.out"]  # the cache, shown
    assert not window.remote.file_panel.loading  # listed again behind it: the footer only
    assert window.status.busy.text() == LISTING
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        fake.release()
    assert fake.calls[-1] == BANDS and len(fake.calls) == calls + 1


def test_a_new_click_replaces_the_pending_listing(qtbot, window, fake):
    turn_on(qtbot, window)
    listed = []
    window.remote.listed.connect(lambda folder, _result: listed.append(folder))
    fake.hold()
    window.remote.open(f"{REMOTE}/01_relax")
    qtbot.waitUntil(lambda: f"{REMOTE}/01_relax" in fake.calls)
    window.remote.open(f"{REMOTE}/02_scf")
    qtbot.waitUntil(lambda: f"{REMOTE}/01_relax" in fake.cancelled, timeout=3000)
    fake.release()
    qtbot.waitUntil(lambda: listed == [f"{REMOTE}/02_scf"], timeout=5000)
    assert grid_names(window) == ["..", "scf.out"]


def test_a_failure_offers_to_try_again_and_the_led_says_offline(qtbot, window, fake):
    down = RemoteFailure("Cluster inacessível (tempo de conexão esgotado).", connection=True)
    fake.folders[REMOTE] = down
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    assert panel.failed and panel.message.text() == down.message
    assert panel.retry_button.isVisible()
    assert window.monitor.state is ConnectionState.OFFLINE
    fake.folders[REMOTE] = TOP
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        panel.retry_button.click()
    assert not panel.failed and grid_names(window)[0] == "01_relax"
    assert window.monitor.state is ConnectionState.ONLINE


def test_a_refused_login_forgets_the_password(qtbot, window_factory, demo_project, monkeypatch):
    fake = FakeListing({REMOTE: RemoteFailure("Autenticação recusada", auth=True)})
    window = remote_window(window_factory, demo_project, monkeypatch, fake, auth="password")
    monkeypatch.delenv("QE_STUDIO_SSH_PASSWORD", raising=False)
    asked = []
    monkeypatch.setattr(
        window.sync, "session_password", lambda ask=True: asked.append(ask) or "senha"
    )
    forgotten = []
    monkeypatch.setattr(window.sync, "forget_password", lambda: forgotten.append(True))
    turn_on(qtbot, window)
    qtbot.wait(300)  # nothing tries again on its own, not even the tree's root
    assert fake.passwords == ["senha"] and forgotten == [True]
    assert asked[0] is True  # turning the mode on asks


def test_f5_lists_the_cluster_folder_again(qtbot, window, fake):
    turn_on(qtbot, window)
    calls = len(fake.calls)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.refresh()
    assert fake.calls[calls:].count(REMOTE) == 1


def test_the_tree_lists_a_folder_when_it_is_opened(qtbot, window, fake):
    turn_on(qtbot, window)
    tree = window.remote.tree_panel
    qtbot.waitUntil(lambda: tree_names(window) == ["01_relax", "02_scf", "03_bands"])
    index = tree.model.index_for(BANDS)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        tree.tree.expand(index)
    qtbot.waitUntil(lambda: tree.model.rowCount(tree.model.index_for(BANDS)) == 1)
    child = tree.model.index(0, 0, tree.model.index_for(BANDS))
    assert child.data() == "orbitals"
    calls = len(fake.calls)
    tree.tree.setCurrentIndex(index)  # a click on a folder of the tree: the grid shows it
    assert window.remote.current == BANDS and len(fake.calls) == calls  # listed: no new listing
    assert grid_names(window) == ["..", "orbitals", "bands.out", "scf.out"]


# -- R5: the menu ------------------------------------------------------------------------------
def test_the_menu_has_download_and_copy_only(qtbot, window, monkeypatch, demo_project):
    turn_on(qtbot, window)
    starts = []
    monkeypatch.setattr(
        window.sync, "start", lambda folder, only=None: starts.append((folder, only))
    )
    menus = menu_spy(monkeypatch, choose="Baixar")
    window.remote.show_menu([RemotePath(f"{BANDS}/bands.out", False)], QPoint())
    window.remote.show_menu([RemotePath(f"{REMOTE}/novo", True)], QPoint())
    assert [text for text, _on, _tip in menus[0]] == ["Baixar", "Copiar caminho"]
    assert starts == [
        (demo_project / "03_bands", "bands.out"),
        (demo_project / "novo", None),  # the mirror, made by the pull when missing
    ]

    two = [RemotePath(f"{BANDS}/bands.out", False), RemotePath(f"{BANDS}/scf.out", False)]
    menus = menu_spy(monkeypatch, choose="Copiar caminho")
    window.remote.show_menu(two, QPoint())
    assert menus[0][0] == ("Baixar", False, ONE_ITEM)
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == f"{BANDS}/bands.out\n{BANDS}/scf.out"


def test_download_waits_for_a_running_sync(qtbot, window, monkeypatch):
    turn_on(qtbot, window)
    monkeypatch.setattr(type(window.sync), "running", property(lambda self: True))
    menus = menu_spy(monkeypatch)
    window.remote.show_menu([RemotePath(f"{REMOTE}/02_scf", True)], QPoint())
    assert menus[0][0] == ("Baixar", False, SYNC_RUNNING)


def test_the_grid_menu_is_the_selection(qtbot, window, monkeypatch):
    turn_on(qtbot, window, REMOTE)
    window.remote.open(BANDS)
    qtbot.waitUntil(lambda: "bands.out" in grid_names(window))
    panel = window.remote.file_panel
    seen = []
    panel.menu_requested.disconnect()
    panel.menu_requested.connect(lambda items, _pos: seen.append(items))
    view = panel.view
    row = grid_names(window).index("bands.out")
    rect = view.visualRect(panel.model.index(row, 0))
    panel._on_context_menu(rect.center())
    assert seen == [[RemotePath(f"{BANDS}/bands.out", False)]]
    up = view.visualRect(panel.model.index(0, 0))
    panel._on_context_menu(up.center())  # ".." has no menu
    assert len(seen) == 1


def test_entering_a_folder_and_going_up(qtbot, window):
    turn_on(qtbot, window)
    panel = window.remote.file_panel
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        panel.folder_activated.emit(BANDS)
    assert window.remote.current == BANDS
    panel.view.activated.emit(panel.model.index(grid_names(window).index("bands.out"), 0))
    assert window.remote.current == BANDS  # a file: nothing (spec 66 plots)
    panel.up_requested.emit()
    assert window.remote.current == REMOTE


def test_revealing_a_local_item_leaves_the_mode(qtbot, window, demo_project):
    turn_on(qtbot, window)
    window.workspace.reveal_requested.emit(demo_project / "02_scf" / "scf.out")  # a tab's menu
    assert not window.remote.active and window.left.currentWidget() is window.explorer


def test_paths_are_never_resolved_by_the_mode():
    """The mapping is path arithmetic (``RemoteBrowser``): ``ui/remote_*`` makes no disk call."""
    import qe_studio.ui.remote_controller as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert ".resolve(" not in source and ".exists(" not in source
