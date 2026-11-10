"""rsync/ssh command lines, environments and output parsers (PRD §5).

rsync output is locale-dependent (pt_BR prints ``3.976.311`` and ``301,89MB/s``), so child
processes run with ``LC_ALL=C.UTF-8`` and ``TZ=UTC`` and sizes are requested with ``--no-h``.
Passwords never appear in argv: ssh reads them through ``SSH_ASKPASS`` from the child's
environment.
"""

from __future__ import annotations

import calendar
import os
import re
import shlex
import stat
import sys
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from ...i18n import _
from .. import cancel
from ..appdirs import atomic_write_text, cache_dir
from ..config import AppConfig, ClusterConfig
from ..project.project_data import PROJECT_DATA_EXCLUDE
from ..remote.scratch import SCRATCH_EXCLUDE
from ..remote.trash_dir import TRASH_EXCLUDE
from . import mux
from .askpass import SECRET_ENV
from .remote_path import Endpoint, local_arg, old_args, remote_arg, shell_path

OUT_FORMAT = "%i|%l|%M|%n"
DELIVERED = "sent|"  # how a transfer's stdout starts the name of each file that arrived

TIMEOUT_SECONDS = 60


def remote_dir_for(
    local_folder: Path, config: AppConfig, *, resolved_root: Path | None = None
) -> str:
    """Remote counterpart of ``local_folder`` (which must lie inside ``paths.local_root``).

    ``resolved_root`` is ``paths.local_root.resolve()`` when the caller already has it (resolving
    touches the disk: the window keeps it, spec 27-8 R3)."""
    root = resolved_root if resolved_root is not None else config.paths.local_root.resolve()
    return remote_dir_of(Path(local_folder).resolve(), root, config.paths.remote_root)


def remote_dir_of(folder: Path, root: Path, remote_root: str) -> str:
    """The remote path of ``folder`` under ``remote_root``; both local paths are already resolved."""
    try:
        relative = folder.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            _("{folder} não está dentro da pasta local configurada ({root})").format(
                folder=folder, root=root
            )
        ) from exc
    remote = PurePosixPath(remote_root)
    return str(remote.joinpath(*relative.parts)) if relative.parts else str(remote)


def ssh_command(cluster: ClusterConfig, ssh_binary: str) -> list[str]:
    """``ssh`` with the options Lain needs. ``StrictHostKeyChecking=yes`` is ours, not the user's
    ssh config: a ``-o`` on the command line wins over ``~/.ssh/config``, so an unknown or changed
    host key is always refused, whatever the config says for that host (spec 27-3 R1). The shared
    connection (``mux.options``, spec 72) comes last, and its master is born with them all."""
    argv = [
        *shlex.split(ssh_binary),
        "-p",
        str(cluster.port),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"ConnectTimeout={cluster.connect_timeout}",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
    ]
    if cluster.auth == "key":
        argv += ["-o", "BatchMode=yes"]
        if cluster.key_path:
            argv += ["-i", str(cluster.key_path), "-o", "IdentitiesOnly=yes"]
    else:
        argv += ["-o", "NumberOfPasswordPrompts=1"]
    return argv + mux.options(cluster)


def askpass_program() -> str:
    """Executable ssh runs to obtain the password (reads it from the child environment)."""
    if sys.platform == "win32":
        exe = Path(sys.executable).with_name("qe-studio-askpass.exe")
        scripts = Path(sys.executable).parent / "Scripts" / "qe-studio-askpass.exe"
        return str(exe if exe.exists() else scripts)
    wrapper = cache_dir() / "askpass.sh"
    content = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m qe_studio.core.sync.askpass "$@"\n'
    if not _wrapper_ready(wrapper, content):
        atomic_write_text(wrapper, content, mode=stat.S_IRWXU)
    return str(wrapper)


def _wrapper_ready(wrapper: Path, content: str) -> bool:
    """The askpass wrapper exists, says ``content`` and can run."""
    try:
        return wrapper.read_text(encoding="utf-8") == content and os.access(wrapper, os.X_OK)
    except (OSError, ValueError):
        return False


def child_env(
    cluster: ClusterConfig, base: dict[str, str] | None = None, password: str | None = None
) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.update(LC_ALL="C.UTF-8", LANG="C.UTF-8", TZ="UTC")
    env.pop(SECRET_ENV, None)
    if cluster.auth == "password":
        secret = password if password is not None else cluster.resolve_password()
        if secret:
            env[SECRET_ENV] = secret
            env["SSH_ASKPASS"] = askpass_program()
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env.setdefault("DISPLAY", ":0")  # some OpenSSH builds still check DISPLAY
    return env


@lru_cache(maxsize=4)
def version_command(rsync_binary: str = "rsync") -> list[str]:
    return [*shlex.split(rsync_binary), "--version"]


def parse_version(output: str) -> tuple[int, ...] | None:
    """``rsync --version`` output → (major, minor, patch), None if it is not rsync's."""
    match = re.search(r"version\s+v?(\d+)\.(\d+)\.(\d+)", output)
    return tuple(int(part) for part in match.groups()) if match else None


def _common(
    config: AppConfig,
    remote: Endpoint,
    version: tuple[int, ...] | None,
    timeout: int = TIMEOUT_SECONDS,
) -> list[str]:
    args = ["--no-h", f"--timeout={timeout}"]
    if old_args(remote, version):
        args.append("--old-args")  # ``remote_arg`` quotes the path for the cluster's shell
    if remote.host is not None:
        args += ["-e", shlex.join(ssh_command(config.cluster, config.sync.ssh_binary))]
    return args


def fixed_excludes(config: AppConfig, remote: Endpoint) -> list[str]:
    """What a pull or a push never lists, whatever the lists of ``config.yaml`` say: the root's
    settings folder (spec 48 R5) and the scratch copies of remote plots (spec 66 R2.2), at any
    depth, and the cluster's trash (spec 84), only in a transfer of ``paths.remote_root`` itself:
    elsewhere a folder named ``trash`` is the user's, and an item inside the trash is downloaded
    by its own path."""
    fixed = [PROJECT_DATA_EXCLUDE, SCRATCH_EXCLUDE]
    root = config.paths.remote_root
    if root and PurePosixPath(remote.path) == PurePosixPath(root):
        fixed.append(TRASH_EXCLUDE)
    return fixed


def dry_run_command(
    config: AppConfig,
    remote: Endpoint,
    local_dir: Path,
    version: tuple[int, ...] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """List files that differ (new, size, time or, with ``sync.checksum``, content) without
    transferring anything. ``fixed_excludes`` are never listed, whatever ``sync.exclude`` says.
    ``extra`` comes before ``sync.exclude`` because rsync's first match wins: a file the user asked
    for by name (``core/remote/download.py``) is downloaded even if that list covers it. With
    ``sync.checksum`` no ``--timeout``: nothing arrives while the cluster hashes a large file, and
    ssh's keepalive watches the connection."""
    fixed = [f"--exclude={pattern}" for pattern in fixed_excludes(config, remote)]
    excludes = [f"--exclude={pattern}" for pattern in config.sync.exclude]
    timeout = 0 if config.sync.checksum else TIMEOUT_SECONDS
    return [
        *shlex.split(config.sync.rsync_binary),
        "-n",
        "-rt",
        *(["--checksum"] if config.sync.checksum else []),
        "-i",
        "--modify-window=1",
        f"--out-format={OUT_FORMAT}",
        *_common(config, remote, version, timeout),
        *fixed,
        *(extra or []),
        *excludes,
        remote_arg(remote, version),
        local_arg(local_dir, config.sync.cygdrive_prefix),
    ]


def transfer_command(
    config: AppConfig,
    remote: Endpoint,
    local_dir: Path,
    version: tuple[int, ...] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Pull exactly the files listed on stdin (NUL separated, relative to the remote dir). With
    ``sync.checksum`` they are sent whatever their date and size say (``--ignore-times``): the
    plan found the content different, and rsync's quick check would skip a same-date, same-size
    file. Each file that arrives is named on stdout (``parse_delivered``)."""
    return [
        *shlex.split(config.sync.rsync_binary),
        "-t",
        *(["--ignore-times"] if config.sync.checksum else []),
        "--info=progress2",
        f"--out-format={DELIVERED}%n",
        "--files-from=-",
        "--from0",
        *_common(config, remote, version),
        *(extra or []),
        remote_arg(remote, version),
        local_arg(local_dir, config.sync.cygdrive_prefix),
    ]


def push_dry_run_command(
    config: AppConfig,
    remote: Endpoint,
    local_dir: Path,
    version: tuple[int, ...] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """List the local files missing or different on the cluster (spec 27 R1.1). No
    ``--ignore-existing``: files the cluster already has are listed too, so the preview says so."""
    patterns = [
        *fixed_excludes(config, remote),  # never sent
        *config.sync.exclude,
        *config.sync.push_exclude,
    ]
    return [
        *shlex.split(config.sync.rsync_binary),
        "-n",
        "-rt",
        "-i",
        "--modify-window=1",
        f"--out-format={OUT_FORMAT}",
        *_common(config, remote, version),
        *(f"--exclude={pattern}" for pattern in patterns),
        *(extra or []),
        local_arg(local_dir, config.sync.cygdrive_prefix),
        remote_arg(remote, version),
    ]


def push_transfer_command(
    config: AppConfig,
    remote: Endpoint,
    local_dir: Path,
    version: tuple[int, ...] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Send exactly the files listed on stdin, never touching what the cluster has (spec 27 R1.2):
    ``--ignore-existing`` skips a file created there since the preview, ``--omit-dir-times``
    leaves the dates of its folders alone, and there is no ``--delete``, ``--update`` or
    ``--inplace``. A new calculation folder (and its missing parents) is made by the remote
    ``mkdir -p`` (R1.3: ``--mkpath`` needs rsync 3.2.3 on the cluster); its path comes from the
    config, never from a file."""
    mkdir = []
    if remote.host is not None:  # local copies ignore --rsync-path
        mkdir = [f"--rsync-path=mkdir -p {shell_path(remote.path)} && rsync"]
    return [
        *shlex.split(config.sync.rsync_binary),
        "-t",
        "--info=progress2",
        f"--out-format={DELIVERED}%n",
        "--files-from=-",
        "--from0",
        "--ignore-existing",
        "--omit-dir-times",
        *_common(config, remote, version),
        *mkdir,
        *(extra or []),
        local_arg(local_dir, config.sync.cygdrive_prefix),
        remote_arg(remote, version),
    ]


def list_command(
    config: AppConfig, remote_dir: str, version: tuple[int, ...] | None = None
) -> list[str]:
    """List one folder of the cluster, its subfolders not (spec 65 R1): a line per entry,
    ``permissions size YYYY/MM/DD HH:MM:SS name``, and ``.`` for the folder itself. Its path may
    hold names read from the cluster, quoted for its shell: ``version`` (the local rsync's) says
    how to send them (``core/sync/remote_path.py``)."""
    cluster = config.cluster
    remote = Endpoint(remote_dir, cluster.host, cluster.user)
    return [
        *shlex.split(config.sync.rsync_binary),
        "--list-only",
        *_common(config, remote, version),
        remote_arg(remote, version),
    ]


def outputs_command(
    config: AppConfig, remote_dir: str, version: tuple[int, ...] | None = None
) -> list[str]:
    """List the scheduler outputs (``<name>.o<job-ID>``) anywhere below one folder of the cluster
    (spec 84: a folder about to go to the trash): its subfolders too, every other file filtered
    out by the sender, and the folders left with none pruned. A line is the one of
    ``list_command``, the name a path relative to ``remote_dir``. ``version`` as in
    ``list_command``. No ``--timeout``: the walk may say nothing for long; ``list_outputs``' deadline
    and ssh's keepalive watch it."""
    cluster = config.cluster
    remote = Endpoint(remote_dir, cluster.host, cluster.user)
    return [
        *shlex.split(config.sync.rsync_binary),
        "--list-only",
        "-r",
        "--prune-empty-dirs",
        "--include=*/",
        "--include=*.o[0-9]*",
        "--exclude=*",
        *_common(config, remote, version, timeout=0),
        remote_arg(remote, version),
    ]


def small_files_command(
    config: AppConfig,
    remote_dir: str,
    dest: Path,
    version: tuple[int, ...] | None = None,
    only: str | None = None,
    skip: Sequence[str] = (),
) -> list[str]:
    """Copy the files at the top of one folder of the cluster, up to 1 MB each, into ``dest``; no
    subfolder (spec 70 R1: the inputs a cancellation reads the ``prefix`` from). ``only``: just that
    file, a name without wildcards (spec 71 R3: the script a submission reads the job name from).
    ``skip``: patterns of files not worth copying. ``version`` as in ``list_command``."""
    cluster = config.cluster
    remote = Endpoint(remote_dir, cluster.host, cluster.user)
    return [
        *shlex.split(config.sync.rsync_binary),
        "-r",
        "--max-size=1M",
        "--exclude=*/",
        *(f"--exclude={pattern}" for pattern in skip),
        *([f"--include={only}", "--exclude=*"] if only is not None else []),
        *_common(config, remote, version),
        remote_arg(remote, version),
        local_arg(dest, config.sync.cygdrive_prefix),
    ]


@dataclass(frozen=True)
class DryRunItem:
    code: str
    size: int
    mtime: float  # epoch seconds (rsync ran with TZ=UTC)
    path: str  # relative to the synced folder

    @property
    def is_file(self) -> bool:
        return self.code.startswith((">f", "<f", "cf"))  # received, sent (push), created


_ESCAPE = re.compile(rb"\\#([0-7]{3})")


def decode_rsync_name(text: str) -> str:
    """Undo rsync's ``\\#ooo`` escaping of non-printable bytes. A name that is not UTF-8 keeps its
    bytes as surrogates, so it still names the same file on the disk and on rsync's stdin."""
    raw = text.encode("utf-8", "surrogateescape")
    raw = _ESCAPE.sub(lambda m: bytes([int(m.group(1), 8)]), raw)
    return raw.decode("utf-8", "surrogateescape")


def parse_itemize_line(line: str) -> DryRunItem | None:
    parts = line.rstrip("\r\n").split("|", 3)
    if len(parts) != 4 or len(parts[0]) < 2:
        return None
    code, size, mtime, name = parts
    try:
        epoch = calendar.timegm(time.strptime(mtime.strip(), "%Y/%m/%d-%H:%M:%S"))
        return DryRunItem(code.strip(), int(size), float(epoch), decode_rsync_name(name))
    except ValueError:
        return None


def parse_dry_run(output: str) -> list[DryRunItem]:
    items = (parse_itemize_line(line) for line in cancel.checked(output.splitlines()))
    return [item for item in items if item is not None and item.is_file]


def parse_delivered(output: str, files: Collection[str]) -> list[str]:
    """Which of ``files`` a transfer's stdout says arrived, in that order. Others it may name (a
    folder it created) are left out."""
    wanted = set(files)
    lines = (line for line in re.split(r"[\r\n]+", output) if line.startswith(DELIVERED))
    names = (decode_rsync_name(line.removeprefix(DELIVERED)) for line in lines)
    return [name for name in dict.fromkeys(names) if name in wanted]


_PERCENT = re.compile(r"(?<!\S)(\d{1,3})%(?=\s|$)")  # a word of its own: names can hold a ``%``
_TO_CHECK = re.compile(r"to-chk=(\d+)/(\d+)")
_XFER = re.compile(r"xfr#(\d+)")


@dataclass(frozen=True)
class Progress:
    percent: int
    files_done: int | None = None
    files_total: int | None = None


def parse_progress(chunk: str) -> Progress | None:
    """Last progress2 update in ``chunk`` (lines are separated by ``\\r``)."""
    for line in reversed(re.split(r"[\r\n]+", chunk)):
        percent = None if line.startswith(DELIVERED) else _PERCENT.search(line)
        if not percent:
            continue
        check = _TO_CHECK.search(line)
        done = total = None
        if check:
            remaining, total = int(check.group(1)), int(check.group(2))
            done = total - remaining
        elif xfer := _XFER.search(line):
            done = int(xfer.group(1))
        return Progress(min(int(percent.group(1)), 100), done, total)
    return None
