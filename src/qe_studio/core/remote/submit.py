"""Submitting a ``.qsub`` from the cluster mode (spec 69 R2, spec 71 R3): ``cd`` to its folder,
``chmod a+x`` and ``cluster.submit_command`` (``qsub``), never while a job of the user runs in that
folder or a job Lain submitted from it is still in the queue.

The only link the cluster gives between a job and a folder is the scheduler's output, ``<name>.o<id>``,
which ``#$ -cwd`` and ``#$ -j y`` put in the folder the job was submitted from when it starts. So
the folder is listed again (never the cache) and the queue asked again (``cluster.jobs_command``):
a running job of the user with its ``.o`` in the folder blocks the submission, and so does a queue
that could not be read. A job that still waits leaves nothing in the folder, but the ones Lain
submitted are in its log (``submit_log``): one of this folder still in the queue blocks too. All of
it is checked when the plan is made and again right before ``qsub``: a job may have started while
the confirmation was open.

A job of the user with the script's name (``#$ -N``), running or waiting anywhere, does not block:
the plan carries it and the user is asked first (spec 71 R3); one that shows up after that question
blocks. A forgotten ``<prefix>.EXIT`` (spec 70) is only reported: pw.x would stop at its first check.

Everything here blocks: it runs in a worker.
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass, replace

from ...i18n import _
from ..cluster_jobs import Job, JobsFailure, JobsSnapshot, fetch_jobs, running_in
from ..config import AppConfig
from .actions import (
    ActionFailure,
    checked_dir,
    checked_name,
    classify_failure,
    failure_of,
    failure_of_jobs,
    run_action,
)
from .inputs import fetch_job_name
from .listing import RemoteFailure, list_remote
from .submit_log import logged_here, read_log, record

log = logging.getLogger(__name__)

SETTING = "cluster.submit_command"
_SUBMITTED = re.compile(r'^Your job (\d+) \("(.*)"\) has been submitted', re.MULTILINE)


@dataclass(frozen=True)
class Submitted:
    job_id: str
    name: str
    log_error: str = ""  # why the job could not be written in the log of submitted jobs


@dataclass(frozen=True)
class SubmitBlocked:
    message: str


@dataclass(frozen=True)
class SubmitPlan:
    remote_dir: str
    script: str
    steps: tuple[str, ...]  # what runs on the cluster, in order (the dialog shows one per line)
    exit_files: tuple[str, ...]  # a forgotten EXIT in the folder: pw.x would stop at once
    job_name: str = ""  # what SGE will call the job: its ``#$ -N``, else the script's name
    same_name: tuple[Job, ...] = ()  # the user's jobs of that name, running or waiting

    @property
    def line(self) -> str:
        """The exact text that goes to ssh."""
        return " && ".join(self.steps)


@dataclass(frozen=True)
class FolderState:
    exit_files: tuple[str, ...]
    snapshot: JobsSnapshot  # the queue asked for the check


def account(config: AppConfig) -> str:
    return f"{config.cluster.user}@{config.cluster.host}"


def submit_steps(config: AppConfig, remote_dir: str, script: str) -> tuple[str, str, str]:
    """``cd``, ``chmod a+x`` and the submission; ``ValueError`` for a name or folder refused by
    ``core/remote/actions.py``."""
    folder = checked_dir(config, remote_dir)
    name = shlex.quote(checked_name(script))
    return (f"cd {folder}", f"chmod a+x {name}", f"{config.cluster.submit_command} {name}")


def parse_submitted(stdout: str) -> Submitted | None:
    """The job of ``Your job <id> ("<name>") has been submitted``, on any line; None otherwise."""
    match = _SUBMITTED.search(stdout)
    return Submitted(match.group(1), match.group(2)) if match else None


def same_name(snapshot: JobsSnapshot, user: str, name: str) -> tuple[Job, ...]:
    """The jobs of ``user`` called ``name``, running first, then waiting."""
    return tuple(job for job in (*snapshot.mine(user), *snapshot.queued(user)) if job.name == name)


def _logged_block(config: AppConfig, remote_dir: str, snapshot: JobsSnapshot) -> str:
    """Why a job Lain submitted from ``remote_dir`` blocks a new one; "" when none is in the queue."""
    user = config.cluster.user
    logged = logged_here(read_log(), account(config), remote_dir)
    for job in (*snapshot.mine(user), *snapshot.queued(user)):
        if (job.job_id, job.name) not in logged:
            continue
        if job.running:
            message = _(
                "O job {job_id} ({name}), que o Lain submeteu desta pasta, ainda está em execução. "
                "Espere ele terminar ou cancele-o antes de submeter outro script."
            )
        else:
            message = _(
                "O job {job_id} ({name}), que o Lain submeteu desta pasta, ainda está na fila. "
                "Espere ele terminar ou cancele-o pela fila antes de submeter outro script."
            )
        return message.format(job_id=job.job_id, name=job.name)
    return ""


def folder_check(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> FolderState | SubmitBlocked | ActionFailure:
    """The EXIT files of ``remote_dir``, listed again, and the queue, asked again, when no job of the
    user runs in the folder and none Lain submitted from it is in the queue."""
    listing = list_remote(config, remote_dir, password)
    if isinstance(listing, RemoteFailure):
        return failure_of(listing)
    jobs = fetch_jobs(config, password)
    if isinstance(jobs, JobsFailure):
        message = _(
            "Não foi possível conferir se já roda um job nesta pasta: {message}. Nada foi submetido."
        )
        return failure_of_jobs(jobs, message)
    names = [entry.name for entry in listing if not entry.is_dir]
    running = running_in(names, jobs, config.cluster.user)
    if running:
        message = _(
            "Já há um job seu em execução nesta pasta: {name} (job {job_id}). Espere ele terminar "
            "ou cancele-o antes de submeter outro script."
        )
        return SubmitBlocked(message.format(name=running[0].name, job_id=running[0].job_id))
    blocked = _logged_block(config, remote_dir, jobs)
    if blocked:
        return SubmitBlocked(blocked)
    exits = tuple(name for name in names if name == "EXIT" or name.endswith(".EXIT"))
    return FolderState(exits, jobs)


def plan_submit(
    config: AppConfig, remote_dir: str, script: str, password: str | None = None
) -> SubmitPlan | SubmitBlocked | ActionFailure:
    """What "Submeter…" will run, after the folder check and with the script's job name read;
    nothing runs that changes the cluster."""
    try:
        steps = submit_steps(config, remote_dir, script)
    except ValueError as exc:
        return ActionFailure(str(exc), local=True)
    checked = folder_check(config, remote_dir, password)
    if isinstance(checked, SubmitBlocked | ActionFailure):
        return checked
    name = fetch_job_name(config, remote_dir, script, password)
    if isinstance(name, ActionFailure):
        return name
    same = same_name(checked.snapshot, config.cluster.user, name)
    return SubmitPlan(remote_dir, script, steps, checked.exit_files, name, same)


def _logged(config: AppConfig, plan: SubmitPlan, submitted: Submitted) -> Submitted:
    """``submitted``, written in the log of submitted jobs; why it could not be, in ``log_error``."""
    try:
        record(account(config), submitted.job_id, submitted.name, plan.remote_dir, plan.script)
    except (OSError, ValueError) as exc:
        log.error("cannot log the submitted job %s: %s", submitted.job_id, exc)
        return replace(submitted, log_error=str(exc))
    return submitted


def submit(
    config: AppConfig, plan: SubmitPlan, password: str | None = None
) -> Submitted | str | SubmitBlocked | ActionFailure:
    """Check the folder again, then run ``plan.line``: the job (written in the log of submitted
    jobs), the first line of an answer that was not recognized (``qsub`` ended with code 0), or why
    nothing was submitted."""
    checked = folder_check(config, plan.remote_dir, password)
    if isinstance(checked, SubmitBlocked | ActionFailure):
        return checked
    known = {job.job_id for job in plan.same_name}
    for job in same_name(checked.snapshot, config.cluster.user, plan.job_name):
        if job.job_id not in known:
            message = _(
                "Um job seu chamado {name} apareceu no cluster depois da confirmação (job "
                "{job_id}): nada foi submetido."
            )
            return SubmitBlocked(message.format(name=job.name, job_id=job.job_id))
    result = run_action(config, plan.line, password)
    if isinstance(result, ActionFailure):
        return result
    if result.code != 0:
        return classify_failure(result, config.cluster.submit_command, SETTING)
    submitted = parse_submitted(result.stdout)
    if submitted is not None:
        return _logged(config, plan, submitted)
    return next((ln.strip() for ln in result.stdout.splitlines() if ln.strip()), "")
