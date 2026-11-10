"""The cluster's jobs (spec 64 R2): what ``cluster.jobs_command`` (``qstatus -a``) prints, read.

The format is the one of the ``qstatus`` script of the user's cluster (SGE underneath): sections
titled "Running jobs:" and "Waiting jobs:" ("… for user: <login>" without ``-a``, where the owner
column is left out), a header line, a line of dashes, then one job per line. A job line is read from
both ends: ``job-ID`` and ``#`` first; last the queue (running jobs only), the date and time and the
owner; what is left in the middle is the name, spaces and all. Dates stay as the cluster writes them,
in its time zone.

Submitting, cancelling and the trash all rely on this list, so a list that may be incomplete is a
failure, never a shorter list: a job line that cannot be read, or a scheduler that says it failed.

``fetch_jobs`` runs the command over ssh (``core/sync/command.py``) and blocks: it runs in a worker.
"""

from __future__ import annotations

import logging
import re
import shlex
import time
from collections.abc import Iterable
from dataclasses import dataclass

from ...i18n import _
from ..config import AppConfig
from ..sync.command import CommandResult, remote_command, run_command
from ..sync.rsync import child_env
from .failure import EXTRA_SECONDS, RemoteFailure, classify_failure

log = logging.getLogger(__name__)

SETTING = "cluster.jobs_command"
SHORTEST_CUT = 10  # SGE's narrowest name column: a shorter name in the queue is the whole name

_TITLE = re.compile(r"^(Running|Waiting) jobs(?: for user: (\S+))?:?$")
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_TIME = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_ID = re.compile(r"^\d+$")
# ``<name>.o<job-ID>``, the output of ``#$ -j y``; a task of an array job adds ``.<task>``
_STDOUT = re.compile(r"^(?P<name>.+)\.o(?P<id>\d+)(?:\.\d+)?$")
# What SGE says when it could not answer, while the ``qstatus`` script around it still ends with 0.
# Only these: ssh banners and login scripts also write on stderr, on every run.
_SCHEDULER_FAILED = re.compile(
    r"^.*(?:qmaster|commlib error|\bqstat\b.*not found).*$|^\s*(?:critical )?error:.*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Job:
    job_id: str
    slots: int  # the "#" column
    name: str
    owner: str | None
    date: str  # "10/15/2026 17:53:02": the start (running) or the submission (waiting)
    queue: str | None  # "running in"; None while waiting
    running: bool

    @property
    def short_date(self) -> str:
        """``10/15 17:53``: ``date`` without the year and the seconds, for the tables."""
        day, _sep, clock = self.date.partition(" ")
        return f"{day.rsplit('/', 1)[0]} {clock.rsplit(':', 1)[0]}"


@dataclass(frozen=True)
class JobsSnapshot:
    running: tuple[Job, ...]
    waiting: tuple[Job, ...]
    fetched_at: float  # epoch seconds

    def mine(self, user: str) -> tuple[Job, ...]:
        """The running jobs of ``user``, in the order of the listing."""
        return tuple(job for job in self.running if job.owner == user)

    def queued(self, user: str) -> tuple[Job, ...]:
        """The waiting jobs of ``user``."""
        return tuple(job for job in self.waiting if job.owner == user)


def same_job_name(listed: str, full: str) -> bool:
    """Whether ``listed``, a name in the queue, can be the job called ``full`` (a ``.o`` file's name
    or what ``qsub`` answered). The queue may cut a long name (spec 70, decision 7), so a name long
    enough to have been cut may be the start of the full one. Only with the job-ID also matching."""
    return listed == full or (len(listed) >= SHORTEST_CUT and full.startswith(listed))


def running_in(file_names: Iterable[str], snapshot: JobsSnapshot, user: str) -> tuple[Job, ...]:
    """The running jobs of ``user`` whose scheduler output ``<name>.o<job-ID>`` is among
    ``file_names`` (a folder's files): the only link the cluster gives between a job and the folder
    it was submitted from (spec 69 R2.2). The ID must match, and the name (``same_job_name``)."""
    outputs = [(m["name"], m["id"]) for name in file_names if (m := _STDOUT.match(name))]
    return tuple(
        job
        for job in snapshot.mine(user)
        if any(job_id == job.job_id and same_job_name(job.name, n) for n, job_id in outputs)
    )


def _job(tokens: list[str], running: bool, owner: str | None) -> Job | None:
    """The job of a line split on spaces; None when it is not one. ``owner``: the section's."""
    if len(tokens) < 5 or not _ID.match(tokens[0]) or not tokens[1].isdigit():
        return None
    rest = tokens[2:]
    queue = rest.pop() if running and not _TIME.match(rest[-1]) else None
    if len(rest) < 3 + (owner is None):  # name, date, time and the owner column
        return None
    clock, day = rest.pop(), rest.pop()
    if not _TIME.match(clock) or not _DATE.match(day):
        return None
    job_owner = owner if owner is not None else rest.pop()
    name = " ".join(rest)
    return Job(tokens[0], int(tokens[1]), name, job_owner, f"{day} {clock}", queue, running)


def parse_qstatus(
    text: str, command: str = "qstatus -a", fetched_at: float | None = None
) -> JobsSnapshot:
    """The jobs of a ``qstatus`` listing. An empty one, or one with titles only, has none; text with
    no title, header or job line in it raises ``ValueError``, and so does a line of a section that
    starts with a job-ID but cannot be read: a queue missing a job would let the guards through."""
    running: list[Job] = []
    waiting: list[Job] = []
    section: bool | None = None  # True: running jobs
    owner: str | None = None  # the user of a "… for user: <login>" section
    known = unknown = False
    unrecognized = _("Saída de {command} não reconhecida.").format(command=command)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if title := _TITLE.match(line):
            section, owner, known = title.group(1) == "Running", title.group(2), True
            continue
        if line.startswith("job-ID") or not line.strip("-"):
            known = True
            continue
        tokens = line.split()
        job = _job(tokens, section, owner) if section is not None else None
        if job is None:
            if section is not None and _ID.match(tokens[0]):
                log.warning("cluster: queue line not understood: %s", line)
                raise ValueError(unrecognized)
            unknown = True
            continue
        (running if job.running else waiting).append(job)
        known = True
    if unknown and not known:
        raise ValueError(unrecognized)
    when = time.time() if fetched_at is None else fetched_at
    return JobsSnapshot(tuple(running), tuple(waiting), when)


def classify(result: CommandResult, command: str) -> JobsSnapshot | RemoteFailure:
    """The jobs of a run of ``command``, or why there are none."""
    if result.code == 0 and not result.timed_out:
        if cause := _SCHEDULER_FAILED.search(result.stderr):
            message = _("{command} não conseguiu ler a fila: {cause}")
            return RemoteFailure(message.format(command=command, cause=cause.group().strip()))
        try:
            return parse_qstatus(result.stdout, command)
        except ValueError as exc:
            return RemoteFailure(str(exc))
    return classify_failure(result, command, SETTING)


def fetch_jobs(config: AppConfig, password: str | None = None) -> JobsSnapshot | RemoteFailure:
    """Run ``cluster.jobs_command`` on the cluster and read what it lists. ``password``: the one
    typed in this session (``auth: password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    command = cluster.jobs_command
    argv = remote_command(config, command)
    log.debug("command: %s", shlex.join(argv))
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        message = _("Não foi possível executar o ssh ({error}).").format(error=exc)
        return RemoteFailure(message, local=True)
    return classify(result, command)
