""" "Submeter…" in the cluster mode (spec 69 R4): the menu item, the reasons it is disabled, the block
by a running job, the confirmation and the answers. ``list_remote``, ``fetch_jobs`` and the ssh run
are fakes and ``ask_submit`` is patched where ``ui/job_actions.py`` imports it: no network."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint

from qe_studio.core.remote import actions
from qe_studio.core.remote import submit as submit_module
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.submit import SubmitBlocked, SubmitPlan, Submitted
from qe_studio.core.sync.command import CommandResult, remote_command
from qe_studio.ui import job_actions, jobs_controller
from qe_studio.ui.dialogs.cluster_action import SubmitDialog
from qe_studio.ui.job_actions import NO_QUEUE, NO_SUBMIT, WAIT
from qe_studio.ui.widgets.remote_model import RemotePath

from action_helpers import FakeCommand, toasts
from jobs_helpers import EMPTY, FakeFetch, snapshot, with_mine
from remote_helpers import ACCOUNT, REMOTE, FakeListing, entries, menu_spy, remote_window, turn_on

BANDS = f"{REMOTE}/03_bands"
SCRIPT = RemotePath(f"{BANDS}/bands.qsub", False)
SUBMIT = "Submeter…"
ANSWER = 'Your job 24123 ("Bands-kao-b") has been submitted\n'


class Asked:
    """``ask_submit``: the plans it was shown; answers ``answer`` after running ``before``."""

    def __init__(self, answer=True):
        self.answer, self.plans, self.before = answer, [], None

    def __call__(self, _parent, plan, account):
        self.plans.append((plan, account))
        if self.before is not None:
            self.before()
        return self.answer


@pytest.fixture
def cluster(monkeypatch):
    """The fakes: ``folders`` (the listings the submission reads), ``jobs`` (its queue), ``queue``
    (the top bar's), ``run`` and ``asked``."""
    folders = FakeListing({BANDS: entries(files=("bands.qsub", "bands.in"))})
    jobs, queue, run, asked = (
        FakeFetch(snapshot(EMPTY)),
        FakeFetch(),
        FakeCommand(CommandResult(0, ANSWER, "")),
        Asked(),
    )
    monkeypatch.setattr(submit_module, "list_remote", folders)
    monkeypatch.setattr(submit_module, "fetch_jobs", jobs)
    monkeypatch.setattr(actions, "run_command", run)
    monkeypatch.setattr(job_actions, "ask_submit", asked)
    monkeypatch.setattr(jobs_controller, "fetch_jobs", queue)
    return SimpleNamespace(folders=folders, jobs=jobs, queue=queue, run=run, asked=asked)


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


def test_a_forgotten_exit_file_is_a_warning_and_enter_cancels(qtbot):
    dialog = SubmitDialog(plan("pwscf.EXIT"), ACCOUNT)
    qtbot.addWidget(dialog)
    (warning,) = dialog.warnings
    assert warning.text().startswith("A pasta tem pwscf.EXIT: o pw.x vai parar")
    assert dialog.cancel_button.isDefault() and not dialog.submit_button.isDefault()
