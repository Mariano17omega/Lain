""" "Submeter…" in the cluster mode (spec 69 R4, spec 71 R3–R5): the menu item, the reasons it is
disabled, the block by a running job, the question about a job of the same name, the confirmation and
the answers. ``list_remote``, ``fetch_jobs``, ``fetch_job_name`` and the ssh run are fakes and
``ask_submit`` and ``ask_same_name`` are patched where ``ui/job_actions.py`` imports them: no
network. The real dialogs run through ``drive_modal``."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from qe_studio.core.cluster_jobs import JobsFailure
from qe_studio.core.remote import actions
from qe_studio.core.remote import submit as submit_module
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.submit import SubmitBlocked, SubmitPlan, Submitted
from qe_studio.core.sync.command import CommandResult, remote_command
from qe_studio.core.sync.monitor import ConnectionState
from qe_studio.ui import job_actions, jobs_controller
from qe_studio.ui.dialogs.cluster_action import SameNameDialog, SubmitDialog, ask_same_name
from qe_studio.ui.job_actions import NO_QUEUE, NO_SUBMIT, WAIT
from qe_studio.ui.widgets.remote_model import RemotePath
from test_atoms_dialog import drive_modal

from action_helpers import FakeCommand, toasts
from jobs_helpers import EMPTY, FakeFetch, snapshot, with_mine
from remote_helpers import ACCOUNT, REMOTE, FakeListing, entries, menu_spy, remote_window, turn_on

BANDS = f"{REMOTE}/03_bands"
SCRIPT = RemotePath(f"{BANDS}/bands.qsub", False)
SUBMIT = "Submeter…"
ANSWER = 'Your job 24123 ("Bands-kao-b") has been submitted\n'
NAME = "Bands-kao-b"  # the script's #$ -N


class Asked:
    """``ask_submit``: the plans it was shown; answers ``answer`` after running ``before``."""

    def __init__(self, answer=True):
        self.answer, self.plans, self.before = answer, [], None

    def __call__(self, _parent, plan, account):
        self.plans.append((plan, account))
        if self.before is not None:
            self.before()
        return self.answer


class AskedName:
    """``ask_same_name``: the names and jobs it was shown; answers ``answer``."""

    def __init__(self, answer=True):
        self.answer, self.shown = answer, []

    def __call__(self, _parent, name, jobs):
        self.shown.append((name, tuple(job.job_id for job in jobs)))
        return self.answer


@pytest.fixture
def cluster(monkeypatch):
    """The fakes: ``folders`` (the listings the submission reads), ``jobs`` (its queue), ``queue``
    (the top bar's), ``run``, ``asked`` and ``asked_name``; the script's job name is ``NAME``."""
    folders = FakeListing({BANDS: entries(files=("bands.qsub", "bands.in"))})
    jobs, queue, run, asked = (
        FakeFetch(snapshot(EMPTY)),
        FakeFetch(),
        FakeCommand(CommandResult(0, ANSWER, "")),
        Asked(),
    )
    monkeypatch.setattr(submit_module, "list_remote", folders)
    monkeypatch.setattr(submit_module, "fetch_jobs", jobs)
    monkeypatch.setattr(submit_module, "fetch_job_name", lambda *_args: NAME)
    monkeypatch.setattr(actions, "run_command", run)
    monkeypatch.setattr(job_actions, "ask_submit", asked)
    asked_name = AskedName()
    monkeypatch.setattr(job_actions, "ask_same_name", asked_name)
    monkeypatch.setattr(jobs_controller, "fetch_jobs", queue)
    return SimpleNamespace(
        folders=folders, jobs=jobs, queue=queue, run=run, asked=asked, asked_name=asked_name
    )


@pytest.fixture
def window(qtbot, window_factory, demo_project, monkeypatch, cluster):
    browse = FakeListing({REMOTE: entries("03_bands"), BANDS: entries(files=("bands.qsub",))})
    window = remote_window(window_factory, demo_project, monkeypatch, browse)
    window.browse = browse
    return window


def submit_item(qtbot, window, monkeypatch, item=SCRIPT):
    """Click "Submeter…" on ``item`` and wait for the end of the action; its answer."""
    menu_spy(monkeypatch, choose=SUBMIT)
    with qtbot.waitSignal(window.job_actions.done, timeout=5000) as blocker:
        window.remote.show_menu([item], QPoint())
    return blocker.args[0]


def items_of(window, monkeypatch, items):
    menus = menu_spy(monkeypatch)
    window.remote.show_menu(items, QPoint())
    return {text: (enabled, tip) for text, enabled, tip in menus[0]}


def test_submit_shows_on_a_qsub_only(window, monkeypatch):
    assert items_of(window, monkeypatch, [SCRIPT])[SUBMIT][0]  # enabled
    for items in (
        [RemotePath(f"{BANDS}/bands.in", False)],
        [RemotePath(BANDS, True)],
        [SCRIPT, RemotePath(f"{BANDS}/other.qsub", False)],
    ):
        assert SUBMIT not in items_of(window, monkeypatch, items), items


@pytest.mark.parametrize(
    ("settings", "reason"), [({"submit_command": ""}, NO_SUBMIT), ({"jobs_command": ""}, NO_QUEUE)]
)
def test_a_setting_turns_it_off(window_factory, demo_project, monkeypatch, settings, reason):
    window = remote_window(window_factory, demo_project, monkeypatch, FakeListing(), **settings)
    assert items_of(window, monkeypatch, [SCRIPT])[SUBMIT] == (False, reason)


def test_an_unsafe_name_is_disabled_with_the_reason(window, monkeypatch):
    unsafe = RemotePath(f"{BANDS}/a b.qsub", False)
    enabled, tip = items_of(window, monkeypatch, [unsafe])[SUBMIT]
    assert not enabled and "Nome não suportado" in tip


def test_one_action_at_a_time(qtbot, window, monkeypatch, cluster):
    cluster.folders.hold()
    try:
        menu_spy(monkeypatch, choose=SUBMIT)
        window.remote.show_menu([SCRIPT], QPoint())
        qtbot.waitUntil(lambda: cluster.folders.calls != [])
        assert items_of(window, monkeypatch, [SCRIPT])[SUBMIT] == (False, WAIT)
        assert "Conferindo a pasta no cluster…" in window.plot_workflow.busy.labels
    finally:
        with qtbot.waitSignal(window.job_actions.done, timeout=5000):
            cluster.folders.release()


def test_a_running_job_in_the_folder_blocks_without_a_dialog(qtbot, window, monkeypatch, cluster):
    cluster.folders.folders[BANDS] = entries(files=("bands.qsub", "Bands-kao-b.o24000"))
    cluster.jobs.result = snapshot(with_mine("Bands-kao-b"))
    result = submit_item(qtbot, window, monkeypatch)
    assert isinstance(result, SubmitBlocked)
    assert (result.message, "warning") in toasts(window)
    assert cluster.asked.plans == [] and cluster.run.argvs == []


def test_the_plan_reaches_the_dialog_with_the_exit_warning(qtbot, window, monkeypatch, cluster):
    cluster.folders.folders[BANDS] = entries(files=("bands.qsub", "pwscf.EXIT"))
    cluster.asked.answer = False
    assert submit_item(qtbot, window, monkeypatch) is None  # declined: nothing runs
    ((plan, account),) = cluster.asked.plans
    assert plan.exit_files == ("pwscf.EXIT",) and account == ACCOUNT
    assert plan.steps == (f"cd {BANDS}", "chmod a+x bands.qsub", "qsub bands.qsub")
    assert cluster.run.argvs == [] and cluster.folders.calls == [BANDS]


def test_confirming_submits_and_says_so(qtbot, window, monkeypatch, cluster):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed):
        window.remote.open(BANDS)
    window.remote.open(REMOTE)  # BANDS stays in the cache
    queries = len(cluster.queue.calls)
    assert submit_item(qtbot, window, monkeypatch) == Submitted("24123", "Bands-kao-b")
    ((plan, _account),) = cluster.asked.plans
    assert cluster.run.argvs == [remote_command(window.config, plan.line)]
    assert ("Job 24123 (Bands-kao-b) submetido.", "info") in toasts(window)
    assert window.status.message.text() == "Job 24123 (Bands-kao-b) submetido."
    assert cluster.folders.calls == [BANDS, BANDS]  # checked again right before qsub
    qtbot.waitUntil(lambda: len(cluster.queue.calls) > queries)  # the new job in the queue
    assert window.remote.browser is not None and window.remote.browser.get(BANDS) is None
    assert window.remote.current == REMOTE  # out of the cache, not listed: it is not shown


def test_the_folder_shown_is_listed_again(qtbot, window, monkeypatch, cluster):
    turn_on(qtbot, window)
    with qtbot.waitSignal(window.remote.listed):
        window.remote.open(BANDS)
    calls = window.browse.calls.count(BANDS)
    submit_item(qtbot, window, monkeypatch)
    qtbot.waitUntil(lambda: window.browse.calls.count(BANDS) > calls)


def test_a_job_that_starts_during_the_dialog_blocks_the_submission(
    qtbot, window, monkeypatch, cluster
):
    def job_starts():
        cluster.folders.folders[BANDS] = entries(files=("bands.qsub", "Bands-kao-b.o24000"))
        cluster.jobs.result = snapshot(with_mine("Bands-kao-b"))

    cluster.asked.before = job_starts
    result = submit_item(qtbot, window, monkeypatch)
    assert isinstance(result, SubmitBlocked) and (result.message, "warning") in toasts(window)
    assert cluster.run.argvs == []  # no qsub


def test_an_answer_that_is_not_recognized_warns(qtbot, window, monkeypatch, cluster):
    cluster.run.result = CommandResult(0, "Job accepted\n", "")
    assert submit_item(qtbot, window, monkeypatch) == "Job accepted"
    text = "O qsub terminou sem erro, mas a resposta não foi reconhecida: Job accepted"
    assert (text, "warning") in toasts(window)


def test_a_failure_says_why(qtbot, window, monkeypatch, cluster):
    cluster.run.result = CommandResult(1, "", "Unable to read script file\n")
    result = submit_item(qtbot, window, monkeypatch)
    assert isinstance(result, ActionFailure)
    text = "A submissão falhou: qsub terminou com código 1: Unable to read script file"
    assert (text, "error") in toasts(window)


def test_a_refused_login_forgets_the_password(
    qtbot, window_factory, demo_project, monkeypatch, cluster
):
    window = remote_window(
        window_factory, demo_project, monkeypatch, FakeListing(), auth="password"
    )
    monkeypatch.delenv("QE_STUDIO_SSH_PASSWORD", raising=False)
    known = {"password": None}
    asked = []

    def session_password(ask=True):
        if known["password"] is None and ask:
            asked.append(True)
            known["password"] = "senha"
        return known["password"]

    monkeypatch.setattr(window.sync, "session_password", session_password)
    monkeypatch.setattr(window.sync, "forget_password", lambda: known.update(password=None))
    cluster.asked.answer = False
    submit_item(qtbot, window, monkeypatch)
    submit_item(qtbot, window, monkeypatch)
    assert asked == [True]  # the password dialog once, then the session's
    assert cluster.folders.passwords == ["senha", "senha"]

    cluster.asked.answer = True
    cluster.run.result = CommandResult(255, "", "lain-test@h: Permission denied (password).\n")
    result = submit_item(qtbot, window, monkeypatch)
    assert isinstance(result, ActionFailure) and result.auth
    assert known["password"] is None  # forgotten: the next action asks again


def test_cancelling_the_password_does_nothing(window_factory, demo_project, monkeypatch, cluster):
    window = remote_window(
        window_factory, demo_project, monkeypatch, FakeListing(), auth="password"
    )
    monkeypatch.delenv("QE_STUDIO_SSH_PASSWORD", raising=False)
    monkeypatch.setattr(window.sync, "session_password", lambda ask=True: None)
    menu_spy(monkeypatch, choose=SUBMIT)
    window.remote.show_menu([SCRIPT], QPoint())
    assert cluster.folders.calls == [] and not window.job_actions.busy_now


# -- a job of the same name, the log, the close (spec 71 R3–R5) ------------------------------------
def test_a_job_of_the_same_name_asks_first(qtbot, window, monkeypatch, cluster):
    cluster.jobs.result = snapshot(with_mine(waiting=1, queued=NAME))  # 25000 waits elsewhere
    cluster.asked_name.answer = False
    assert submit_item(qtbot, window, monkeypatch) is None
    assert cluster.asked_name.shown == [(NAME, ("25000",))]
    assert cluster.asked.plans == [] and cluster.run.argvs == []  # no submit dialog, no qsub

    cluster.asked_name.answer = True
    assert submit_item(qtbot, window, monkeypatch) == Submitted("24123", NAME)
    ((plan, _account),) = cluster.asked.plans  # then the usual confirmation
    assert plan.job_name == NAME and [job.job_id for job in plan.same_name] == ["25000"]


def test_without_a_job_of_the_same_name_nothing_more_is_asked(qtbot, window, monkeypatch, cluster):
    assert submit_item(qtbot, window, monkeypatch) == Submitted("24123", NAME)
    assert cluster.asked_name.shown == [] and len(cluster.asked.plans) == 1


def test_a_queue_that_does_not_answer_is_an_error_and_the_led_goes_offline(
    qtbot, window, monkeypatch, cluster
):
    cluster.jobs.result = JobsFailure(
        "O cluster não respondeu a qstatus -a a tempo.", connection=True
    )
    result = submit_item(qtbot, window, monkeypatch)
    assert isinstance(result, ActionFailure) and result.connection
    assert (f"A submissão falhou: {result.message}", "error") in toasts(window)
    assert window.monitor.state is ConnectionState.OFFLINE
    assert cluster.asked.plans == [] and cluster.run.argvs == []


def test_a_log_that_cannot_be_written_is_a_warning(qtbot, window, monkeypatch, cluster):
    def broken(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(submit_module, "record", broken)
    result = submit_item(qtbot, window, monkeypatch)
    assert result == Submitted("24123", NAME, log_error="disco cheio")
    text = (
        "Job 24123 (Bands-kao-b) submetido. O registro de jobs submetidos não pôde ser gravado "
        "(disco cheio)."
    )
    assert (text, "warning") in toasts(window)


def test_nothing_runs_once_the_window_is_closing(qtbot, window, monkeypatch, cluster):
    cluster.asked.before = window.job_actions.cancel  # the shutdown step, dialog still open
    menu_spy(monkeypatch, choose=SUBMIT)
    window.remote.show_menu([SCRIPT], QPoint())
    qtbot.waitUntil(lambda: cluster.asked.plans != [], timeout=5000)
    qtbot.wait(200)
    assert not window.job_actions.busy_now and cluster.run.argvs == []  # no qsub (spec 71 R5)


# -- the dialog (R4.4) -----------------------------------------------------------------------------
def plan(*exit_files: str) -> SubmitPlan:
    steps = (f"cd {BANDS}", "chmod a+x bands.qsub", "qsub bands.qsub")
    return SubmitPlan(BANDS, "bands.qsub", steps, exit_files)


def test_the_dialog_shows_the_folder_and_the_exact_commands(qtbot):
    dialog = SubmitDialog(plan(), ACCOUNT)
    qtbot.addWidget(dialog)
    texts = [label.text() for label in dialog.findChildren(type(dialog.commands))]
    assert "Submeter bands.qsub?" in texts and f"Pasta: {ACCOUNT}:{BANDS}" in texts
    assert dialog.commands.text() == f"cd {BANDS}\nchmod a+x bands.qsub\nqsub bands.qsub"
    assert dialog.windowTitle() == "Submeter no cluster"
    assert dialog.warnings == [] and dialog.submit_button.isDefault()


def test_the_dialog_shows_the_job_name(qtbot):
    named = SubmitPlan(BANDS, "bands.qsub", plan().steps, (), NAME)
    dialog = SubmitDialog(named, ACCOUNT)
    qtbot.addWidget(dialog)
    texts = [label.text() for label in dialog.findChildren(type(dialog.commands))]
    assert f"Job: {NAME}" in texts
    unnamed = SubmitDialog(plan(), ACCOUNT)
    qtbot.addWidget(unnamed)
    assert not any(
        t.startswith("Job:")
        for t in (x.text() for x in unnamed.findChildren(type(unnamed.commands)))
    )


def test_the_same_name_dialog_lists_the_jobs_and_enter_declines(qtbot):
    jobs = snapshot(with_mine(NAME, waiting=1, queued=NAME))
    mine = (jobs.running[-1], jobs.waiting[-1])
    dialog = SameNameDialog(NAME, mine)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Job com o mesmo nome"
    assert [row.text() for row in dialog.rows] == [
        "em execução desde 10/24/2026 09:00:00",
        "na fila desde 10/24/2026 10:00:00",
    ]
    assert dialog.back_button.isDefault() and not dialog.go_button.autoDefault()
    drive_modal(lambda shown: QTest.keyClick(shown, Qt.Key.Key_Return))
    assert ask_same_name(None, NAME, mine) is False  # type: ignore[arg-type]
    drive_modal(lambda shown: shown.go_button.click())
    assert ask_same_name(None, NAME, mine) is True  # type: ignore[arg-type]


def test_a_forgotten_exit_file_is_a_warning_and_enter_cancels(qtbot):
    dialog = SubmitDialog(plan("pwscf.EXIT"), ACCOUNT)
    qtbot.addWidget(dialog)
    (warning,) = dialog.warnings
    assert warning.text().startswith("A pasta tem pwscf.EXIT: o pw.x vai parar")
    assert dialog.cancel_button.isDefault() and not dialog.submit_button.isDefault()
