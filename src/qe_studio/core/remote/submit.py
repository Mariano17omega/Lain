"""Submitting a ``.qsub`` from the cluster mode (spec 69 R2): ``cd`` to its folder, ``chmod a+x`` and
``cluster.submit_command`` (``qsub``), never while a job of the user runs in that folder.

The only link the cluster gives between a job and a folder is the scheduler's output, ``<name>.o<id>``,
which ``#$ -cwd`` and ``#$ -j y`` put in the folder the job was submitted from when it starts. So
the folder is listed again (never the cache) and the queue asked again (``cluster.jobs_command``):
a running job of the user with its ``.o`` in the folder blocks the submission, and so does a queue
that could not be read. Both are checked when the plan is made and again right before ``qsub``: a
job may have started while the confirmation was open. A forgotten ``<prefix>.EXIT`` (spec 70) is
only reported: pw.x would stop at its first check.

Everything here blocks: it runs in a worker.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from ...i18n import _
from ..cluster_jobs import JobsFailure, fetch_jobs, running_in
from ..config import AppConfig
from .actions import ActionFailure, checked_dir, checked_name, classify_failure, run_action
from .listing import RemoteFailure, list_remote

SETTING = "cluster.submit_command"
_SUBMITTED = re.compile(r'^Your job (\d+) \("(.*)"\) has been submitted', re.MULTILINE)


@dataclass(frozen=True)
class Submitted:
    job_id: str
    name: str


@dataclass(frozen=True)
class SubmitBlocked:
    message: str


@dataclass(frozen=True)
class SubmitPlan:
    remote_dir: str
    script: str
    steps: tuple[str, ...]  # what runs on the cluster, in order (the dialog shows one per line)
    exit_files: tuple[str, ...]  # a forgotten EXIT in the folder: pw.x would stop at once

    @property
    def line(self) -> str:
        """The exact text that goes to ssh."""
        return " && ".join(self.steps)


def submit_steps(config: AppConfig, remote_dir: str, script: str) -> tuple[str, str, str]:
    """``cd``, ``chmod a+x`` and the submission; ``ValueError`` for a name or folder refused by
    ``core/remote/actions.py``."""
    folder = checked_dir(config, remote_dir)
    name = shlex.quote(checked_name(script))
    return (f"cd {folder}", f"chmod a+x {name}", f"{config.cluster.submit_command} {name}")


def submit_line(config: AppConfig, remote_dir: str, script: str) -> str:
    return " && ".join(submit_steps(config, remote_dir, script))


def parse_submitted(stdout: str) -> Submitted | None:
    """The job of ``Your job <id> ("<name>") has been submitted``, on any line; None otherwise."""
    match = _SUBMITTED.search(stdout)
    return Submitted(match.group(1), match.group(2)) if match else None


def folder_check(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> tuple[str, ...] | SubmitBlocked | ActionFailure:
    """The EXIT files of ``remote_dir``, listed again, when no job of the user runs in it."""
    listing = list_remote(config, remote_dir, password)
    if isinstance(listing, RemoteFailure):
        return ActionFailure(
            listing.message, listing.connection, listing.auth, listing.missing, listing.local
        )
    jobs = fetch_jobs(config, password)
    if isinstance(jobs, JobsFailure):
        message = _(
            "Não foi possível conferir se já roda um job nesta pasta: {message}. Nada foi submetido."
        )
        return SubmitBlocked(message.format(message=jobs.message.rstrip(".")))
    names = [entry.name for entry in listing if not entry.is_dir]
    running = running_in(names, jobs, config.cluster.user)
    if running:
        message = _(
            "Já há um job seu em execução nesta pasta: {name} (job {job_id}). Espere ele terminar "
            "ou cancele-o antes de submeter outro script."
        )
        return SubmitBlocked(message.format(name=running[0].name, job_id=running[0].job_id))
    return tuple(name for name in names if name == "EXIT" or name.endswith(".EXIT"))


def plan_submit(
    config: AppConfig, remote_dir: str, script: str, password: str | None = None
) -> SubmitPlan | SubmitBlocked | ActionFailure:
    """What "Submeter…" will run, after the folder check; nothing runs that changes the cluster."""
    try:
        steps = submit_steps(config, remote_dir, script)
    except ValueError as exc:
        return ActionFailure(str(exc), local=True)
    checked = folder_check(config, remote_dir, password)
    if isinstance(checked, SubmitBlocked | ActionFailure):
        return checked
    return SubmitPlan(remote_dir, script, steps, checked)


def submit(
    config: AppConfig, plan: SubmitPlan, password: str | None = None
) -> Submitted | str | SubmitBlocked | ActionFailure:
    """Check the folder again, then run ``plan.line``: the job, the first line of an answer that
    was not recognized (``qsub`` ended with code 0), or why nothing was submitted."""
    checked = folder_check(config, plan.remote_dir, password)
    if isinstance(checked, SubmitBlocked | ActionFailure):
        return checked
    result = run_action(config, plan.line, password)
    if isinstance(result, ActionFailure):
        return result
    if result.code != 0:
        return classify_failure(result, config.cluster.submit_command, SETTING)
    submitted = parse_submitted(result.stdout)
    if submitted is not None:
        return submitted
    return next((ln.strip() for ln in result.stdout.splitlines() if ln.strip()), "")
