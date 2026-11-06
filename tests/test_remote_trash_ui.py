""" "Apagar…" in the cluster mode (spec 84 R2): the item, the reasons it is disabled, the confirmation and
the answers. ``list_remote``, ``fetch_jobs`` and the ssh run are fakes and ``ask_trash`` is patched where
``ui/cluster/remote_trash.py`` imports it: no network. The real dialog runs through ``drive_modal``."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu

from qe_studio.core.config import parse_config
from qe_studio.core.remote import actions
from qe_studio.core.remote import submit as submit_core
from qe_studio.core.remote import trash as trash_core
from qe_studio.core.remote.trash import IN_TRASH, TrashBlocked, TrashDone, TrashPlan, trash_steps
from qe_studio.core.sync.command import remote_command
from qe_studio.ui.cluster import jobs_controller, remote_trash
from qe_studio.ui.cluster.job_actions import WAIT
from qe_studio.ui.cluster.remote_trash import DELETE, NO_QUEUE
from qe_studio.ui.dialogs.cluster_action import TRASH_NOTE, TrashDialog, ask_trash
from qe_studio.ui.widgets.cluster.remote_model import RemotePath
from test_atoms_dialog import drive_modal

from action_helpers import FakeCommand, toasts
from jobs_helpers import EMPTY, FakeFetch, snapshot, with_mine
from remote_helpers import (
    ACCOUNT,
    REMOTE,
    FakeListing,
    FakeOutputs,
    entries,
    menu_spy,
    remote_window,
    turn_on,
)

BANDS = f"{REMOTE}/03_bands"
FOLDER = RemotePath(BANDS, True)
SCRIPT = RemotePath(f"{BANDS}/bands.qsub", False)
FILE = RemotePath(f"{BANDS}/bands.in", False)
NOW = datetime(2026, 10, 30, 14, 2, 11)


class Asked:
    """``ask_trash``: the plans it was shown; answers ``answer`` after running ``before``."""

    def __init__(self, answer=True):
        self.answer, self.shown, self.before = answer, [], None

    def __call__(self, _parent, plan, account):
        self.shown.append(SimpleNamespace(plan=plan, account=account))
        if self.before is not None:
            self.before()
        return self.answer


@pytest.fixture
def cluster(monkeypatch):
    """The fakes: ``folders`` and ``jobs`` (what the move reads), ``queue`` (the top bar's), ``run``
    and ``asked``."""
    folders = FakeListing(
        {
            REMOTE: entries("03_bands", "trash"),
            BANDS: entries(files=("bands.qsub", "bands.in")),
        }
    )
    jobs, queue = FakeFetch(snapshot(EMPTY)), FakeFetch(snapshot(EMPTY))
    run, asked = FakeCommand(), Asked()
    monkeypatch.setattr(trash_core, "list_remote", folders)
    monkeypatch.setattr(trash_core, "list_outputs", FakeOutputs(folders))
    monkeypatch.setattr(trash_core, "fetch_jobs", jobs)
    monkeypatch.setattr(actions, "run_command", run)
    monkeypatch.setattr(remote_trash, "ask_trash", asked)
    monkeypatch.setattr(jobs_controller, "fetch_jobs", queue)
    return SimpleNamespace(folders=folders, jobs=jobs, queue=queue, run=run, asked=asked)


@pytest.fixture
def window(qtbot, window_factory, demo_project, monkeypatch, cluster):
    browse = FakeListing(
        {REMOTE: entries("03_bands", "trash"), BANDS: entries(files=("bands.qsub", "bands.in"))}
    )
    window = remote_window(window_factory, demo_project, monkeypatch, browse)
    window.browse = browse
    qtbot.waitUntil(lambda: window.jobs.result is not None, timeout=5000)
    return window


def items_of(window, monkeypatch, items):
    menus = menu_spy(monkeypatch)
    window.remote.show_menu(items, QPoint())
    return {text: (enabled, tip) for text, enabled, tip in menus[0]}


def delete(qtbot, window, monkeypatch, items):
    """Click "Apagar…" on ``items`` and wait for the end of the action; its answer."""
    menu_spy(monkeypatch, choose=DELETE)
    with qtbot.waitSignal(window.remote_trash.done, timeout=5000) as blocker:
        window.remote.show_menu(items, QPoint())
    return blocker.args[0]


# -- the menu (R2.1) -------------------------------------------------------------------------------
def test_the_item_comes_after_the_job_items(window, monkeypatch):
    shown = []

    def exec_(menu, *_args):
        shown.append(["-" if a.isSeparator() else a.text() for a in menu.actions()])

    monkeypatch.setattr(QMenu, "exec", exec_)
    for items in ([SCRIPT], [FILE], [FILE, SCRIPT]):
        window.remote.show_menu(items, QPoint())
    assert shown == [
        ["Baixar", "-", "Submeter…", "Cancelar simulação…", DELETE, "-", "Copiar caminho"],
        ["Baixar", "-", DELETE, "-", "Copiar caminho"],
        ["Baixar", "-", DELETE, "-", "Copiar caminho"],
    ]
    assert items_of(window, monkeypatch, [FILE, SCRIPT])[DELETE][0]  # enabled


def test_the_local_menu_has_no_such_item(window, demo_project, monkeypatch):
    menus = menu_spy(monkeypatch)
    window.item_actions.show([demo_project / "03_bands"], QPoint(), can_rename=True)
    assert menus and DELETE not in [text for text, _enabled, _tip in menus[0]]


def test_the_trash_and_what_is_in_it_are_disabled(window, monkeypatch):
    for path in (f"{REMOTE}/trash", f"{REMOTE}/trash/03_bands/old_2026-10-30_14-02-11"):
        assert items_of(window, monkeypatch, [RemotePath(path, True)])[DELETE] == (False, IN_TRASH)
    enabled, tip = items_of(window, monkeypatch, [RemotePath(f"{BANDS}/a b.in", False)])[DELETE]
    assert not enabled and "Nome não suportado" in tip


def test_without_the_jobs_command_it_is_disabled(window_factory, demo_project, monkeypatch):
    window = remote_window(
        window_factory, demo_project, monkeypatch, FakeListing(), jobs_command=""
    )
    assert items_of(window, monkeypatch, [FILE])[DELETE] == (False, NO_QUEUE)


def test_a_submission_in_progress_disables_it(qtbot, window, monkeypatch, cluster):
    held = FakeListing()  # the submission's folder check: "not found" once released
    monkeypatch.setattr(submit_core, "list_remote", held)
    held.hold()
    try:
        menu_spy(monkeypatch, choose="Submeter…")
        window.remote.show_menu([SCRIPT], QPoint())
        qtbot.waitUntil(lambda: held.calls != [])
        assert items_of(window, monkeypatch, [FILE])[DELETE] == (False, WAIT)
    finally:
        with qtbot.waitSignal(window.job_actions.done, timeout=5000):
            held.release()
    assert items_of(window, monkeypatch, [FILE])[DELETE][0]  # enabled again
    assert cluster.asked.shown == [] and cluster.run.argvs == []


# -- the check, the confirmation and the answer (R2.2–R2.3) ----------------------------------------
def test_no_sync_starts_while_items_are_checked_or_moved(
    qtbot, window, demo_project, monkeypatch, cluster
):
    """rsync would find the folder gone halfway: a partial mirror. Pull and push alike, from the moment
    "Apagar…" is clicked to the end of the move."""
    runs, said = [], []
    window.sync.run = lambda folder, endpoint, password=None, only=None: runs.append(folder)
    window.sync.run_push = lambda folder, endpoint, password=None: runs.append(folder)
    window.sync.message.connect(lambda text, _level, _ms: said.append(text))
    folder = demo_project / "03_bands" / "sub"  # below a project: one a push takes
    folder.mkdir()

    def refused() -> None:
        before = len(said)
        window.sync.start(folder)
        window.sync.push(folder)
        assert runs == [] and said[before:] == [WAIT, WAIT]

    def during_the_dialog() -> None:
        cluster.folders.hold()  # the move's first look at the folder waits

    cluster.asked.before = during_the_dialog
    cluster.folders.hold()
    try:
        menu_spy(monkeypatch, choose=DELETE)
        window.remote.show_menu([FOLDER], QPoint())
        qtbot.waitUntil(lambda: cluster.folders.calls != [])  # the check
        refused()
        cluster.folders.release()
        qtbot.waitUntil(lambda: cluster.asked.shown != [], timeout=5000)
        qtbot.waitUntil(lambda: window.job_actions.busy_now, timeout=5000)  # the move
        refused()
    finally:
        with qtbot.waitSignal(window.remote_trash.done, timeout=5000):
            cluster.folders.release()
    window.sync.start(folder)
    assert runs == [folder]  # over: it starts again


def test_declining_runs_nothing(qtbot, window, monkeypatch, cluster):
    cluster.asked.answer = False
    assert delete(qtbot, window, monkeypatch, [FILE, SCRIPT]) is None
    (shown,) = cluster.asked.shown
    assert shown.account == ACCOUNT and shown.plan.remote_dir == BANDS
    assert [item for item, _target in shown.plan.moves] == [
        "03_bands/bands.in",
        "03_bands/bands.qsub",
    ]
    assert all(target.startswith("trash/03_bands/bands_") for _item, target in shown.plan.moves)
    assert cluster.run.argvs == []


def test_confirming_runs_the_line_of_the_plan_and_lists_the_folder_again(
    qtbot, window, monkeypatch, cluster
):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed):
        window.remote.open(BANDS)
    listed = window.browse.calls.count(BANDS)
    result = delete(qtbot, window, monkeypatch, [FILE])
    (shown,) = cluster.asked.shown
    assert result == TrashDone(shown.plan.moves)
    assert cluster.run.argvs == [remote_command(window.config, shown.plan.line)]
    assert len(cluster.jobs.calls) == 2  # the queue asked again right before the mv
    assert ("1 item movido para trash", "info") in toasts(window)
    qtbot.waitUntil(lambda: window.browse.calls.count(BANDS) > listed)
    assert window.remote.current == BANDS


def test_the_folder_shown_deleted_from_the_tree_opens_the_one_above(
    qtbot, window, monkeypatch, cluster
):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed):
        window.remote.open(BANDS)
    result = delete(qtbot, window, monkeypatch, [FOLDER])
    assert isinstance(result, TrashDone)
    assert window.remote.current == REMOTE


def test_a_running_job_is_a_toast_and_no_dialog(qtbot, window, monkeypatch, cluster):
    cluster.folders.folders[BANDS] = entries(files=("bands.qsub", "bands.in", "Bands-kao-b.o24000"))
    cluster.jobs.result = snapshot(with_mine("Bands-kao-b"))
    result = delete(qtbot, window, monkeypatch, [FILE])
    assert result == TrashBlocked(
        "Há um job seu em execução em 03_bands (24000): cancele-o antes de apagar."
    )
    assert (result.message, "warning") in toasts(window)
    assert cluster.asked.shown == [] and cluster.run.argvs == []


def test_nothing_runs_once_the_window_is_closing(qtbot, window, monkeypatch, cluster):
    cluster.asked.before = window.job_actions.cancel  # the shutdown step, dialog still open
    menu_spy(monkeypatch, choose=DELETE)
    window.remote.show_menu([FILE], QPoint())
    qtbot.waitUntil(lambda: cluster.asked.shown != [], timeout=5000)
    qtbot.wait(200)
    assert not window.job_actions.busy_now and cluster.run.argvs == []


# -- the dialog (R2.2) -----------------------------------------------------------------------------
def plan() -> TrashPlan:
    config = parse_config(
        {"paths": {"remote_root": REMOTE}, "cluster": {"host": "hpc.example", "user": "usuario"}}
    )
    items = ((FOLDER.path, True),)
    moves = trash_core.trash_moves(REMOTE, items, NOW)
    return TrashPlan(REMOTE, items, moves, trash_steps(config, items, NOW))


def test_the_dialog_shows_each_target_and_the_commands(qtbot):
    dialog = TrashDialog(plan(), ACCOUNT)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Apagar no cluster"
    assert dialog.moves.toPlainText() == "03_bands → trash/03_bands_2026-10-30_14-02-11"
    assert dialog.note.text() == TRASH_NOTE
    assert dialog.commands.toPlainText() == "\n".join(plan().steps)
    assert dialog.commands.isReadOnly()
    assert dialog.cancel_button.isDefault() and not dialog.move_button.autoDefault()


def test_cancel_and_enter_decline_only_the_button_confirms(qtbot):
    drive_modal(lambda dialog: dialog.cancel_button.click())
    assert ask_trash(None, plan(), ACCOUNT) is False  # type: ignore[arg-type]
    drive_modal(lambda dialog: QTest.keyClick(dialog, Qt.Key.Key_Return))
    assert ask_trash(None, plan(), ACCOUNT) is False  # type: ignore[arg-type]
    drive_modal(lambda dialog: dialog.move_button.click())
    assert ask_trash(None, plan(), ACCOUNT) is True  # type: ignore[arg-type]
