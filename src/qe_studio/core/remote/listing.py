"""One folder of the cluster, listed (spec 65 R1): ``rsync --list-only`` over ssh, read.

rsync runs with ``LC_ALL=C.UTF-8``, ``TZ=UTC`` and ``--no-h`` (``child_env``, ``list_command``): a line
is ``permissions size YYYY/MM/DD HH:MM:SS name``, the size without separators, the time in UTC and
the name as it is, spaces and all (non-printable bytes as ``\\#ooo``); ``.`` is the folder itself and
a link is ``name -> target``. Hidden names (a leading dot) and the folders ``ui.hidden_dirs`` hides
are left out, as in the local panels.

``list_remote`` runs it (``core/sync/command.py``) and blocks: it runs in a worker.
"""

from __future__ import annotations

import calendar
import logging
import re
import shlex
import time
from collections.abc import Iterable
from dataclasses import dataclass

from ...i18n import _
from ..config import AppConfig
from ..paths import is_hidden, natural_key, normalize_patterns
from ..sync.command import CommandResult, run_command
from ..sync.rsync import (
    AUTH_DENIED,
    child_env,
    decode_rsync_name,
    explain_failure,
    is_auth_failure,
    is_connection_failure,
    list_command,
    parse_version,
    version_command,
)

log = logging.getLogger(__name__)

EXTRA_SECONDS = 30  # on top of ``cluster.connect_timeout``: what the listing itself may take
VERSION_SECONDS = 10
SSH_FAILED = 255  # rsync's code when the remote shell failed (a refused login among others)
PARTIAL = 23  # rsync's code when the source could not be read
RSYNC_MISSING = _("rsync não encontrado (sync.rsync_binary).")
NOT_FOUND = _("Pasta não encontrada no cluster.")
NO_ACCESS = _("Sem permissão para ler esta pasta no cluster.")
TIMED_OUT = _("O cluster não respondeu a tempo.")

_LINE = re.compile(r"^(\S+)\s+(\d+)\s+(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) (.*)$")
_versions: dict[str, tuple[int, ...]] = {}  # the local rsync's, by ``sync.rsync_binary``


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    is_dir: bool
    size: int
    mtime: float  # epoch seconds
    link: bool = False  # a symbolic link: never entered (``is_dir`` is false)


@dataclass(frozen=True)
class RemoteFailure:
    message: str
    connection: bool = False  # the cluster was not reached, or stopped answering
    auth: bool = False  # it refused the login
    missing: bool = False  # the folder does not exist there
    local: bool = False  # rsync could not be run here


def sort_entries(entries: Iterable[RemoteEntry], by: str = "name") -> list[RemoteEntry]:
    """Folders first, then ``by``: ``"name"`` in natural order (``run2`` before ``run10``);
    ``"size"`` the largest file first (folders stay by name); ``"date"`` the newest first. Equal
    keys go by name, so the order is the same whatever order ``entries`` came in."""

    def key(entry: RemoteEntry) -> tuple:
        name = natural_key(entry.name)
        if by == "date":
            return (not entry.is_dir, -entry.mtime, name)
        if by == "size" and not entry.is_dir:
            return (True, -entry.size, name)
        return (not entry.is_dir, 0, name)

    return sorted(entries, key=key)


def parse_listing(stdout: str, hidden_dirs: list[str]) -> list[RemoteEntry]:
    """The entries of a ``list_command`` output, sorted; lines of any other shape are skipped."""
    patterns = normalize_patterns(hidden_dirs)
    entries = []
    for line in stdout.splitlines():
        match = _LINE.match(line)
        if match is None:
            continue
        mode, size, when, raw = match.groups()
        link = mode.startswith("l")
        if link:
            raw = raw.split(" -> ", 1)[0]
        name = decode_rsync_name(raw)
        is_dir = mode.startswith("d")
        if not name or name.startswith(".") or "/" in name:
            continue
        if is_dir and is_hidden(name, patterns):
            continue
        mtime = float(calendar.timegm(time.strptime(when, "%Y/%m/%d %H:%M:%S")))
        entries.append(RemoteEntry(name, is_dir, int(size), mtime, link))
    return sort_entries(entries)


def classify(result: CommandResult, hidden_dirs: list[str]) -> list[RemoteEntry] | RemoteFailure:
    """The entries of a run of ``list_command``, or why there are none. A refused login is ssh's
    (rsync's code 255); a "Permission denied" with code 23 is a folder the user cannot read, which
    says nothing about the password."""
    if result.timed_out:
        return RemoteFailure(TIMED_OUT, connection=True)
    if result.code == 0:
        return parse_listing(result.stdout, hidden_dirs)
    stderr = result.stderr
    code = result.code if result.code is not None else -1
    if code == SSH_FAILED and is_auth_failure(stderr):
        return RemoteFailure(explain_failure(code, stderr), auth=True)
    if code == PARTIAL and "No such file or directory" in stderr:
        return RemoteFailure(NOT_FOUND, missing=True)
    if code == PARTIAL and AUTH_DENIED in stderr:
        return RemoteFailure(NO_ACCESS)
    if is_connection_failure(code, stderr):
        return RemoteFailure(explain_failure(code, stderr), connection=True)
    return RemoteFailure(explain_failure(code, stderr))


def local_version(rsync_binary: str, env: dict[str, str]) -> tuple[int, ...] | None:
    """The local rsync's version, asked once per binary in the session; None when it cannot run."""
    known = _versions.get(rsync_binary)
    if known is not None:
        return known
    result = run_command(version_command(rsync_binary), env, VERSION_SECONDS)
    version = parse_version(result.stdout) if result.code == 0 else None
    if version is not None:
        _versions[rsync_binary] = version
    return version


def list_remote(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> list[RemoteEntry] | RemoteFailure:
    """List ``remote_dir`` on the cluster. ``password``: the one typed in this session (``auth:
    password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        version = local_version(config.sync.rsync_binary, env)
        if version is None:
            return RemoteFailure(RSYNC_MISSING, local=True)
        argv = list_command(config, remote_dir, version)
        log.debug("remote: %s", shlex.join(argv))
        result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        message = _("Não foi possível executar o rsync ({error}).").format(error=exc)
        return RemoteFailure(message, local=True)
    return classify(result, config.ui.hidden_dirs)
