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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from ...i18n import _
from ..appdirs import cache_dir
from ..config import AppConfig, ClusterConfig
from ..project_data import PROJECT_DATA_EXCLUDE
from ..scratch import SCRATCH_EXCLUDE
from .askpass import SECRET_ENV

OUT_FORMAT = "%i|%l|%M|%n"

TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Endpoint:
    """Remote side of a sync. ``host=None`` means a local path (used by tests)."""

    path: str
    host: str | None = None
    user: str | None = None

    def spec(self) -> str:
        path = self.path.rstrip("/") + "/"
        if self.host is None:
            return path
        login = f"{self.user}@{self.host}" if self.user else self.host
        return f"{login}:{path}"


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
    host key is always refused, whatever the config says for that host (spec 27-3 R1)."""
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
    return argv


def askpass_program() -> str:
    """Executable ssh runs to obtain the password (reads it from the child environment)."""
    if sys.platform == "win32":
        exe = Path(sys.executable).with_name("qe-studio-askpass.exe")
        scripts = Path(sys.executable).parent / "Scripts" / "qe-studio-askpass.exe"
        return str(exe if exe.exists() else scripts)
    wrapper = cache_dir() / "askpass.sh"
    content = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m qe_studio.core.sync.askpass "$@"\n'
    if not wrapper.exists() or wrapper.read_text() != content:
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(content)
        wrapper.chmod(stat.S_IRWXU)
    return str(wrapper)


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
    match = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)", output)
    return tuple(int(part) for part in match.groups()) if match else None


def _common(config: AppConfig, remote: Endpoint, version: tuple[int, ...] | None) -> list[str]:
    args = ["--no-h", f"--timeout={TIMEOUT_SECONDS}"]
    if version is not None and version < (3, 2, 4):
        args.append("--protect-args")  # newer clients protect remote args by default
    if remote.host is not None:
        args += ["-e", shlex.join(ssh_command(config.cluster, config.sync.ssh_binary))]
    return args


def dry_run_command(
    config: AppConfig,
    remote: Endpoint,
    local_dir: Path,
    version: tuple[int, ...] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """List files that differ (new, size, time or, with ``sync.checksum``, content) without
    transferring anything. The root's settings folder (spec 48 R5) and the scratch copies of remote
    plots (spec 66 R2.2) are never listed, whatever ``sync.exclude`` says."""
    fixed = [PROJECT_DATA_EXCLUDE, SCRATCH_EXCLUDE]
    excludes = [f"--exclude={pattern}" for pattern in [*fixed, *config.sync.exclude]]
    return [
        *shlex.split(config.sync.rsync_binary),
        "-n",
        "-rt",
        *(["--checksum"] if config.sync.checksum else []),
        "-i",
        "--modify-window=1",
        f"--out-format={OUT_FORMAT}",
        *_common(config, remote, version),
        *excludes,
        *(extra or []),
        remote.spec(),
        str(local_dir).rstrip("/\\") + "/",
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
    file."""
    return [
        *shlex.split(config.sync.rsync_binary),
        "-t",
        *(["--ignore-times"] if config.sync.checksum else []),
        "--info=progress2",
        "--files-from=-",
        "--from0",
        *_common(config, remote, version),
        *(extra or []),
        remote.spec(),
        str(local_dir).rstrip("/\\") + "/",
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
    fixed = [PROJECT_DATA_EXCLUDE, SCRATCH_EXCLUDE]  # never sent: see ``dry_run_command``
    patterns = [*fixed, *config.sync.exclude, *config.sync.push_exclude]
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
        str(local_dir).rstrip("/\\") + "/",
        remote.spec(),
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
        mkdir = [f"--rsync-path=mkdir -p {shlex.quote(remote.path)} && rsync"]
    return [
        *shlex.split(config.sync.rsync_binary),
        "-t",
        "--info=progress2",
        "--files-from=-",
        "--from0",
        "--ignore-existing",
        "--omit-dir-times",
        *_common(config, remote, version),
        *mkdir,
        *(extra or []),
        str(local_dir).rstrip("/\\") + "/",
        remote.spec(),
    ]


def list_command(
    config: AppConfig, remote_dir: str, version: tuple[int, ...] | None = None
) -> list[str]:
    """List one folder of the cluster, its subfolders not (spec 65 R1): a line per entry,
    ``permissions size YYYY/MM/DD HH:MM:SS name``, and ``.`` for the folder itself. Its path may
    hold names read from the cluster: ``version`` (the local rsync's) adds ``--protect-args`` on
    the clients that do not protect remote arguments by themselves."""
    cluster = config.cluster
    remote = Endpoint(remote_dir, cluster.host, cluster.user)
    return [
        *shlex.split(config.sync.rsync_binary),
        "--list-only",
        *_common(config, remote, version),
        remote.spec(),
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
    """Undo rsync's ``\\#ooo`` escaping of non-printable bytes."""
    raw = text.encode("utf-8", "surrogateescape")
    raw = _ESCAPE.sub(lambda m: bytes([int(m.group(1), 8)]), raw)
    return raw.decode("utf-8", "replace")


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
    items = (parse_itemize_line(line) for line in output.splitlines())
    return [item for item in items if item is not None and item.is_file]


_PERCENT = re.compile(r"(\d{1,3})%")
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
        percent = _PERCENT.search(line)
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


AUTH_DENIED = "Permission denied"

FAILURE_HINTS = (
    ("Host key verification failed", _("Chave do host desconhecida. Conecte-se uma vez pelo "
     "terminal (ssh usuario@host) para confirmar a identidade do cluster.")),
    (AUTH_DENIED, _("Autenticação recusada pelo cluster (verifique usuário, chave ou senha).")),
    ("Could not resolve hostname", _("Endereço do cluster não encontrado (verifique cluster.host).")),
    ("Connection timed out", _("Cluster inacessível (tempo de conexão esgotado).")),
    ("Connection refused", _("Conexão recusada pelo cluster (verifique a porta SSH).")),
    ("No route to host", _("Cluster inacessível (sem rota; verifique a rede/VPN).")),
    ("Network is unreachable", _("Rede indisponível.")),
    ("No such file or directory", _("Pasta não encontrada no cluster.")),
    ("timeout in data send/receive", _("Conexão interrompida (sem resposta do cluster).")),
    ("command not found", _("rsync não está instalado no cluster.")),
)  # fmt: skip


# rsync's last words when the stream ends early. It also trails real causes (host key refused,
# authentication, rsync missing on the cluster), so it only counts when nothing explains the failure.
INTERRUPTED = "connection unexpectedly closed"

CONNECTION_NEEDLES = (
    "Connection timed out",
    "Connection refused",
    "No route to host",
    "Network is unreachable",
    "Could not resolve hostname",
    "timeout in data send/receive",
    "Connection closed",
)


def _first_cause(stderr: str) -> tuple[str, str] | None:
    """The first known cause (its needle and hint) found in ``stderr``."""
    return next(((needle, hint) for needle, hint in FAILURE_HINTS if needle in stderr), None)


def known_cause(stderr: str) -> str | None:
    """The explanation of the first known cause found in ``stderr`` (ssh's, or rsync's), if any."""
    cause = _first_cause(stderr)
    return cause[1] if cause is not None else None


def is_auth_failure(stderr: str) -> bool:
    """The cluster refused the credentials (the remembered password is then wrong): the first known
    cause in ``stderr`` is the authentication one."""
    cause = _first_cause(stderr)
    return cause is not None and cause[0] == AUTH_DENIED


def is_connection_failure(exit_code: int, stderr: str) -> bool:
    """ssh could not reach/keep the cluster (as opposed to a remote error)."""
    return (
        any(needle in stderr for needle in CONNECTION_NEEDLES)
        or (exit_code == 255 and AUTH_DENIED not in stderr)
        or (INTERRUPTED in stderr and _first_cause(stderr) is None)
    )


def explain_failure(exit_code: int, stderr: str) -> str:
    if cause := _first_cause(stderr):
        return cause[1]
    if INTERRUPTED in stderr:
        return _("Conexão interrompida (o cluster encerrou a conexão durante a transferência).")
    last = next((ln.strip() for ln in reversed(stderr.splitlines()) if ln.strip()), "")
    return _("rsync terminou com código {exit_code}").format(exit_code=exit_code) + (
        f": {last}" if last else "."
    )
