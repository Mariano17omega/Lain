"""Commands that change the cluster (spec 69 R1): what they may contain, how they run, how they fail.

A command is built from a program named in ``config.yaml`` (``cluster.submit_command``) and fixed
words (``cd``, ``chmod a+x``); a value read from the cluster (a file or folder name) enters only as an
argument, after ``checked_name`` and ``shlex.quote``. Names with spaces or shell characters are
refused even though they would be quoted: the cluster's login shell may not be ``bash``. The
``paths.remote_root`` of ``config.yaml`` is the user's own and is only quoted, but for a leading ``~``
or ``~user``, left for the shell to expand as rsync leaves it (``core/sync/remote_path.py``).

``run_action`` runs the command over ssh (``core/sync/command.py``) and blocks: it runs in a worker,
and only after the user confirmed it.
"""

from __future__ import annotations

import logging
import re
import shlex
from pathlib import PurePosixPath

from ...i18n import _
from ..config import AppConfig
from ..sync.command import CommandResult, remote_command, run_command, tail
from ..sync.remote_path import shell_path
from ..sync.rsync import child_env
from .failure import EXTRA_SECONDS, RemoteFailure

log = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._+-]*$")


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
    """``remote_dir`` as one shell word: ``paths.remote_root`` (``shell_path``: quoted, a leading ``~``
    left to the shell) and, below it, quoted names that pass ``checked_name``. ``ValueError`` for a
    folder outside ``remote_root``."""
    root = config.paths.remote_root
    path = PurePosixPath(remote_dir)
    if not root or not path.is_relative_to(root):
        message = _("A pasta {folder} não está em paths.remote_root ({root}).")
        raise ValueError(message.format(folder=remote_dir, root=root))
    parts = path.relative_to(root).parts
    return shell_path(root) + "".join("/" + shlex.quote(checked_name(part)) for part in parts)


def run_action(
    config: AppConfig, command: str, password: str | None = None
) -> CommandResult | RemoteFailure:
    """Run ``command`` on the cluster. ``password``: the one typed in this session (``auth:
    password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    argv = remote_command(config, command)
    log.info("cluster: action %s", shlex.join(argv))
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        message = _("Não foi possível executar o ssh ({error}).").format(error=exc)
        return RemoteFailure(message, local=True)
    # What the cluster answered: the job ID of a ``qsub`` is only here.
    outcome = "timeout" if result.timed_out else result.code
    log.info("cluster: action -> %s: %s", outcome, tail(result.stdout))
    return result
