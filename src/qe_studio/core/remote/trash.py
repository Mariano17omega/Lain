"""Deleting in the cluster mode (spec 84): "Apagar…" moves files and folders into the trash,
``<remote_root>/trash/<path>/<name>_<date>`` (``core/remote/trash_dir.py``), and never deletes anything.

The command is one line of fixed words, run from the root: ``cd <remote_root> && mkdir -p <the targets'
folder> && test ! -e <target> && mv <item> <target>``, a ``test`` and a ``mv`` per item, with paths relative
to the root and every part passed by ``checked_name`` and ``shlex.quote`` (``core/remote/actions.py``).
``test ! -e`` keeps anything from being overwritten (and an item from going *into* a folder of the same
name, which is what ``mv`` would do), and the first step that fails stops the others. The date is the
local time of Lain's machine, fixed when the plan is made: the dialog shows the command that runs.

A job of the user moved along would go on writing in the trash, or lose its ``outdir``. So the folder of
the items is listed again and the queue asked (``cluster.jobs_command``): a running job with its
``<name>.o<id>`` there blocks, and so does one with its output anywhere in a deleted folder, its
subfolders included (``list_outputs``, asked only while a job of the user runs: a subfolder it cannot
read blocks too, since that job could be in it), and a job Lain
submitted from the folder of the items, or from a deleted folder or below it, still in the queue (its
log, spec 71). It is all checked when the plan is made and again right before ``mv``, as "Submeter…"
does.

Everything here blocks: it runs in a worker.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from ...i18n import _
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
from .cluster_jobs import Job, JobsFailure, JobsSnapshot, fetch_jobs, running_in
from .listing import RemoteEntry, RemoteFailure, list_outputs, list_remote
from .submit import account
from .submit_log import logged_here, logged_under, read_log
from .trash_dir import TRASH_DIR, in_trash

STAMP = "%Y-%m-%d_%H-%M-%S"
MOVE = "mv"
NOTHING = _("Selecione um item para apagar.")
ROOT = _("A pasta raiz do cluster (paths.remote_root) não vai para a lixeira.")
IN_TRASH = _("Já está na lixeira: para apagar de vez, use o terminal no cluster.")
ONE_FOLDER = _("Selecione itens de uma pasta só para apagar.")

Item = tuple[str, bool]  # (path on the cluster, is a folder): the cluster mode's ``RemotePath``
Move = tuple[str, str]  # (item, target), relative to ``paths.remote_root``


@dataclass(frozen=True)
class TrashPlan:
    remote_dir: str  # the folder of the items
    items: tuple[Item, ...]
    moves: tuple[Move, ...]
    steps: tuple[str, ...]  # what runs on the cluster, in order (the dialog shows one per line)

    @property
    def line(self) -> str:
        """The exact text that goes to ssh."""
        return " && ".join(self.steps)


@dataclass(frozen=True)
class TrashBlocked:
    message: str


@dataclass(frozen=True)
class TrashDone:
    moved: tuple[Move, ...]  # what left its folder
    failure: ActionFailure | None = None  # the step that stopped the others, when one did


# -- the names -------------------------------------------------------------------------------------
def stamped(name: str, is_dir: bool, now: datetime) -> str:
    """``name`` with the date: at the end of a folder's or of a file without extension, before the
    last extension of a file (``a.tar.gz`` → ``a.tar_<date>.gz``)."""
    stamp = now.strftime(STAMP)
    path = PurePosixPath(name)
    if is_dir or not path.suffix:
        return f"{name}_{stamp}"
    return f"{path.stem}_{stamp}{path.suffix}"


def trash_target(remote_root: str, item_path: str, is_dir: bool, now: datetime) -> str:
    """Where ``item_path`` goes, relative to ``remote_root``: its path below the root, inside
    ``trash/``, with the date in the name (``projeto/PDOS`` → ``trash/projeto/PDOS_<date>``)."""
    relative = PurePosixPath(item_path).relative_to(remote_root)
    name = stamped(relative.name, is_dir, now)
    return str(PurePosixPath(TRASH_DIR, *relative.parent.parts, name))


def trash_moves(remote_root: str, items: Sequence[Item], now: datetime) -> tuple[Move, ...]:
    """(item, target) of each item, relative to ``remote_root``."""
    return tuple(
        (
            str(PurePosixPath(path).relative_to(remote_root)),
            trash_target(remote_root, path, is_dir, now),
        )
        for path, is_dir in items
    )


def trash_blocked(config: AppConfig, items: Sequence[Item]) -> str:
    """Why ``items`` cannot go to the trash; "" when they can: the root, what is already in the
    trash, a path outside ``paths.remote_root`` or with a name ``checked_name`` refuses, and items of
    different folders (the grid shows one folder; the tree selects one)."""
    if not items:
        return NOTHING
    root = config.paths.remote_root
    for path, _is_dir in items:
        if root and PurePosixPath(path) == PurePosixPath(root):
            return ROOT
        if in_trash(root, path):
            return IN_TRASH
        try:
            checked_dir(config, path)
        except ValueError as exc:
            return str(exc)
    if len({PurePosixPath(path).parent for path, _is_dir in items}) > 1:
        return ONE_FOLDER
    return ""


# -- the command -----------------------------------------------------------------------------------
def _word(relative: str) -> str:
    """A path relative to the root as one shell word: every part checked and quoted."""
    return "/".join(shlex.quote(checked_name(part)) for part in PurePosixPath(relative).parts)


def trash_steps(config: AppConfig, items: Sequence[Item], now: datetime) -> tuple[str, ...]:
    """``cd`` to the root, ``mkdir -p`` of the targets' folder, then ``test ! -e`` and ``mv`` per
    item; ``ValueError`` for items ``trash_blocked`` refuses."""
    if reason := trash_blocked(config, items):
        raise ValueError(reason)
    root = config.paths.remote_root
    moves = trash_moves(root, items, now)
    folders = dict.fromkeys(str(PurePosixPath(target).parent) for _item, target in moves)
    steps = [f"cd {checked_dir(config, root)}", "mkdir -p " + " ".join(map(_word, folders))]
    for item, target in moves:
        steps += [f"test ! -e {_word(target)}", f"{MOVE} {_word(item)} {_word(target)}"]
    return tuple(steps)


def trash_command(config: AppConfig, items: Sequence[Item], now: datetime) -> str:
    """The exact text that goes to ssh (``trash_steps`` joined by ``&&``)."""
    return " && ".join(trash_steps(config, items, now))


# -- the checks on the cluster ---------------------------------------------------------------------
def _shown(config: AppConfig, folder: str) -> str:
    """``folder`` as the messages name it: relative to the root (the root and a folder outside it
    as they are)."""
    root = config.paths.remote_root
    path = PurePosixPath(folder)
    if not root or not path.is_relative_to(root) or path == PurePosixPath(root):
        return folder
    return str(path.relative_to(root))


def _runs_in(config: AppConfig, folder: str, job: Job) -> TrashBlocked:
    message = _("Há um job seu em execução em {folder} ({job_id}): cancele-o antes de apagar.")
    return TrashBlocked(message.format(folder=_shown(config, folder), job_id=job.job_id))


def _running(
    config: AppConfig, folder: str, entries: list[RemoteEntry], jobs: JobsSnapshot
) -> TrashBlocked | None:
    """Why a running job of the user with its ``<name>.o<id>`` among ``entries`` (``folder``'s)
    blocks; None when there is none."""
    names = [entry.name for entry in entries if not entry.is_dir]
    running = running_in(names, jobs, config.cluster.user)
    return _runs_in(config, folder, running[0]) if running else None


def _running_below(
    config: AppConfig, folder: str, jobs: JobsSnapshot, password: str | None
) -> TrashBlocked | ActionFailure | None:
    """Why a running job of the user with its ``<name>.o<id>`` anywhere in ``folder`` (a folder
    deleted, its subfolders included) blocks, or a subfolder that could not be read, where one could
    be; None when there is none. A job found in what could be read comes first: it says more."""
    outputs = list_outputs(config, folder, password)
    if isinstance(outputs, RemoteFailure):
        return failure_of(outputs)
    for relative in map(PurePosixPath, outputs.found):
        running = running_in([relative.name], jobs, config.cluster.user)
        if running:
            return _runs_in(config, str(PurePosixPath(folder) / relative.parent), running[0])
    if outputs.unread:
        message = _(
            "Não foi possível ler {folder} no cluster, e há um job seu em execução: sem saber se ele "
            "roda lá, nada foi movido."
        )
        return TrashBlocked(message.format(folder=_shown(config, outputs.unread[0])))
    return None


def _logged(
    config: AppConfig, remote_dir: str, items: Sequence[Item], jobs: JobsSnapshot
) -> TrashBlocked | None:
    """Why a job Lain submitted from ``remote_dir``, or from a deleted folder or below it, still in
    the queue blocks; None when there is none."""
    entries, who, user = read_log(), account(config), config.cluster.user
    folders = {key: remote_dir for key in logged_here(entries, who, remote_dir)}
    for path, is_dir in items:
        if is_dir:
            folders.update(
                {(e.job_id, e.name): e.remote_dir for e in logged_under(entries, who, path)}
            )
    for job in (*jobs.mine(user), *jobs.queued(user)):
        folder = folders.get((job.job_id, job.name))
        if folder is None:
            continue
        if job.running:
            message = _(
                "O job {job_id} ({name}), que o Lain submeteu de {folder}, está em execução: "
                "cancele-o antes de apagar."
            )
        else:
            message = _(
                "O job {job_id} ({name}), que o Lain submeteu de {folder}, ainda está na fila: "
                "cancele-o pela fila antes de apagar."
            )
        shown = _shown(config, folder)
        return TrashBlocked(message.format(job_id=job.job_id, name=job.name, folder=shown))
    return None


def trash_check(
    config: AppConfig, remote_dir: str, items: Sequence[Item], password: str | None = None
) -> TrashBlocked | ActionFailure | None:
    """Why nothing may move now (an item no longer there, the queue unreadable, a job of the user in
    the folder of the items or anywhere in a deleted folder); None when nothing blocks."""
    listing = list_remote(config, remote_dir, password)
    if isinstance(listing, RemoteFailure):
        return failure_of(listing)
    present = {(entry.name, entry.is_dir) for entry in listing}
    for path, is_dir in items:
        name = PurePosixPath(path).name
        if (name, is_dir) not in present:
            message = _("{name} não está mais nesta pasta do cluster: nada foi movido.")
            return TrashBlocked(message.format(name=name))
    jobs = fetch_jobs(config, password)
    if isinstance(jobs, JobsFailure):
        message = _("Não foi possível conferir se roda um job aqui: {message}. Nada foi movido.")
        return failure_of_jobs(jobs, message)
    # The folder of the items and the log first: they need no other login.
    blocked = _running(config, remote_dir, listing, jobs) or _logged(
        config, remote_dir, items, jobs
    )
    if blocked is not None or not jobs.mine(config.cluster.user):
        return blocked  # with no job of the user running, nothing below can be one
    for path, is_dir in items:
        if is_dir and (blocked := _running_below(config, path, jobs, password)) is not None:
            return blocked
    return None


# -- planning and moving ---------------------------------------------------------------------------
def plan_trash(
    config: AppConfig,
    items: Sequence[Item],
    password: str | None = None,
    now: datetime | None = None,
) -> TrashPlan | TrashBlocked | ActionFailure:
    """What "Apagar…" will run for ``items`` (of one folder), after ``trash_check``; nothing runs
    that changes the cluster. ``now``: the date of the names (the local time by default)."""
    plain = tuple((path, bool(is_dir)) for path, is_dir in items)
    if reason := trash_blocked(config, plain):
        return TrashBlocked(reason)
    when = now or datetime.now()
    try:
        steps = trash_steps(config, plain, when)
    except ValueError as exc:
        return ActionFailure(str(exc), local=True)
    remote_dir = str(PurePosixPath(plain[0][0]).parent)
    checked = trash_check(config, remote_dir, plain, password)
    if checked is not None:
        return checked
    moves = trash_moves(config.paths.remote_root, plain, when)
    return TrashPlan(remote_dir, plain, moves, steps)


def _exists(config: AppConfig, target: str, password: str | None) -> bool:
    """``target`` (relative to the root) is listed in its folder of the trash."""
    path = PurePosixPath(config.paths.remote_root, target)
    listing = list_remote(config, str(path.parent), password)
    return not isinstance(listing, RemoteFailure) and any(e.name == path.name for e in listing)


def run_trash(
    config: AppConfig, plan: TrashPlan, password: str | None = None
) -> TrashDone | TrashBlocked | ActionFailure:
    """Check again, then run ``plan.line``: what moved, and the step that stopped the others (the
    folder is listed again to tell); why nothing moved otherwise."""
    checked = trash_check(config, plan.remote_dir, plan.items, password)
    if checked is not None:
        return checked
    result = run_action(config, plan.line, password)
    if isinstance(result, ActionFailure):
        return result
    if result.code == 0:
        return TrashDone(plan.moves)
    failure = classify_failure(result, MOVE)
    listing = list_remote(config, plan.remote_dir, password)
    if isinstance(listing, RemoteFailure):
        return failure
    left = {entry.name for entry in listing}
    moved = tuple(move for move in plan.moves if PurePosixPath(move[0]).name not in left)
    stuck = next((move for move in plan.moves if move not in moved), None)
    if stuck is not None and _exists(config, stuck[1], password):
        message = _("Já existe {target} no cluster: nada foi sobrescrito.")
        failure = ActionFailure(message.format(target=stuck[1]))
    return TrashDone(moved, failure) if moved else failure
