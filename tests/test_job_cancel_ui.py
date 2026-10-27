""" "Cancelar simulação…" in the cluster mode and the cancel buttons of the queue popup (spec 70 R4–R6,
spec 71 R2, R5–R6): the item, the reasons it is disabled, the dialog and the answers. ``list_remote``,
``fetch_jobs``, ``fetch_stop_sources`` and the ssh run are fakes and ``ask_cancel`` is patched where
``ui/job_cancel.py`` imports it: no network. The real dialog runs through ``drive_modal``."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu

from qe_studio.core.remote import actions
from qe_studio.core.remote import job_cancel as job_cancel_core
from qe_studio.core.remote.inputs import StopSource
from qe_studio.core.remote.job_cancel import Done, NotRunning, Refused
from qe_studio.core.sync.command import CommandResult, remote_command
from qe_studio.ui import job_cancel, jobs_controller
from qe_studio.ui.dialogs.cluster_action import CancelDialog, ask_cancel
from qe_studio.ui.job_actions import WAIT
from qe_studio.ui.job_cancel import CANCEL, NO_DELETE, NO_QUEUE, NOTE_EXIT, NOTE_QDEL
from qe_studio.ui.widgets.remote_model import RemotePath
from test_atoms_dialog import drive_modal

from action_helpers import FakeCommand, toasts
from jobs_helpers import QSTATUS_ALL, USER, FakeFetch, snapshot, with_mine
from remote_helpers import ACCOUNT, REMOTE, FakeListing, entries, menu_spy, remote_window, turn_on

BANDS = f"{REMOTE}/03_bands"
FOLDER = RemotePath(BANDS, True)
SCRIPT = RemotePath(f"{BANDS}/bands.qsub", False)
TOUCH = f"touch {BANDS}/al.EXIT"
RUNNING = with_mine("Bands-kao-b", waiting=2, queued="Bands-kao-b")  # 24000 runs; 25000, 25001 wait


class Asked:
    """``ask_cancel``: what each dialog was shown; answers ``answer`` after running ``before``."""

    def __init__(self, answer=True):
        self.answer, self.shown, self.before = answer, [], None

    def __call__(self, _parent, rows, method, note, line):
        self.shown.append(SimpleNamespace(rows=rows, method=method, note=note, line=line))
        if self.before is not None:
            self.before()
        return self.answer


@pytest.fixture
def cluster(monkeypatch):
    """The fakes: ``folders`` and ``jobs`` (what the cancellation reads), ``prefixes``, ``queue``
    (the top bar's), ``run`` and ``asked``."""
    folders = FakeListing({BANDS: entries(files=("bands.qsub", "al.scf.in", "Bands-kao-b.o24000"))})
    jobs, queue = FakeFetch(snapshot(RUNNING)), FakeFetch(snapshot(RUNNING))
    prefixes = SimpleNamespace(result=(StopSource("al", ("al.scf.in",)),))
    run, asked = FakeCommand(), Asked()
    monkeypatch.setattr(job_cancel_core, "list_remote", folders)
    monkeypatch.setattr(job_cancel_core, "fetch_jobs", jobs)
    monkeypatch.setattr(job_cancel_core, "fetch_stop_sources", lambda *_args: prefixes.result)
    monkeypatch.setattr(actions, "run_command", run)
    monkeypatch.setattr(job_cancel, "ask_cancel", asked)
    monkeypatch.setattr(jobs_controller, "fetch_jobs", queue)
    return SimpleNamespace(
        folders=folders, jobs=jobs, queue=queue, prefixes=prefixes, run=run, asked=asked
    )


@pytest.fixture
def window(qtbot, window_factory, demo_project, monkeypatch, cluster):
    browse = FakeListing({REMOTE: entries("03_bands"), BANDS: entries(files=("bands.qsub",))})
    window = remote_window(window_factory, demo_project, monkeypatch, browse)
    window.browse = browse
    qtbot.waitUntil(lambda: window.jobs.result is not None, timeout=5000)
    return window


def items_of(window, monkeypatch, items):
    menus = menu_spy(monkeypatch)
    window.remote.show_menu(items, QPoint())
    return {text: (enabled, tip) for text, enabled, tip in menus[0]}


def cancel_item(qtbot, window, monkeypatch, item=FOLDER):
    """Click "Cancelar simulação…" on ``item`` and wait for the end of the action; its answer."""
    menu_spy(monkeypatch, choose=CANCEL)
    with qtbot.waitSignal(window.job_cancel.done, timeout=5000) as blocker:
        window.remote.show_menu([item], QPoint())
    return blocker.args[0]


# -- the menu (R4) ---------------------------------------------------------------------------------
def test_the_item_shows_on_a_folder_and_a_qsub(window, monkeypatch):
    assert items_of(window, monkeypatch, [FOLDER])[CANCEL][0]  # enabled
    assert items_of(window, monkeypatch, [SCRIPT])[CANCEL][0]
    for items in (
        [RemotePath(f"{BANDS}/al.scf.in", False)],
        [FOLDER, RemotePath(f"{REMOTE}/04_dos", True)],
    ):
        assert CANCEL not in items_of(window, monkeypatch, items), items


def test_the_item_sits_between_plotar_and_copiar_caminho(window, monkeypatch):
    shown = []

    def exec_(menu, *_args):
        shown.append(["-" if a.isSeparator() else a.text() for a in menu.actions()])

    monkeypatch.setattr(QMenu, "exec", exec_)
    window.remote.show_menu([FOLDER], QPoint())
    window.remote.show_menu([SCRIPT], QPoint())
    assert shown == [
        ["Baixar", "Plotar", "-", CANCEL, "-", "Copiar caminho"],
        ["Baixar", "-", "Submeter…", CANCEL, "-", "Copiar caminho"],
    ]


def test_without_the_jobs_command_it_is_disabled(window_factory, demo_project, monkeypatch):
    window = remote_window(
        window_factory, demo_project, monkeypatch, FakeListing(), jobs_command=""
    )
    assert items_of(window, monkeypatch, [FOLDER])[CANCEL] == (False, NO_QUEUE)


def test_a_folder_with_an_unsafe_name_is_disabled(window, monkeypatch):
    enabled, tip = items_of(window, monkeypatch, [RemotePath(f"{REMOTE}/a b", True)])[CANCEL]
    assert not enabled and "Nome não suportado" in tip


def test_one_action_at_a_time(qtbot, window, monkeypatch, cluster):
    cluster.folders.hold()
    try:
        menu_spy(monkeypatch, choose=CANCEL)
        window.remote.show_menu([FOLDER], QPoint())
        qtbot.waitUntil(lambda: cluster.folders.calls != [])
        assert items_of(window, monkeypatch, [FOLDER])[CANCEL] == (False, WAIT)
        assert "Submeter…" in items_of(window, monkeypatch, [SCRIPT])  # shared: disabled too
        assert items_of(window, monkeypatch, [SCRIPT])["Submeter…"] == (False, WAIT)
        assert "Conferindo o job no cluster…" in window.plot_workflow.busy.labels
    finally:
        with qtbot.waitSignal(window.job_cancel.done, timeout=5000):
            cluster.folders.release()


def test_no_running_job_is_a_toast_and_no_dialog(qtbot, window, monkeypatch, cluster):
    cluster.folders.folders[BANDS] = entries(files=("bands.qsub", "Bands-kao-b.o23000"))
    result = cancel_item(qtbot, window, monkeypatch)
    assert isinstance(result, NotRunning)
    assert (result.message, "info") in toasts(window)
    assert cluster.asked.shown == [] and cluster.run.argvs == []


def test_the_dialog_gets_the_job_the_folder_and_the_line(qtbot, window, monkeypatch, cluster):
    cluster.prefixes.result = (
        StopSource("al", ("al.scf.in", "relax.in")),
        StopSource("al_conv", ("ecut40.in",)),
    )
    cluster.asked.answer = False
    assert cancel_item(qtbot, window, monkeypatch, SCRIPT) is None  # declined: nothing runs
    (shown,) = cluster.asked.shown
    assert shown.rows == [
        [
            ("Job", "Bands-kao-b"),
            ("ID", "24000"),
            ("Dono", USER),
            ("Início", "10/24/2026 09:00:00"),
            ("Núcleos", "16"),
            ("Pasta", f"{ACCOUNT}:{BANDS}"),
        ]
    ]
    assert shown.method == (
        "arquivo de parada do pw.x: al.EXIT (al.scf.in, relax.in), al_conv.EXIT (ecut40.in)"
    )
    assert shown.note == NOTE_EXIT
    assert shown.line == f"touch {BANDS}/al.EXIT {BANDS}/al_conv.EXIT"
    assert cluster.run.argvs == []


def test_confirming_creates_the_stop_file(qtbot, window, monkeypatch, cluster):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed):
        window.remote.open(BANDS)
    listed, queries = window.browse.calls.count(BANDS), len(cluster.queue.calls)
    result = cancel_item(qtbot, window, monkeypatch)
    assert result == Done("Pedido de parada criado: al.EXIT. O pw.x para na próxima verificação.")
    assert cluster.run.argvs == [remote_command(window.config, TOUCH)]
    assert (result.message, "info") in toasts(window)
    assert len(cluster.jobs.calls) == 2  # the queue asked again right before the touch
    qtbot.waitUntil(lambda: window.browse.calls.count(BANDS) > listed)  # the new al.EXIT shows
    qtbot.waitUntil(lambda: len(cluster.queue.calls) > queries)


def test_a_job_that_ended_during_the_dialog_gets_nothing(qtbot, window, monkeypatch, cluster):
    def ended():
        cluster.jobs.result = snapshot(QSTATUS_ALL)

    cluster.asked.before = ended
    result = cancel_item(qtbot, window, monkeypatch)
    assert result == Refused("O job 24000 não está mais em execução: nada foi criado.")
    assert (result.message, "warning") in toasts(window)
    assert cluster.run.argvs == []  # no touch


def test_a_failure_says_why(qtbot, window, monkeypatch, cluster):
    cluster.run.result = CommandResult(1, "", "touch: cannot touch 'x': Read-only file system\n")
    cancel_item(qtbot, window, monkeypatch)
    text = "O cancelamento falhou: touch terminou com código 1: touch: cannot touch 'x': Read-only file system"
    assert (text, "error") in toasts(window)


# -- the popup (R5) --------------------------------------------------------------------------------
def open_popup(qtbot, window):
    window.jobs.indicator.click()
    popup = window.jobs.popup
    qtbot.waitUntil(popup.isVisible, timeout=2000)
    return popup


def click_cancel(qtbot, window, index):
    """Click the cancel button of the ``index``-th waiting job of the user; the answer."""
    popup = open_popup(qtbot, window)
    with qtbot.waitSignal(window.job_cancel.done, timeout=5000) as blocker:
        popup.cancel_buttons[index].click()
    return blocker.args[0]


def test_a_button_asks_for_the_job_of_its_row(qtbot, window, cluster):
    popup = open_popup(qtbot, window)
    asked = []
    popup.cancel_requested.connect(asked.append)
    second = popup.cancel_buttons[1]
    assert second.toolTip() == "Cancelar o job 25001 (qdel)" and second.isEnabled()
    cluster.asked.answer = False
    with qtbot.waitSignal(window.job_cancel.done, timeout=5000):
        second.click()
    assert [job.job_id for job in asked] == ["25001"]  # same name as 25000: by its row
    assert not popup.isVisible()  # closed before the dialog


def test_the_dialog_of_a_waiting_job(qtbot, window, cluster):
    cluster.asked.answer = False
    assert click_cancel(qtbot, window, 0) is None
    (shown,) = cluster.asked.shown
    assert ("ID", "25000") in shown.rows[0] and ("Envio", "10/24/2026 10:00:00") in shown.rows[0]
    assert ("Pasta", "não informada pelo qstatus") in shown.rows[0]
    assert shown.method == "qdel 25000 (o job sai da fila antes de começar)"
    assert shown.note == NOTE_QDEL and shown.line == "qdel 25000"
    assert cluster.run.argvs == []


def test_confirming_deletes_the_waiting_job(qtbot, window, cluster):
    queries = len(cluster.queue.calls)
    result = click_cancel(qtbot, window, 0)
    assert result == Done("Job 25000 (Bands-kao-b) cancelado com qdel.")
    assert cluster.run.argvs == [remote_command(window.config, "qdel 25000")]
    assert (result.message, "info") in toasts(window)
    qtbot.waitUntil(lambda: len(cluster.queue.calls) > queries)


def test_a_job_that_started_is_never_deleted(qtbot, window, cluster):
    started = RUNNING.replace("  25000 16 Bands-kao-b", "  25999 16 Bands-kao-b", 1)
    started = started.replace("  24000 16", "  25000 16", 1)  # 25000 runs now
    cluster.jobs.result = snapshot(started)
    result = click_cancel(qtbot, window, 0)
    assert isinstance(result, Refused) and result.message.startswith("O job 25000 começou a rodar")
    assert (result.message, "warning") in toasts(window)
    assert cluster.run.argvs == []  # no qdel


def test_a_click_during_an_action_says_so_and_asks_nothing(qtbot, window, monkeypatch, cluster):
    cluster.asked.answer = False  # the folder's own dialog, at the end
    popup = open_popup(qtbot, window)
    assert all(button.isEnabled() for button in popup.cancel_buttons)  # drawn before the action
    cluster.folders.hold()
    try:
        menu_spy(monkeypatch, choose=CANCEL)
        window.remote.show_menu([FOLDER], QPoint())
        qtbot.waitUntil(lambda: cluster.folders.calls != [])
        popup.cancel_buttons[0].click()
        assert (WAIT, "warning") in toasts(window)  # never silent (spec 71 R6)
        assert not popup.isVisible() and cluster.asked.shown == []
    finally:
        with qtbot.waitSignal(window.job_cancel.done, timeout=5000):
            cluster.folders.release()
    assert [shown.line for shown in cluster.asked.shown] == [TOUCH]  # no qdel was asked
    assert cluster.run.argvs == []


def test_the_buttons_are_enabled_again_when_the_popup_reopens(qtbot, window, cluster):
    cluster.asked.answer = False
    click_cancel(qtbot, window, 0)
    popup = open_popup(qtbot, window)
    assert popup.cancel_buttons and all(button.isEnabled() for button in popup.cancel_buttons)


def test_nothing_runs_once_the_window_is_closing(qtbot, window, monkeypatch, cluster):
    cluster.asked.before = window.job_actions.cancel  # the shutdown step, dialog still open
    menu_spy(monkeypatch, choose=CANCEL)
    window.remote.show_menu([FOLDER], QPoint())
    qtbot.waitUntil(lambda: cluster.asked.shown != [], timeout=5000)
    qtbot.wait(200)
    assert not window.job_actions.busy_now and cluster.run.argvs == []  # spec 71 R5


def test_the_reason_disables_the_buttons(qtbot, window_factory, demo_project, monkeypatch, cluster):
    window = remote_window(
        window_factory, demo_project, monkeypatch, FakeListing(), delete_command=""
    )
    qtbot.waitUntil(lambda: window.jobs.result is not None, timeout=5000)
    popup = open_popup(qtbot, window)
    assert popup.cancel_buttons and all(not b.isEnabled() for b in popup.cancel_buttons)
    assert {b.toolTip() for b in popup.cancel_buttons} == {NO_DELETE}


# -- the dialog (R6) -------------------------------------------------------------------------------
ROWS = [[("Job", "Bands-kao-b"), ("ID", "24000"), ("Pasta", f"{ACCOUNT}:{BANDS}")]]


def test_the_dialog_shows_the_job_the_method_and_the_command(qtbot):
    dialog = CancelDialog(ROWS, "arquivo de parada do pw.x (al.EXIT)", NOTE_EXIT, TOUCH)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Cancelar simulação"
    assert [label.text() for label in dialog.values] == [
        "Bands-kao-b",
        "24000",
        f"{ACCOUNT}:{BANDS}",
    ]
    assert (
        dialog.method.text() == "arquivo de parada do pw.x (al.EXIT)"
        and dialog.method.font().bold()
    )
    assert dialog.command.text() == TOUCH and dialog.note.text() == NOTE_EXIT
    assert dialog.back_button.isDefault() and not dialog.cancel_button.isDefault()
    assert not dialog.cancel_button.autoDefault()


def test_back_and_enter_decline_only_the_button_confirms(qtbot):
    drive_modal(lambda dialog: dialog.back_button.click())
    assert ask_cancel(None, ROWS, "m", "n", TOUCH) is False  # type: ignore[arg-type]
    drive_modal(lambda dialog: QTest.keyClick(dialog, Qt.Key.Key_Return))
    assert ask_cancel(None, ROWS, "m", "n", TOUCH) is False  # type: ignore[arg-type]
    drive_modal(lambda dialog: dialog.cancel_button.click())
    assert ask_cancel(None, ROWS, "m", "n", TOUCH) is True  # type: ignore[arg-type]
