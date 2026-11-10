"""One folder of the cluster, listed (spec 65 R1): ``rsync --list-only`` over ssh, read.

rsync runs with ``LC_ALL=C.UTF-8``, ``TZ=UTC`` and ``--no-h`` (``child_env``, ``list_command``): a line
is ``permissions size YYYY/MM/DD HH:MM:SS name``, the size without separators, the time in UTC and
the name as it is, spaces and all (non-printable bytes as ``\\#ooo``); ``.`` is the folder itself and
a link is ``name -> target``. Hidden names (a leading dot) and the folders ``ui.hidden_dirs`` hides
are left out, as in the local panels.

``list_remote`` runs it (``core/sync/command.py``) and blocks: it runs in a worker. ``list_outputs`` is
the same for the scheduler outputs below a folder, its subfolders included (spec 84): it reads a whole
tree, so it has much longer, and a subfolder it could not read does not throw away what it read.
"""

from __future__ import annotations

import calendar
import logging
import re
import shlex
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ...i18n import _
from ..config import AppConfig
from ..files.paths import is_hidden, natural_key, normalize_patterns
from ..sync.command import CommandResult, run_command
from ..sync.rsync import (
    child_env,
    decode_rsync_name,
    list_command,
    outputs_command,
    parse_version,
    version_command,
)
from ..sync.rsync_errors import (
    AUTH_DENIED,
    PARTIAL,
    VANISHED,
    explain_failure,
    is_auth_failure,
    is_connection_failure,
    unread_paths,
)
from .failure import EXTRA_SECONDS, RemoteFailure

log = logging.getLogger(__name__)

OUTPUTS_SECONDS = 300  # the same for a whole tree; a dead connection is ssh's keepalive, code 255
VERSION_SECONDS = 10
NOT_FOUND = _("Pasta não encontrada no cluster.")
NO_ACCESS = _("Sem permissão para ler esta pasta no cluster.")
TIMED_OUT = _("O cluster não respondeu a tempo.")
TOO_LONG = _("A pasta é grande demais para conferir a tempo se roda um job nas subpastas.")

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
class Outputs:
    """What ``list_outputs`` found below a folder."""

    found: list[str]  # the scheduler outputs that could be read, relative to the folder
    unread: tuple[str, ...] = ()  # the folders below it that could not be, as rsync names them


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


def parse_outputs(stdout: str) -> list[str]:
    """The files of an ``outputs_command`` output, as paths relative to the folder listed; folders
    and lines of any other shape are skipped."""
    found = []
    for line in stdout.splitlines():
        match = _LINE.match(line)
        if match is not None and match.group(1).startswith("-"):
            found.append(decode_rsync_name(match.group(4)))
    return found


def _read_the_folder(stdout: str) -> bool:
    """Whether a listing reached the folder itself: it prints its ``.`` line first, whatever matches."""
    matches = map(_LINE.match, stdout.splitlines())
    return any(match is not None and match.group(4) == "." for match in matches)


def classify(result: CommandResult, hidden_dirs: list[str]) -> list[RemoteEntry] | RemoteFailure:
    """The entries of a run of ``list_command``, or why there are none. A file that vanished while
    it ran (code 24, normal where pw.x runs) is just not listed, once the folder itself was read."""
    if result.code == VANISHED and _read_the_folder(result.stdout):
        return parse_listing(result.stdout, hidden_dirs)
    failure = failed(result)
    return parse_listing(result.stdout, hidden_dirs) if failure is None else failure


def failed(result: CommandResult) -> RemoteFailure | None:
    """Why a run of a listing gave nothing; None when it succeeded. A refused login is ssh's
    (rsync's code 255); a "Permission denied" with code 23 is a folder the user cannot read, which
    says nothing about the password."""
    if result.timed_out:
        return RemoteFailure(TIMED_OUT, connection=True)
    if result.code == 0:
        return None
    stderr = result.stderr
    code = result.code if result.code is not None else -1
    if is_auth_failure(code, stderr):
        return RemoteFailure(explain_failure(code, stderr), auth=True)
    if code == PARTIAL and "No such file or directory" in stderr:
        return RemoteFailure(NOT_FOUND, missing=True)
    if code == PARTIAL and AUTH_DENIED in stderr:
        return RemoteFailure(NO_ACCESS)
    if is_connection_failure(code, stderr):
        return RemoteFailure(explain_failure(code, stderr), connection=True)
    return RemoteFailure(explain_failure(code, stderr))


def local_version(rsync_binary: str, env: dict[str, str]) -> tuple[int, ...] | None:
    """The local rsync's version, asked once per binary in the session. None when its banner does
    not say one: every command takes that as a new client (``core/sync/remote_path.py``). ``OSError``
    when it cannot be run or does not answer."""
    known = _versions.get(rsync_binary)
    if known is not None:
        return known
    result = run_command(version_command(rsync_binary), env, VERSION_SECONDS)
    if result.timed_out or result.code != 0:
        raise OSError(_("--version não respondeu"))
    version = parse_version(result.stdout)
    if version is not None:
        _versions[rsync_binary] = version
    return version


def _run(
    config: AppConfig,
    build: Callable[[tuple[int, ...] | None], list[str]],
    password: str | None,
    seconds: int = EXTRA_SECONDS,
) -> CommandResult | RemoteFailure:
    """Run the rsync command ``build`` makes for the local rsync's version; ``seconds``: what it may
    take, on top of ``cluster.connect_timeout``."""
    cluster = config.cluster
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        argv = build(local_version(config.sync.rsync_binary, env))
        log.debug("command: %s", shlex.join(argv))
        return run_command(argv, env, cluster.connect_timeout + seconds)
    except OSError as exc:
        message = _("Não foi possível executar o rsync ({error}).").format(error=exc)
        return RemoteFailure(message, local=True)


def list_remote(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> list[RemoteEntry] | RemoteFailure:
    """List ``remote_dir`` on the cluster. ``password``: the one typed in this session (``auth:
    password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    result = _run(config, lambda version: list_command(config, remote_dir, version), password)
    if isinstance(result, RemoteFailure):
        return result
    return classify(result, config.ui.hidden_dirs)


def _unread(result: CommandResult) -> tuple[str, ...] | None:
    """The folders a partial listing could not read; one that vanished during the walk is not among
    them, since no job runs in it. None when what arrived cannot be used: the folder itself was not
    read, nothing says what failed, or a failure could not be understood."""
    if not _read_the_folder(result.stdout):
        return None
    return unread_paths(result.code, result.stderr)


def list_outputs(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> Outputs | RemoteFailure:
    """The scheduler outputs (``<name>.o<job-ID>``) anywhere below ``remote_dir``, as paths
    relative to it, hidden folders included, and the folders below it that could not be read.
    ``password`` as in ``list_remote``. Running out of time says nothing about the connection."""
    result = _run(
        config,
        lambda version: outputs_command(config, remote_dir, version),
        password,
        OUTPUTS_SECONDS,
    )
    if isinstance(result, RemoteFailure):
        return result
    if result.timed_out:
        return RemoteFailure(TOO_LONG)
    unread = () if result.code == 0 else _unread(result)
    if unread is None:
        failure = failed(result)
        assert failure is not None  # the code is not 0
        return failure
    return Outputs(parse_outputs(result.stdout), unread)
