"""Commands that change the cluster (spec 69 R1): what they may contain, how they run, how they fail.

A command is built from a program named in ``config.yaml`` (``cluster.submit_command``) and fixed
words (``cd``, ``chmod a+x``); a value read from the cluster (a file or folder name) enters only as an
argument, after ``checked_name`` and ``shlex.quote``. Names with spaces or shell characters are
refused even though they would be quoted: the cluster's login shell may not be ``bash``. The
``paths.remote_root`` of ``config.yaml`` is the user's own and is only quoted.

``run_action`` runs the command over ssh (``core/sync/command.py``) and blocks: it runs in a worker,
and only after the user confirmed it.
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

from ...i18n import _
from ..cluster_jobs import JobsFailure
from ..config import AppConfig
from ..sync.command import CommandResult, remote_command, run_command
from ..sync.rsync import child_env, is_auth_failure, is_connection_failure, known_cause
from .listing import SSH_FAILED, RemoteFailure

log = logging.getLogger(__name__)

EXTRA_SECONDS = 30  # on top of ``cluster.connect_timeout``: what the command itself may take
SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class ActionFailure:
    message: str
    connection: bool = False  # the cluster was not reached, or stopped answering
    auth: bool = False  # it refused the login
    missing: bool = False  # the command (or the folder) does not exist there
    local: bool = False  # ssh itself could not be run, or nothing was sent


def failure_of(listing: RemoteFailure) -> ActionFailure:
    """A listing (or a copy) of the cluster that failed, as the failure of the action it serves."""
    return ActionFailure(
        listing.message, listing.connection, listing.auth, listing.missing, listing.local
    )


def failure_of_jobs(jobs: JobsFailure, message: str) -> ActionFailure:
    """A queue that could not be read (``cluster.jobs_command``) as the failure of the action that
    needed it, which nothing ran: ``message`` gets the queue's own as ``{message}`` (spec 71 R4)."""
    text = message.format(message=jobs.message.rstrip("."))
    return ActionFailure(text, jobs.connection, jobs.auth, jobs.missing, jobs.local)


def checked_name(name: str) -> str:
    """``name`` (one file or folder name read from the cluster) when it may enter a command."""
    if not SAFE_NAME.fullmatch(name):
        message = _(
            "Nome não suportado para um comando no cluster: {name} (use letras, números, '.', '_', "
            "'+' e '-')."
        )
        raise ValueError(message.format(name=name))
    return name


def checked_dir(config: AppConfig, remote_dir: str) -> str:
    """``remote_dir`` as one shell word, quoted: ``paths.remote_root`` (only quoted) and, below it,
    names that pass ``checked_name``. ``ValueError`` for a folder outside ``remote_root``."""
    root = config.paths.remote_root
    path = PurePosixPath(remote_dir)
    if not root or not path.is_relative_to(root):
        message = _("A pasta {folder} não está em paths.remote_root ({root}).")
        raise ValueError(message.format(folder=remote_dir, root=root))
    parts = path.relative_to(root).parts
    return shlex.quote(root) + "".join("/" + shlex.quote(checked_name(part)) for part in parts)


def classify_failure(
    result: CommandResult, command: str, setting: str | None = None
) -> ActionFailure:
    """Why a run of ``command`` (the program of ``setting`` in ``config.yaml``; None for a fixed
    word such as ``touch``) did not succeed."""
    if result.timed_out:
        message = _("O cluster não respondeu a {command} a tempo.").format(command=command)
        return ActionFailure(message, connection=True)
    stderr = result.stderr
    code = result.code if result.code is not None else -1
    # ssh's own code: a command that fails on the cluster may also say "Permission denied".
    if code == SSH_FAILED and is_auth_failure(stderr):
        return ActionFailure(known_cause(stderr) or "", auth=True)
    if code == 127 or "command not found" in stderr:
        if setting is None:
            message = _("O comando {command} não foi encontrado no cluster.")
        else:
            message = _("O comando {command} não foi encontrado no cluster ({setting}).")
        return ActionFailure(message.format(command=command, setting=setting), missing=True)
    if is_connection_failure(code, stderr):
        fallback = _("Cluster inacessível (ssh terminou com código {code}).").format(code=code)
        return ActionFailure(known_cause(stderr) or fallback, connection=True)
    last = next((ln.strip() for ln in reversed(stderr.splitlines()) if ln.strip()), "")
    message = _("{command} terminou com código {code}").format(command=command, code=code)
    return ActionFailure(message + (f": {last}" if last else "."))


def run_action(
    config: AppConfig, command: str, password: str | None = None
) -> CommandResult | ActionFailure:
    """Run ``command`` on the cluster. ``password``: the one typed in this session (``auth:
    password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    argv = remote_command(config, command)
    log.info("cluster action: %s", shlex.join(argv))
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        return run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        message = _("Não foi possível executar o ssh ({error}).").format(error=exc)
        return ActionFailure(message, local=True)
