"""The cluster's jobs (spec 64 R2): what ``cluster.jobs_command`` (``qstatus -a``) prints, read.

The format is the one of the ``qstatus`` script of the user's cluster (SGE underneath): sections
titled "Running jobs:" and "Waiting jobs:" ("… for user: <login>" without ``-a``, where the owner
column is left out), a header line, a line of dashes, then one job per line. A job line is read from
both ends: ``job-ID`` and ``#`` first; last the queue (running jobs only), the date and time and the
owner; what is left in the middle is the name, spaces and all. Dates stay as the cluster writes them,
in its time zone.

``fetch_jobs`` runs the command over ssh (``core/sync/command.py``) and blocks: it runs in a worker.
"""

from __future__ import annotations

import logging
import re
import shlex
import time
from collections.abc import Iterable
from dataclasses import dataclass

from ..i18n import _
from .config import AppConfig
from .sync.command import CommandResult, remote_command, run_command
from .sync.rsync import child_env, is_auth_failure, is_connection_failure, known_cause

log = logging.getLogger(__name__)

EXTRA_SECONDS = 30  # on top of ``cluster.connect_timeout``: what the command itself may take

_TITLE = re.compile(r"^(Running|Waiting) jobs(?: for user: (\S+))?:?$")
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_TIME = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_ID = re.compile(r"^\d+$")
_STDOUT = re.compile(r"^(?P<name>.+)\.o(?P<id>\d+)$")  # ``<name>.o<job-ID>``: ``#$ -j y`` output


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


def running_in(file_names: Iterable[str], snapshot: JobsSnapshot, user: str) -> tuple[Job, ...]:
    """The running jobs of ``user`` whose scheduler output ``<name>.o<job-ID>`` is among
    ``file_names`` (a folder's files): the only link the cluster gives between a job and the folder
    it was submitted from (spec 69 R2.2). The name and the ID must both match."""
    outputs = {(m["name"], m["id"]) for name in file_names if (m := _STDOUT.match(name))}
    return tuple(job for job in snapshot.mine(user) if (job.name, job.job_id) in outputs)


@dataclass(frozen=True)
class JobsFailure:
    message: str
    connection: bool = False  # the cluster was not reached, or stopped answering
    auth: bool = False  # it refused the login
    missing: bool = False  # the command does not exist there
    local: bool = False  # ssh itself could not be run


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
    no title, header or job line in it raises ``ValueError``."""
    running: list[Job] = []
    waiting: list[Job] = []
    section: bool | None = None  # True: running jobs
    owner: str | None = None  # the user of a "… for user: <login>" section
    known = unknown = False
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
        job = _job(line.split(), section, owner) if section is not None else None
        if job is None:
            unknown = True
            continue
        (running if job.running else waiting).append(job)
        known = True
    if unknown and not known:
        raise ValueError(_("Saída de {command} não reconhecida.").format(command=command))
    when = time.time() if fetched_at is None else fetched_at
    return JobsSnapshot(tuple(running), tuple(waiting), when)


def classify(result: CommandResult, command: str) -> JobsSnapshot | JobsFailure:
    """The jobs of a run of ``command``, or why there are none."""
    if result.timed_out:
        message = _("O cluster não respondeu a {command} a tempo.").format(command=command)
        return JobsFailure(message, connection=True)
    if result.code == 0:
        try:
            return parse_qstatus(result.stdout, command)
        except ValueError as exc:
            return JobsFailure(str(exc))
    stderr = result.stderr
    code = result.code if result.code is not None else -1
    if is_auth_failure(stderr):
        return JobsFailure(known_cause(stderr) or "", auth=True)
    if code == 127 or "command not found" in stderr:
        message = _("O comando {command} não foi encontrado no cluster (cluster.jobs_command).")
        return JobsFailure(message.format(command=command), missing=True)
    if is_connection_failure(code, stderr):
        fallback = _("Cluster inacessível (ssh terminou com código {code}).").format(code=code)
        return JobsFailure(known_cause(stderr) or fallback, connection=True)
    last = next((ln.strip() for ln in reversed(stderr.splitlines()) if ln.strip()), "")
    message = _("{command} terminou com código {code}").format(command=command, code=code)
    return JobsFailure(message + (f": {last}" if last else "."))


def fetch_jobs(config: AppConfig, password: str | None = None) -> JobsSnapshot | JobsFailure:
    """Run ``cluster.jobs_command`` on the cluster and read what it lists. ``password``: the one
    typed in this session (``auth: password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    command = cluster.jobs_command
    argv = remote_command(config, command)
    log.debug("jobs: %s", shlex.join(argv))
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        message = _("Não foi possível executar o ssh ({error}).").format(error=exc)
        return JobsFailure(message, local=True)
    return classify(result, command)
