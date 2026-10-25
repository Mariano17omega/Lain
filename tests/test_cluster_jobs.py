"""Reading ``qstatus`` (spec 64 R2): the two listings of the spec, names with spaces, empty and
unknown output, the user's jobs, and why a query failed (from its code and stderr)."""

import pytest

from qe_studio.core import cluster_jobs
from qe_studio.core.cluster_jobs import (
    JobsFailure,
    JobsSnapshot,
    classify,
    fetch_jobs,
    parse_qstatus,
    running_in,
)
from qe_studio.core.config import parse_config
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.rsync import FAILURE_HINTS

from jobs_helpers import EMPTY, QSTATUS_ALL, QSTATUS_MINE, USER, with_mine

HINTS = dict(FAILURE_HINTS)


def test_the_whole_queue():
    jobs = parse_qstatus(QSTATUS_ALL)
    assert [j.name for j in jobs.running] == ["Nd2Fe14B-4f-129", "hBN+Sm-1", "hBN+Eu-1"]
    assert [j.name for j in jobs.waiting] == ["Sm3NbO8-HP-130", "BNNT90-S-375"]
    first = jobs.running[0]
    assert (first.job_id, first.slots, first.owner) == ("23538", 32, "usuario_a")
    assert (first.date, first.queue, first.running) == ("10/15/2026 17:53:02", "physica.q", True)
    queued = jobs.waiting[1]
    assert (queued.job_id, queued.owner, queued.date) == (
        "23543",
        "usuario_a",
        "10/15/2026 18:07:00",
    )
    assert queued.queue is None and not queued.running


def test_the_short_date_drops_the_year_and_the_seconds():
    jobs = parse_qstatus(QSTATUS_ALL)
    assert jobs.running[0].short_date == "10/15 17:53"
    assert jobs.waiting[1].short_date == "10/15 18:07"
    assert jobs.running[0].date == "10/15/2026 17:53:02"  # the parsed text is untouched
    padless = parse_qstatus("Running jobs:\n  7 4 x  me  1/5/2026 9:03:07 q\n")
    assert padless.running[0].short_date == "1/5 9:03"


def test_the_user_variant_takes_the_owner_from_the_title():
    jobs = parse_qstatus(QSTATUS_MINE)
    assert jobs.running == ()
    assert [(j.name, j.owner) for j in jobs.waiting] == [
        ("Bands-kao-b", USER),
        ("PDS-B", USER),
        ("Bands-kao-001-p", USER),
    ]
    assert jobs.queued(USER) == jobs.waiting


def test_a_running_section_of_the_user():
    text = (
        "Running jobs for user: usuario\n"
        " job-ID  # name                      start time          running in\n"
        "--------------------------------------------------------------------\n"
        "  23700 16 Relax-1                   10/24/2026 08:00:00 physica.q\n"
    )
    (job,) = parse_qstatus(text).running
    assert (job.name, job.owner, job.queue) == ("Relax-1", USER, "physica.q")


def test_a_name_with_spaces_stays_whole():
    text = QSTATUS_ALL.replace("hBN+Sm-1                 ", "hBN Sm 1 final           ")
    assert parse_qstatus(text).running[1].name == "hBN Sm 1 final"


def test_a_running_job_without_a_queue():
    text = "Running jobs:\n  23538 32 Nd2Fe14B-4f-129 usuario_a 10/15/2026 17:53:02\n"
    (job,) = parse_qstatus(text).running
    assert (job.owner, job.queue) == ("usuario_a", None)


@pytest.mark.parametrize(
    "text", ["", "\n\n", EMPTY, "Running jobs:\n", QSTATUS_MINE.split(" job-ID")[0]]
)
def test_empty_output_or_titles_only_have_no_jobs(text):
    jobs = parse_qstatus(text)
    assert jobs.running == () and jobs.waiting == ()


@pytest.mark.parametrize("text", ["bash: warning: something\n", "hello world\n23538 32 x\n"])
def test_text_that_is_no_listing_raises(text):
    with pytest.raises(ValueError, match="qstatus -a"):
        parse_qstatus(text)


def test_an_odd_line_inside_a_listing_is_skipped():
    jobs = parse_qstatus(QSTATUS_ALL + "  (2 more jobs hidden)\n")
    assert len(jobs.running) == 3 and len(jobs.waiting) == 2


def test_mine_is_the_running_jobs_of_the_user_in_order():
    jobs = parse_qstatus(with_mine("Bands-A", "PDOS-B", waiting=2))
    assert [j.name for j in jobs.mine(USER)] == ["Bands-A", "PDOS-B"]
    assert len(jobs.queued(USER)) == 2
    assert [j.name for j in jobs.mine("usuario_b")] == ["hBN+Sm-1", "hBN+Eu-1"]
    assert jobs.mine("nobody") == ()


# -- failures (R2.4) --------------------------------------------------------------------------
def failure(code, stderr="", stdout="", timed_out=False) -> JobsFailure:
    result = classify(CommandResult(code, stdout, stderr, timed_out), "qstatus -a")
    assert isinstance(result, JobsFailure)
    return result


def test_a_refused_login():
    found = failure(255, "usuario@cluster: Permission denied (publickey,password).\n")
    assert found.auth and not (found.connection or found.missing)
    assert found.message == HINTS["Permission denied"]


def test_no_connection():
    found = failure(255, "ssh: connect to host cluster port 22: Connection refused\n")
    assert found.connection and not (found.auth or found.missing)
    assert found.message == HINTS["Connection refused"]
    assert failure(255).connection  # ssh's own exit code, nothing said


def test_a_command_the_cluster_does_not_have():
    for found in (failure(127, "bash: qstatus: command not found\n"), failure(127)):
        assert found.missing and not (found.auth or found.connection)
        assert "qstatus -a" in found.message and "cluster.jobs_command" in found.message


def test_another_exit_code_says_the_last_line():
    found = failure(2, "qstatus: reading\nqstatus: cannot reach qmaster\n")
    assert not (found.auth or found.connection or found.missing)
    assert found.message == "qstatus -a terminou com código 2: qstatus: cannot reach qmaster"
    assert failure(1).message == "qstatus -a terminou com código 1."


def test_a_timeout_counts_as_no_connection():
    found = failure(None, timed_out=True)
    assert found.connection and "qstatus -a" in found.message


def test_an_unknown_listing_is_a_failure_of_the_command():
    found = failure(0, stdout="something else\n")
    assert found.message == "Saída de qstatus -a não reconhecida."
    assert not (found.auth or found.connection or found.missing or found.local)


def test_a_good_run_is_a_snapshot():
    result = classify(CommandResult(0, QSTATUS_ALL, ""), "qstatus -a")
    assert isinstance(result, JobsSnapshot) and len(result.running) == 3


def test_ssh_that_cannot_be_run_is_a_local_failure():
    config = parse_config(
        {"cluster": {"host": "hpc.example", "user": USER}, "sync": {"ssh_binary": "/no/such/ssh"}}
    )
    found = fetch_jobs(config)
    assert isinstance(found, JobsFailure) and found.local and not found.connection


def test_fetch_runs_the_configured_command_with_the_time_limit(monkeypatch):
    seen = []

    def fake(argv, env, timeout_s):
        seen.append((argv, timeout_s))
        return CommandResult(0, QSTATUS_MINE, "")

    monkeypatch.setattr(cluster_jobs, "run_command", fake)
    cluster = {"host": "hpc.example", "user": USER, "jobs_command": "qstatus", "connect_timeout": 5}
    result = fetch_jobs(parse_config({"cluster": cluster}))
    assert isinstance(result, JobsSnapshot) and len(result.waiting) == 3
    ((argv, timeout_s),) = seen
    assert argv[-2:] == [f"{USER}@hpc.example", "qstatus"] and timeout_s == 35


# -- spec 69 R2.2: a running job of the user in a folder ---------------------------------------------
def test_a_running_job_is_in_the_folder_of_its_output():
    jobs = parse_qstatus(with_mine("Bands-kao-b", "PDS-B"))  # jobs 24000 and 24001
    names = ["bands.qsub", "Bands-kao-b.o24000", "bands.out"]
    assert [job.job_id for job in running_in(names, jobs, USER)] == ["24000"]
    assert [job.name for job in running_in([*names, "PDS-B.o24001"], jobs, USER)] == [
        "Bands-kao-b",
        "PDS-B",
    ]


@pytest.mark.parametrize(
    "name",
    [
        "Bands-kao-b.o23000",  # an old run: its ID is not in the queue
        "Bands-kao-b.e24000",  # the error stream, not the output
        "Outro.o24000",  # the same ID with another name
        "Bands-kao-b.o24000.bak",
        "Bands-kao-b.po24000",
    ],
)
def test_other_files_are_no_running_job(name):
    jobs = parse_qstatus(with_mine("Bands-kao-b"))
    assert running_in([name], jobs, USER) == ()


def test_a_job_of_another_user_or_waiting_does_not_count():
    jobs = parse_qstatus(with_mine(waiting=1))
    others = ["Nd2Fe14B-4f-129.o23538", "Queued-0.o25000"]  # usuario_a's running, ours waiting
    assert running_in(others, jobs, USER) == ()
    assert [j.job_id for j in running_in(others, jobs, "usuario_a")] == ["23538"]
