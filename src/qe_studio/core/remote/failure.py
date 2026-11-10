"""How something on the cluster failed: one type for a listing, the queue and an action, and one
reading of what a command run over ssh answered (``core/sync/command.py``)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from ...i18n import _
from ..sync.command import CommandResult
from ..sync.rsync_errors import (
    SSH_FAILED,
    is_auth_failure,
    is_connection_failure,
    known_cause,
    not_found,
)

EXTRA_SECONDS = 30  # on top of ``cluster.connect_timeout``: what the command itself may take


@dataclass(frozen=True)
class RemoteFailure:
    message: str
    connection: bool = False  # the cluster was not reached, or stopped answering
    auth: bool = False  # it refused the login
    missing: bool = False  # the folder or the command does not exist there
    local: bool = False  # ssh or rsync could not be run here, or nothing was sent

    @property
    def answered(self) -> bool:
        """The cluster was reached and took the login: it is the command that failed."""
        return not (self.connection or self.auth or self.local)


def explained(failure: RemoteFailure, message: str) -> RemoteFailure:
    """``failure`` (a queue that could not be read) as the failure of the action that needed it,
    which nothing ran: ``message`` gets the original one as ``{message}`` (spec 71 R4)."""
    return replace(failure, message=message.format(message=failure.message.rstrip(".")))


def classify_failure(
    result: CommandResult, command: str, setting: str | None = None, others: Iterable[str] = ()
) -> RemoteFailure:
    """Why a run of ``command`` (the program of ``setting`` in ``config.yaml``; None for a fixed
    word such as ``touch``) did not succeed. ``others``: the fixed words that ran before it in the
    same ``&&`` line, which the cluster's last words may name instead."""
    if result.timed_out:
        message = _("O cluster não respondeu a {command} a tempo.").format(command=command)
        return RemoteFailure(message, connection=True)
    stderr = result.stderr
    code = result.code if result.code is not None else -1
    if is_auth_failure(code, stderr):
        return RemoteFailure(known_cause(stderr) or "", auth=True)
    earlier = tuple(others)
    program = PurePosixPath(command.split()[0]).name if command.strip() else command
    absent = not_found(stderr, (program, *earlier))
    if code == 127 or absent:
        name = absent if absent in earlier else command
        if setting is None or name != command:
            message = _("O comando {command} não foi encontrado no cluster.")
        else:
            message = _("O comando {command} não foi encontrado no cluster ({setting}).")
        return RemoteFailure(message.format(command=name, setting=setting), missing=True)
    if is_connection_failure(code, stderr):
        fallback = _("Cluster inacessível (ssh terminou com código {code}).").format(code=code)
        return RemoteFailure(known_cause(stderr) or fallback, connection=True)
    if code == SSH_FAILED and (cause := known_cause(stderr)):  # ssh refused the host key
        return RemoteFailure(cause)
    last = next((ln.strip() for ln in reversed(stderr.splitlines()) if ln.strip()), "")
    words = re.split(r"[:\s]+", last)
    step = next((word for word in earlier if word in words), command)
    message = _("{command} terminou com código {code}").format(command=step, code=code)
    return RemoteFailure(message + (f": {last}" if last else "."))
