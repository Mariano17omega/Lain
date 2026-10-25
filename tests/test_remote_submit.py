"""Submitting a ``.qsub`` (spec 69 R2): the line, the answer, and never over a running job of the
user in the same folder. ``list_remote``, ``fetch_jobs`` and ``run_action`` are fakes: no network."""

import pytest

from qe_studio.core.cluster_jobs import JobsFailure
from qe_studio.core.config import parse_config
from qe_studio.core.remote import submit as submit_module
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.listing import NOT_FOUND, RemoteFailure
from qe_studio.core.remote.submit import (
    SubmitBlocked,
    SubmitPlan,
    Submitted,
    parse_submitted,
    plan_submit,
    submit,
    submit_line,
)
from qe_studio.core.sync.command import CommandResult

from action_helpers import FakeAction
from jobs_helpers import EMPTY, USER, FakeFetch, snapshot, with_mine
from remote_helpers import FakeListing, entries

ROOT = "/home/u/runs"
BANDS = f"{ROOT}/ilita/Bands"
ANSWER = 'Your job 24123 ("Bands-kao-b") has been submitted\n'


def config(**cluster):
    settings = {"host": "hpc.example", "user": USER, **cluster}
    return parse_config({"paths": {"remote_root": ROOT}, "cluster": settings})


@pytest.fixture
def fakes(monkeypatch):
    """``(listing, fetch, run)``: ``BANDS`` holds the script, the queue has no job of the user."""
    listing = FakeListing({BANDS: entries(files=("bands.qsub", "bands.in"))})
    fetch, run = FakeFetch(snapshot(EMPTY)), FakeAction(CommandResult(0, ANSWER, ""))
    monkeypatch.setattr(submit_module, "list_remote", listing)
    monkeypatch.setattr(submit_module, "fetch_jobs", fetch)
    monkeypatch.setattr(submit_module, "run_action", run)
    return listing, fetch, run


def test_the_line_is_exact():
    assert submit_line(config(), BANDS, "bands.qsub") == (
        f"cd {BANDS} && chmod a+x bands.qsub && qsub bands.qsub"
    )
    assert submit_line(config(submit_command="/opt/sge/bin/qsub"), BANDS, "x.qsub").endswith(
        "&& /opt/sge/bin/qsub x.qsub"
    )


def test_the_answer_of_qsub_is_read():
    assert parse_submitted(ANSWER) == Submitted("24123", "Bands-kao-b")
    assert parse_submitted("warning: no project\n" + ANSWER) == Submitted("24123", "Bands-kao-b")
    assert parse_submitted('Your job-array 1.1-10:1 ("x") has been submitted') is None
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


def test_a_queue_that_cannot_be_read_blocks_the_plan(fakes):
    _listing, fetch, run = fakes
    fetch.result = JobsFailure("O cluster não respondeu a qstatus -a a tempo.", connection=True)
    blocked = plan_submit(config(), BANDS, "bands.qsub")
    assert blocked == SubmitBlocked(
        "Não foi possível conferir se já roda um job nesta pasta: O cluster não respondeu a "
        "qstatus -a a tempo. Nada foi submetido."
    )
    assert run.commands == []


def test_a_listing_that_fails_is_an_action_failure(fakes):
    listing, fetch, _run = fakes
    listing.folders[BANDS] = RemoteFailure(NOT_FOUND, missing=True)
    assert plan_submit(config(), BANDS, "bands.qsub") == ActionFailure(NOT_FOUND, missing=True)
    assert fetch.calls == []


def test_an_unsafe_name_is_never_planned(fakes):
    listing, _fetch, _run = fakes
    failure = plan_submit(config(), BANDS, "a b.qsub")
    assert isinstance(failure, ActionFailure) and failure.local
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

    run.result = CommandResult(0, "\n  Job queued somewhere else\n", "")
    assert submit(config(), plan) == "Job queued somewhere else"

    run.result = CommandResult(1, "", "Unable to read script file because of error\n")
    failure = submit(config(), plan)
    assert failure == ActionFailure(
        "qsub terminou com código 1: Unable to read script file because of error"
    )

    run.result = ActionFailure("Não foi possível executar o ssh (x).", local=True)
    assert submit(config(), plan) == run.result
