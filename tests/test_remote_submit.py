"""Submitting a ``.qsub`` (spec 69 R2, spec 71 R3–R4): the line, the answer, never over a running job
of the user in the same folder nor over a job Lain submitted from it still in the queue, the user's
jobs of the same name and the log of submitted jobs. ``list_remote``, ``fetch_jobs``,
``fetch_job_name`` and ``run_action`` are fakes: no network; the log is in the test's data folder."""

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote import submit as submit_module
from qe_studio.core.remote import submit_log
from qe_studio.core.remote.failure import RemoteFailure
from qe_studio.core.remote.listing import NOT_FOUND
from qe_studio.core.remote.submit import (
    SubmitBlocked,
    SubmitPlan,
    Submitted,
    parse_submitted,
    plan_submit,
    submit,
    submit_steps,
)
from qe_studio.core.remote.submit_log import read_log, record
from qe_studio.core.sync.command import CommandResult

from action_helpers import FakeAction
from jobs_helpers import EMPTY, USER, FakeFetch, snapshot, with_mine
from remote_helpers import FakeListing, entries

ROOT = "/home/u/runs"
BANDS = f"{ROOT}/ilita/Bands"
ANSWER = 'Your job 24123 ("Bands-kao-b") has been submitted\n'
NAME = "Bands-kao-b"  # the script's #$ -N
ACCOUNT = f"{USER}@hpc.example"


def config(**cluster):
    settings = {"host": "hpc.example", "user": USER, **cluster}
    return parse_config({"paths": {"remote_root": ROOT}, "cluster": settings})


@pytest.fixture
def fakes(monkeypatch):
    """``(listing, fetch, run)``: ``BANDS`` holds the script, whose job name is ``NAME``; the queue
    has no job of the user."""
    listing = FakeListing({BANDS: entries(files=("bands.qsub", "bands.in"))})
    fetch, run = FakeFetch(snapshot(EMPTY)), FakeAction(CommandResult(0, ANSWER, ""))
    monkeypatch.setattr(submit_module, "list_remote", listing)
    monkeypatch.setattr(submit_module, "fetch_jobs", fetch)
    monkeypatch.setattr(submit_module, "fetch_job_name", lambda *_args: NAME)
    monkeypatch.setattr(submit_module, "run_action", run)
    return listing, fetch, run


def line(cfg, folder, script) -> str:
    return SubmitPlan(folder, script, submit_steps(cfg, folder, script), ()).line


def test_the_line_is_exact():
    assert line(config(), BANDS, "bands.qsub") == (
        f"cd {BANDS} && chmod a+x bands.qsub && qsub bands.qsub"
    )
    assert line(config(submit_command="/opt/sge/bin/qsub"), BANDS, "x.qsub").endswith(
        "&& /opt/sge/bin/qsub x.qsub"
    )


def test_the_answer_of_qsub_is_read():
    assert parse_submitted(ANSWER) == Submitted("24123", "Bands-kao-b")
    assert parse_submitted("warning: no project\n" + ANSWER) == Submitted("24123", "Bands-kao-b")
    assert parse_submitted('Your job-array 1.1-10:1 ("x") has been submitted') == Submitted(
        "1", "x"
    )
    assert parse_submitted("") is None


def test_the_plan_reports_a_forgotten_exit_file(fakes):
    listing, fetch, _run = fakes
    listing.folders[BANDS] = entries("tmp", files=("bands.qsub", "pwscf.EXIT", "EXIT", "EXITO"))
    plan = plan_submit(config(), BANDS, "bands.qsub", "pw")
    assert plan == SubmitPlan(
        BANDS,
        "bands.qsub",
        (f"cd {BANDS}", "chmod a+x bands.qsub", "qsub bands.qsub"),
        ("pwscf.EXIT", "EXIT"),
        NAME,
        (),
    )
    assert plan.line == f"cd {BANDS} && chmod a+x bands.qsub && qsub bands.qsub"
    assert listing.calls == [BANDS] and listing.passwords == ["pw"] and fetch.calls == ["pw"]


def test_a_running_job_of_the_user_in_the_folder_blocks_the_plan(fakes):
    listing, fetch, run = fakes
    listing.folders[BANDS] = entries(files=("bands.qsub", "Bands-kao-b.o24000"))
    fetch.result = snapshot(with_mine("Bands-kao-b"))  # job 24000, running, of the user
    blocked = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(blocked, SubmitBlocked)
    assert "Bands-kao-b (job 24000)" in blocked.message
    assert run.commands == []


def test_a_queue_that_cannot_be_read_fails_with_its_flags(fakes):
    _listing, fetch, run = fakes
    fetch.result = RemoteFailure("O cluster não respondeu a qstatus -a a tempo.", connection=True)
    failure = plan_submit(config(), BANDS, "bands.qsub")
    assert failure == RemoteFailure(
        "Não foi possível conferir se já roda um job nesta pasta: O cluster não respondeu a "
        "qstatus -a a tempo. Nada foi submetido.",
        connection=True,
    )
    fetch.result = RemoteFailure("Permission denied", auth=True)
    failure = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(failure, RemoteFailure) and failure.auth  # spec 71 R4: the LED, the password
    assert run.commands == []


def test_a_listing_that_fails_is_an_action_failure(fakes):
    listing, fetch, _run = fakes
    listing.folders[BANDS] = RemoteFailure(NOT_FOUND, missing=True)
    assert plan_submit(config(), BANDS, "bands.qsub") == RemoteFailure(NOT_FOUND, missing=True)
    assert fetch.calls == []


def test_an_unsafe_name_is_never_planned(fakes):
    listing, _fetch, _run = fakes
    failure = plan_submit(config(), BANDS, "a b.qsub")
    assert isinstance(failure, RemoteFailure) and failure.local
    assert listing.calls == []


def test_a_job_that_starts_after_the_plan_blocks_the_submission(fakes):
    listing, fetch, run = fakes
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan)
    listing.folders[BANDS] = entries(files=("bands.qsub", "Bands-kao-b.o24000"))
    fetch.result = snapshot(with_mine("Bands-kao-b"))  # it started while the dialog was open
    assert isinstance(submit(config(), plan), SubmitBlocked)
    assert run.commands == []  # qsub never ran
    assert listing.calls == [BANDS, BANDS] and len(fetch.calls) == 2  # asked again, not cached


def test_the_three_answers_of_a_submission(fakes):
    _listing, _fetch, run = fakes
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan)
    assert submit(config(), plan) == Submitted("24123", "Bands-kao-b")
    assert run.commands == [plan.line]
    (logged,) = read_log()  # spec 71 R3
    assert (logged.account, logged.job_id, logged.name) == (ACCOUNT, "24123", "Bands-kao-b")
    assert (logged.remote_dir, logged.script) == (BANDS, "bands.qsub")

    run.result = CommandResult(0, "\n  Job queued somewhere else\n", "")
    assert submit(config(), plan) == "Job queued somewhere else"

    run.result = CommandResult(1, "", "Unable to read script file because of error\n")
    failure = submit(config(), plan)
    assert failure == RemoteFailure(
        "qsub terminou com código 1: Unable to read script file because of error"
    )

    run.result = RemoteFailure("Não foi possível executar o ssh (x).", local=True)
    assert submit(config(), plan) == run.result


# -- the log of submitted jobs and the name of the job (spec 71 R3) -------------------------------
def test_a_job_lain_submitted_from_the_folder_blocks_while_it_waits(fakes):
    _listing, fetch, run = fakes
    record(ACCOUNT, "25000", NAME, BANDS, "bands.qsub")
    fetch.result = snapshot(with_mine(waiting=1, queued=NAME))  # 25000 waits: no .o yet
    blocked = plan_submit(config(), BANDS, "bands.qsub")
    assert blocked == SubmitBlocked(
        f"O job 25000 ({NAME}), que o Lain submeteu desta pasta, ainda está na fila. Espere ele "
        "terminar ou cancele-o pela fila antes de submeter outro script."
    )
    fetch.result = snapshot(with_mine(NAME))  # running, its .o elsewhere (#$ -o)
    record(ACCOUNT, "24000", NAME, BANDS, "bands.qsub")
    blocked = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(blocked, SubmitBlocked) and "ainda está em execução" in blocked.message
    assert run.commands == []


@pytest.mark.parametrize(
    "logged",
    [
        (ACCOUNT, "25000", NAME, f"{ROOT}/other", "bands.qsub"),  # another folder
        (ACCOUNT, "25000", "Old-name", BANDS, "bands.qsub"),  # the ID reused by SGE
        ("outro@hpc.example", "25000", NAME, BANDS, "bands.qsub"),  # another account
    ],
)
def test_a_logged_job_of_elsewhere_does_not_block(fakes, logged):
    _listing, fetch, _run = fakes
    record(*logged)
    fetch.result = snapshot(with_mine(waiting=1, queued=NAME))
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan) and [job.job_id for job in plan.same_name] == ["25000"]


def test_the_plan_lists_the_user_s_jobs_of_the_same_name(fakes):
    _listing, fetch, _run = fakes
    queue = with_mine(NAME, "Other", waiting=2, queued=NAME)
    queue = queue.replace("hBN+Sm-1                ", f"{NAME:<24}")  # usuario_b's: not counted
    fetch.result = snapshot(queue)
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan) and plan.job_name == NAME
    assert [(job.job_id, job.running) for job in plan.same_name] == [
        ("24000", True),
        ("25000", False),
        ("25001", False),
    ]


def test_a_job_of_the_same_name_that_shows_up_after_the_question_blocks(fakes):
    _listing, fetch, run = fakes
    fetch.result = snapshot(with_mine(waiting=1, queued=NAME))
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan) and len(plan.same_name) == 1
    fetch.result = snapshot(with_mine(waiting=2, queued=NAME))  # 25001 came meanwhile
    blocked = submit(config(), plan)
    assert blocked == SubmitBlocked(
        f"Um job seu chamado {NAME} apareceu no cluster depois da confirmação (job 25001): nada "
        "foi submetido."
    )
    assert run.commands == []
    fetch.result = snapshot(with_mine(waiting=1, queued=NAME))  # the one already asked about
    assert submit(config(), plan) == Submitted("24123", NAME)


def test_a_log_that_cannot_be_written_never_undoes_the_job(fakes, monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(submit_module, "record", broken)
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan)
    assert submit(config(), plan) == Submitted("24123", NAME, log_error="disco cheio")
    assert read_log() == []


def test_a_job_array_is_written_in_the_log(fakes):
    _listing, _fetch, run = fakes
    run.result = CommandResult(
        0, f'Your job-array 24123.1-10:1 ("{NAME}") has been submitted\n', ""
    )
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan)
    assert submit(config(), plan) == Submitted("24123", NAME)
    assert [entry.job_id for entry in read_log()] == ["24123"]


def test_a_logged_job_whose_name_the_queue_cut_blocks(fakes):
    _listing, fetch, _run = fakes
    full = "Bands-kao-b-with-a-name-longer-than-the-column"
    record(ACCOUNT, "25000", full, BANDS, "bands.qsub")
    fetch.result = snapshot(with_mine(waiting=1, queued=full[:25]))
    assert isinstance(plan_submit(config(), BANDS, "bands.qsub"), SubmitBlocked)


def test_a_log_that_cannot_be_read_stops_the_submission(fakes, monkeypatch, tmp_path):
    """A waiting job leaves nothing else in the folder: without the log it would go unseen."""
    monkeypatch.setattr(submit_log, "log_path", lambda: tmp_path)  # reading a folder fails
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, RemoteFailure) and plan.local
    assert plan.message.endswith("Nada foi submetido.")


def test_a_failing_cd_is_named_and_not_qsub(fakes):
    _listing, _fetch, run = fakes
    plan = plan_submit(config(), BANDS, "bands.qsub")
    assert isinstance(plan, SubmitPlan)
    run.result = CommandResult(1, "", "bash: line 1: cd: /x: No such file or directory\n")
    answer = submit(config(), plan)
    assert isinstance(answer, RemoteFailure) and answer.message.startswith(
        "cd terminou com código 1"
    )
