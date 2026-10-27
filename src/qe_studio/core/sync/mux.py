"""One ssh connection for many commands (spec 72): OpenSSH's ``ControlMaster``.

The first ssh to the cluster becomes a master that logs in and keeps the connection; the next ones
(``qstatus``, the listing, ``qsub``, the sync's rsync…) open a session through its socket, without
a login of their own, until ``PERSIST_SECONDS`` pass with no client. ``ssh_command`` adds
``options`` to every ssh Lain runs; ``cluster.multiplex: false`` turns it off. A session the
cluster refuses (its ``MaxSessions``) makes ssh log in by itself, as without a master.

The sockets live in ``control_dir()``: a folder of the user's own, ``0700``, short enough for the
path of a Unix socket (104 bytes on BSD/macOS). Each Lain process has its own masters (their
sockets start with its pid): closing the window stops them (``close_all``, the "ssh" step of
``ui/shutdown.py``) and never another Lain's; one left by a killed Lain ends by itself.

With ``auth: password`` the master is born from the environment of the first ssh, askpass secret
included, and keeps it while it lives: up to ``PERSIST_SECONDS`` after the last command, less when
Lain closes. Only the user and root can read it, as with the ssh of a long rsync: an accepted risk
(spec 72, review of 27/10/2026).
"""

from __future__ import annotations

import logging
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from functools import cache
from pathlib import Path

from ..config import ClusterConfig

log = logging.getLogger(__name__)

PERSIST_SECONDS = 120  # what the master waits for another client (the user's measure, spec 72)
# ``<folder>/<pid>-%C``: a pid has at most 7 digits (``pid_max`` 4194304), %C is 40 characters and
# ssh first binds ``<path>.<16 random>``, so a folder of 34 bytes gives a socket path of 100, under
# the 104 of BSD/macOS (108 on Linux). Bytes, not characters: the kernel counts bytes.
MAX_DIR_BYTES = 34
FOLDER = "qe-studio-mux"
FALLBACK_TMP = "/tmp"  # when the temp folder is too long (macOS: /var/folders/…/T)


def control_dir(create: bool = True) -> Path | None:
    """The folder of the sockets, made when missing (``create``); None when there is no safe one
    (Windows, a path too long, a link, another owner, a folder that cannot be made). Checked on
    every call: a tmp cleaner may remove it, or someone else put a link in its place, while Lain
    runs."""
    if sys.platform == "win32":
        return None  # OpenSSH for Windows does not multiplex (not verified): off there
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isabs(runtime):
        return _prepared(os.path.join(runtime, FOLDER), create)
    name = f"{FOLDER}-{os.getuid()}"
    base = os.path.join(tempfile.gettempdir(), name)
    if _too_long(base):
        base = os.path.join(FALLBACK_TMP, name)
    return _prepared(base, create)


def _too_long(path: str) -> bool:
    return len(os.fsencode(path)) > MAX_DIR_BYTES


def _prepared(path: str, create: bool) -> Path | None:
    if _too_long(path):
        return None
    if create:
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
        except OSError:
            return None
    try:
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            return None  # a link or someone else's folder: never put a socket there
        if info.st_mode & 0o077:
            os.chmod(path, 0o700)
    except OSError:
        return None  # not there (``create=False``) or gone meanwhile
    return Path(path)


def _own() -> str:
    """The start of this process's socket names."""
    return f"{os.getpid()}-"


def sockets(folder: Path) -> list[Path]:
    """The sockets in ``folder`` (the masters of every Lain, live or dead)."""
    found = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if stat.S_ISSOCK(entry.stat(follow_symlinks=False).st_mode):
                        found.append(Path(entry.path))
                except OSError:
                    continue  # gone meanwhile
    except OSError:
        return []
    return sorted(found)


def options(cluster: ClusterConfig) -> list[str]:
    """The ssh options of the shared connection; none when it is off or has no folder."""
    if not cluster.multiplex:
        _log_once("ssh: multiplexing off (cluster.multiplex: false)")
        return []
    folder = control_dir()
    if folder is None:
        _log_once("ssh: multiplexing off (no safe folder for the control sockets)")
        return []
    _log_once(f"ssh: multiplexing through {folder}")
    return [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={folder}/{_own()}%C",
        "-o",
        f"ControlPersist={PERSIST_SECONDS}",
    ]


@cache
def _log_once(message: str) -> None:
    log.debug(message)


def close_all(ssh_binary: str, timeout_s: float) -> bool:
    """Stop this process's masters within ``timeout_s``; False when one did not stop in time.

    ``ssh -O stop`` (``-S``: the socket itself; the host only fills the argument) makes the master
    remove its socket at once and exit when no session is left. Another Lain's masters (another
    pid) are left alone, and the folder is never made here. A dead socket fails and is skipped; a
    master that does not answer in its share of the time is left to ``PERSIST_SECONDS``, and the
    next ones still get theirs. Never raises."""
    folder = control_dir(create=False)
    found = [p for p in sockets(folder) if p.name.startswith(_own())] if folder else []
    deadline = time.monotonic() + timeout_s
    finished = True
    for index, path in enumerate(found):
        share = (deadline - time.monotonic()) / (len(found) - index)
        if share <= 0:
            return False
        try:
            argv = [*shlex.split(ssh_binary), "-O", "stop", "-S", str(path), "localhost"]
            subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=share,
                check=False,
            )
        except subprocess.TimeoutExpired:
            finished = False  # stuck on a dead network: the next master still gets its share
        except (OSError, ValueError) as exc:  # no ssh to run: the masters end by themselves
            log.warning("ssh: cannot stop the shared connections (%s)", exc)
            return True
    return finished
