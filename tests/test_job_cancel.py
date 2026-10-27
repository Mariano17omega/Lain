"""Cancelling a job (spec 70 R2, spec 71 R2): the stop file for a running job of the folder, one per
prefix of its SCF, relax and vc-relax inputs, ``qdel`` for a job still waiting, and a fresh queue
before either. ``list_remote``, ``fetch_jobs``, ``fetch_stop_sources`` and ``run_action`` are fakes:
no network."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core.cluster_jobs import Job, JobsFailure, JobsSnapshot
from qe_studio.core.config import parse_config
from qe_studio.core.remote import job_cancel
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.inputs import StopSource
from qe_studio.core.remote.job_cancel import (
    Done,
    NotRunning,
    Refused,
    StopPlan,
    delete_line,
    delete_waiting,
    exit_line,
    plan_stop,
    stop,
    waiting_check,
)
from qe_studio.core.sync.command import CommandResult

from action_helpers import FakeAction
from jobs_helpers import EMPTY, QSTATUS_ALL, USER, FakeFetch, snapshot, with_mine
from remote_helpers import FakeListing, entries

ROOT = "/home/u/runs"
BANDS = f"{ROOT}/ilita/Bands"
TOUCH = f"touch {BANDS}/al.EXIT"


def config(**cluster):
    settings = {"host": "hpc.example", "user": USER, **cluster}
    return parse_config({"paths": {"remote_root": ROOT}, "cluster": settings})


AL = (StopSource("al", ("al.scf.in",)),)


class FakeSources:
    def __init__(self, result=AL):
        self.result, self.calls = result, []

    def __call__(self, _config, remote_dir, password=None):
        self.calls.append(remote_dir)
        return self.result


@pytest.fixture
def fakes(monkeypatch):
    """``(listing, fetch, prefixes, run)``: ``BANDS`` holds the ``.o`` of job 24000, which runs."""
    listing = FakeListing({BANDS: entries("tmp", files=("al.scf.in", "Bands-kao-b.o24000"))})
    fetch = FakeFetch(snapshot(with_mine("Bands-kao-b", waiting=2)))
    prefixes, run = FakeSources(), FakeAction()
    monkeypatch.setattr(job_cancel, "list_remote", listing)
    monkeypatch.setattr(job_cancel, "fetch_jobs", fetch)
    monkeypatch.setattr(job_cancel, "fetch_stop_sources", prefixes)
    monkeypatch.setattr(job_cancel, "run_action", run)
    return listing, fetch, prefixes, run


def running_job():
    return snapshot(with_mine("Bands-kao-b")).running[-1]


def waiting_job(index=0):
    return snapshot(with_mine(waiting=2)).waiting[2 + index]  # after the two of usuario_a


# -- the stop file ---------------------------------------------------------------------------------
def test_a_running_job_of_the_folder_gets_its_stop_file(fakes):
    listing, fetch, prefixes, run = fakes
    plan = plan_stop(config(), BANDS, "pw")
    assert plan == StopPlan(BANDS, (running_job(),), AL, TOUCH)
    assert plan.prefixes == ("al",) and plan.files == ("al.EXIT",)
    assert listing.calls == [BANDS] and fetch.calls == ["pw"] and prefixes.calls == [BANDS]
    assert run.commands == []  # planning changes nothing

    assert stop(config(), plan, "pw") == Done(
        "Pedido de parada criado: al.EXIT. O pw.x para na próxima verificação."
    )
    assert run.commands == [TOUCH] and fetch.calls == ["pw", "pw"]  # the queue asked again


def test_two_prefixes_one_line():
    assert exit_line(config(), BANDS, ("al", "al_bands")) == (
        f"touch {BANDS}/al.EXIT {BANDS}/al_bands.EXIT"
    )
    spaced = parse_config({"paths": {"remote_root": "/home/u/my runs"}, "cluster": {}})
    assert exit_line(spaced, "/home/u/my runs/Al", ("al",)) == "touch '/home/u/my runs'/Al/al.EXIT"
    with pytest.raises(ValueError):
        exit_line(config(), "/elsewhere/Al", ("al",))


@pytest.mark.parametrize(
    "files",
    [
        ("al.scf.in",),  # no scheduler output
        ("al.scf.in", "Bands-kao-b.o23000"),  # an old run of the same name
        ("al.scf.in", "Bands-kao.o24000"),  # another name
        ("al.scf.in", "hBN+Sm-1.o23591"),  # a job of usuario_b
    ],
)
def test_no_running_job_of_the_user_in_the_folder(fakes, files):
    listing, _fetch, prefixes, run = fakes
    listing.folders[BANDS] = entries(files=files)
    result = plan_stop(config(), BANDS)
    assert isinstance(result, NotRunning)
    assert result.message.startswith("Nenhum job seu em execução nesta pasta")
    assert prefixes.calls == [] and run.commands == []


def test_without_an_scf_or_relax_input_there_is_no_stop_file(fakes):
    _listing, _fetch, prefixes, run = fakes
    prefixes.result = ()  # e.g. only nscf or bands inputs (spec 71 R2)
    result = plan_stop(config(), BANDS)
    assert isinstance(result, NotRunning)
    assert result.message.startswith("Nenhum input de scf, relax ou vc-relax do pw.x")
    assert run.commands == []


def test_one_stop_file_per_prefix_of_the_sources(fakes):
    _listing, _fetch, prefixes, run = fakes
    prefixes.result = (
        StopSource("e30", ("ecut30.in",)),
        StopSource("e40", ("ecut40.in",)),
    )
    plan = plan_stop(config(), BANDS)
    assert isinstance(plan, StopPlan)
    assert plan.line == f"touch {BANDS}/e30.EXIT {BANDS}/e40.EXIT"
    assert plan.files == ("e30.EXIT", "e40.EXIT")


def test_failures_before_the_plan(fakes):
    listing, fetch, prefixes, _run = fakes
    prefixes.result = ActionFailure("prefix não suportado para o arquivo de parada: a b.")
    assert plan_stop(config(), BANDS) == prefixes.result

    fetch.result = JobsFailure("O cluster não respondeu a qstatus -a a tempo.", connection=True)
    assert plan_stop(config(), BANDS) == ActionFailure(
        "Não foi possível conferir o estado do job no cluster: O cluster não respondeu a qstatus "
        "-a a tempo. Nada foi feito.",
        connection=True,
    )
    calls = len(listing.calls)
    failure = plan_stop(config(), "/elsewhere/Bands")
    assert isinstance(failure, ActionFailure) and failure.local
    assert len(listing.calls) == calls  # refused before the cluster is asked


def test_a_job_that_ended_during_the_dialog_gets_no_stop_file(fakes):
    _listing, fetch, _prefixes, run = fakes
    plan = plan_stop(config(), BANDS)
    assert isinstance(plan, StopPlan)
    fetch.result = snapshot(QSTATUS_ALL)  # it ended
    assert stop(config(), plan) == Refused(
        "O job 24000 não está mais em execução: nada foi criado."
    )
    fetch.result = JobsFailure("x", auth=True)
    failure = stop(config(), plan)
    assert isinstance(failure, ActionFailure) and failure.auth
    assert run.commands == []  # no touch


def test_a_touch_that_fails_says_why(fakes):
    _listing, _fetch, _prefixes, run = fakes
    plan = plan_stop(config(), BANDS)
    assert isinstance(plan, StopPlan)
    run.result = CommandResult(1, "", "touch: cannot touch 'x': Permission denied\n")
    assert stop(config(), plan) == ActionFailure(
        "touch terminou com código 1: touch: cannot touch 'x': Permission denied"
    )
    run.result = CommandResult(127, "", "bash: touch: command not found\n")
    assert stop(config(), plan) == ActionFailure(
        "O comando touch não foi encontrado no cluster.", missing=True
    )


# -- qdel ------------------------------------------------------------------------------------------
def test_a_waiting_job_is_deleted_by_its_id(fakes):
    _listing, fetch, _prefixes, run = fakes
    job = waiting_job()
    assert delete_line(config(), job) == "qdel 25000"
    assert delete_line(config(delete_command="/opt/sge/bin/qdel"), job) == "/opt/sge/bin/qdel 25000"
    assert delete_waiting(config(), job, "pw") == Done("Job 25000 (Queued-0) cancelado com qdel.")
    assert run.commands == ["qdel 25000"] and fetch.calls == ["pw"]


def test_an_id_that_is_not_a_number_is_never_sent():
    job = Job("1;rm", 1, "x", USER, "10/24/2026 10:00:00", None, False)
    with pytest.raises(ValueError):
        delete_line(config(), job)


@pytest.mark.parametrize(
    ("queue", "message"),
    [
        (  # it started: the same ID now runs
            EMPTY.replace(
                "jobs:\n", f"jobs:\n  25000 16 Queued-0 {USER} 10/24/2026 10:30:00 q\n", 1
            ),
            "O job 25000 começou a rodar: o qdel não é usado em jobs em execução. Cancele pela "
            "pasta dele, no modo cluster (Cancelar simulação…).",
        ),
        (EMPTY, "O job 25000 não está mais na fila: nada foi feito."),
        (
            with_mine(waiting=1, queued="Outro"),
            "O job 25000 da fila não é mais Queued-0: nada foi feito.",
        ),
    ],
)
def test_qdel_never_runs_on_a_job_that_is_not_waiting(fakes, queue, message):
    _listing, fetch, _prefixes, run = fakes
    fetch.result = snapshot(queue)
    assert delete_waiting(config(), waiting_job()) == Refused(message)
    assert run.commands == []


def test_a_queue_that_cannot_be_read_runs_nothing(fakes):
    _listing, fetch, _prefixes, run = fakes
    fetch.result = JobsFailure("O comando qstatus não foi encontrado.", missing=True)
    failure = delete_waiting(config(), waiting_job())
    assert isinstance(failure, ActionFailure) and failure.missing
    assert failure.message.endswith("Nada foi feito.")
    assert run.commands == []


def test_a_qdel_that_fails_says_why(fakes):
    _listing, _fetch, _prefixes, run = fakes
    run.result = CommandResult(1, "", 'denied: job "25000" does not exist\n')
    assert delete_waiting(config(), waiting_job()) == ActionFailure(
        'qdel terminou com código 1: denied: job "25000" does not exist'
    )


def test_another_owner_s_job_of_the_same_id_is_refused():
    fresh = snapshot(with_mine(waiting=1))
    other = Job("25000", 16, "Queued-0", "usuario_a", "10/24/2026 10:00:00", None, False)
    swapped = JobsSnapshot(fresh.running, (*fresh.waiting[:2], other), fresh.fetched_at)
    assert isinstance(waiting_check(swapped, waiting_job(), USER), Refused)


# -- the property ----------------------------------------------------------------------------------
IDS, NAMES, OWNERS = ("1", "2", "3"), ("a", "b"), (USER, "outro")


@st.composite
def jobs(draw, running: bool) -> Job:
    return Job(
        draw(st.sampled_from(IDS)),
        1,
        draw(st.sampled_from(NAMES)),
        draw(st.sampled_from(OWNERS)),
        "10/24/2026 10:00:00",
        "q" if running else None,
        running,
    )


@given(
    st.lists(jobs(True), max_size=4),
    st.lists(jobs(False), max_size=4),
    jobs(False),
)
def test_waiting_check_only_passes_a_job_still_waiting(running, waiting, job):
    fresh = JobsSnapshot(tuple(running), tuple(waiting), 0.0)
    result = waiting_check(fresh, job, USER)
    in_running = any(other.job_id == job.job_id for other in running)
    same = [other for other in waiting if other.job_id == job.job_id]
    if isinstance(result, Job):
        assert not in_running and result in waiting and result.job_id == job.job_id
        assert all(other.name == job.name and other.owner == USER for other in same)
    else:
        assert isinstance(result, Refused)
        assert (
            in_running
            or not same
            or any(other.name != job.name or other.owner != USER for other in same)
        )
