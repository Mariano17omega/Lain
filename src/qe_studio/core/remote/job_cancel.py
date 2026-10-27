"""Cancelling a job (spec 70 R2): ``<prefix>.EXIT`` for one that runs, ``qdel`` for one that waits.

The method is never chosen: it comes from where the user clicked, and a fresh ``qstatus`` decides
right before acting (never the cache of the queue popup).

- A **running** job is matched to a folder by its scheduler output ``<name>.o<id>`` (the only link
  the cluster gives, ``running_in``) and stopped by creating ``<prefix>.EXIT`` there, one per
  ``prefix`` of the folder's SCF, relax and vc-relax inputs of pw.x (the cluster administrator's
  rule, spec 71 R2): pw.x stops cleanly at its next check and deletes the file. A later pw.x of the
  script with the same ``prefix`` still runs; one with another of these prefixes stops at its first
  check. ``qdel`` is never used on it: the process would go on running out of the queue.
- A **waiting** job is cancelled with ``cluster.delete_command`` (``qdel``) and its ID, only while the
  ID is still in "Waiting jobs", with the same name and owner, and not in "Running jobs". A job that
  waits has no ``.o`` and no folder in the listing: the ID is what tells apart jobs of the same
  name. Between that query and ``qdel`` there is the time of one login, which SGE gives no way to
  close (no "delete only if still waiting").

Everything here blocks: it runs in a worker.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

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
from .inputs import StopSource, fetch_stop_sources
from .listing import RemoteFailure, list_remote

SETTING = "cluster.delete_command"
TOUCH = "touch"
_ID = re.compile(r"^\d+$")


@dataclass(frozen=True)
class StopPlan:
    remote_dir: str
    jobs: tuple[Job, ...]  # the user's jobs running in the folder
    sources: tuple[StopSource, ...]  # a prefix of the folder's SCF/relax/vc-relax inputs, each
    line: str  # the exact text that goes to ssh

    @property
    def prefixes(self) -> tuple[str, ...]:
        return tuple(source.prefix for source in self.sources)

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(f"{prefix}.EXIT" for prefix in self.prefixes)


@dataclass(frozen=True)
class NotRunning:
    message: str


@dataclass(frozen=True)
class Done:
    message: str


@dataclass(frozen=True)
class Refused:
    message: str


def _queue(config: AppConfig, password: str | None) -> JobsSnapshot | ActionFailure:
    """The queue, asked again; without it nothing runs."""
    jobs = fetch_jobs(config, password)
    if isinstance(jobs, JobsFailure):
        message = _(
            "Não foi possível conferir o estado do job no cluster: {message}. Nada foi feito."
        )
        return failure_of_jobs(jobs, message)
    return jobs


# -- a running job: the stop file ------------------------------------------------------------------
def exit_line(config: AppConfig, remote_dir: str, prefixes: tuple[str, ...]) -> str:
    """``touch`` and one quoted ``<remote_dir>/<prefix>.EXIT`` per prefix; ``ValueError`` for a
    folder or a prefix refused by ``core/remote/actions.py``."""
    folder = checked_dir(config, remote_dir)
    paths = [f"{folder}/{shlex.quote(checked_name(f'{prefix}.EXIT'))}" for prefix in prefixes]
    return " ".join([TOUCH, *paths])


def plan_stop(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> StopPlan | NotRunning | ActionFailure:
    """What "Cancelar simulação…" will run in ``remote_dir``: the folder listed and the queue asked
    again, then the inputs read. Nothing runs that changes the cluster."""
    try:
        checked_dir(config, remote_dir)
    except ValueError as exc:
        return ActionFailure(str(exc), local=True)
    listing = list_remote(config, remote_dir, password)
    if isinstance(listing, RemoteFailure):
        return failure_of(listing)
    snapshot = _queue(config, password)
    if isinstance(snapshot, ActionFailure):
        return snapshot
    names = [entry.name for entry in listing if not entry.is_dir]
    jobs = running_in(names, snapshot, config.cluster.user)
    if not jobs:
        return NotRunning(
            _(
                "Nenhum job seu em execução nesta pasta: nenhum arquivo <nome>.o<id> corresponde a "
                "um job em execução no qstatus. Um job na fila se cancela pela fila do cluster, na "
                "barra superior."
            )
        )
    sources = fetch_stop_sources(config, remote_dir, password)
    if isinstance(sources, ActionFailure):
        return sources
    if not sources:
        return NotRunning(
            _(
                "Nenhum input de scf, relax ou vc-relax do pw.x (até 1 MB) nesta pasta: o arquivo "
                "de parada usa o prefix de um deles."
            )
        )
    prefixes = tuple(source.prefix for source in sources)
    return StopPlan(remote_dir, jobs, sources, exit_line(config, remote_dir, prefixes))


def stop(
    config: AppConfig, plan: StopPlan, password: str | None = None
) -> Done | Refused | ActionFailure:
    """Create the stop files of ``plan`` when one of its jobs still runs, after a fresh queue."""
    snapshot = _queue(config, password)
    if isinstance(snapshot, ActionFailure):
        return snapshot
    running = {(job.job_id, job.name) for job in snapshot.mine(config.cluster.user)}
    if not any((job.job_id, job.name) in running for job in plan.jobs):
        message = _("O job {job_id} não está mais em execução: nada foi criado.")
        return Refused(message.format(job_id=plan.jobs[0].job_id))
    result = run_action(config, plan.line, password)
    if isinstance(result, ActionFailure):
        return result
    if result.code != 0:
        return classify_failure(result, TOUCH)
    message = _("Pedido de parada criado: {files}. O pw.x para na próxima verificação.")
    return Done(message.format(files=", ".join(plan.files)))


# -- a waiting job: qdel ---------------------------------------------------------------------------
def delete_line(config: AppConfig, job: Job) -> str:
    """``cluster.delete_command`` and the job's ID; ``ValueError`` for an ID that is not a number."""
    if not _ID.fullmatch(job.job_id):
        raise ValueError(_("ID de job não suportado: {job_id}.").format(job_id=job.job_id))
    return f"{config.cluster.delete_command} {job.job_id}"


def waiting_check(snapshot: JobsSnapshot, job: Job, user: str) -> Job | Refused:
    """The job of ``snapshot`` that ``job`` (a row of an older listing) still is, when it waits and
    is ``user``'s; why not otherwise. Compared by ID: names repeat."""
    if any(other.job_id == job.job_id for other in snapshot.running):
        message = _(
            "O job {job_id} começou a rodar: o qdel não é usado em jobs em execução. Cancele pela "
            "pasta dele, no modo cluster (Cancelar simulação…)."
        )
        return Refused(message.format(job_id=job.job_id))
    same = [other for other in snapshot.waiting if other.job_id == job.job_id]
    if not same:
        message = _("O job {job_id} não está mais na fila: nada foi feito.")
        return Refused(message.format(job_id=job.job_id))
    if any(other.name != job.name or other.owner != user for other in same):
        message = _("O job {job_id} da fila não é mais {name}: nada foi feito.")
        return Refused(message.format(job_id=job.job_id, name=job.name))
    return same[0]


def delete_waiting(
    config: AppConfig, job: Job, password: str | None = None
) -> Done | Refused | ActionFailure:
    """``qdel`` ``job`` when a fresh queue shows it still waiting; why nothing ran otherwise."""
    try:
        line = delete_line(config, job)
    except ValueError as exc:
        return ActionFailure(str(exc), local=True)
    snapshot = _queue(config, password)
    if isinstance(snapshot, ActionFailure):
        return snapshot
    checked = waiting_check(snapshot, job, config.cluster.user)
    if isinstance(checked, Refused):
        return checked
    result = run_action(config, line, password)
    if isinstance(result, ActionFailure):
        return result
    if result.code != 0:
        return classify_failure(result, config.cluster.delete_command, SETTING)
    message = _("Job {job_id} ({name}) cancelado com qdel.")
    return Done(message.format(job_id=checked.job_id, name=checked.name))
