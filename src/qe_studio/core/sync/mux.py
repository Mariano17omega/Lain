"""One ssh connection for many commands (spec 72): OpenSSH's ``ControlMaster``.

The first ssh to the cluster becomes a master that logs in and keeps the connection; the next ones
(``qstatus``, the listing, ``qsub``, the sync's rsync…) open a session through its socket, without
a login of their own, until ``PERSIST_SECONDS`` pass with no client. ``ssh_command`` adds
``options`` to every ssh Lain runs; ``cluster.multiplex: false`` turns it off. A session the
cluster refuses (its ``MaxSessions``) makes ssh log in by itself, as without a master.

The sockets live in ``control_dir()``: a folder of the user's own, ``0700``, short enough for the
path of a Unix socket (104 characters on BSD/macOS). Closing the window stops the masters
(``close_all``, the "ssh" step of ``ui/shutdown.py``); one left by a killed Lain ends by itself.
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
from functools import cache, lru_cache
from pathlib import Path

from ..config import ClusterConfig

log = logging.getLogger(__name__)

PERSIST_SECONDS = 120  # what the master waits for another client (the user's measure, spec 72)
# ``<folder>/%C``: %C is 40 characters and ssh first binds ``<path>.<16 random>``, so a folder of 42
# gives a socket path of 100, under the 104 of BSD/macOS (108 on Linux).
MAX_DIR_CHARS = 42
FOLDER = "qe-studio-mux"


def control_dir() -> Path | None:
    """The folder of the sockets, made on first use; None when there is no safe one (Windows, a
    path too long, a link, another owner, a folder that cannot be made)."""
    if sys.platform == "win32":
        return None  # OpenSSH for Windows does not multiplex (not verified): off there
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isabs(runtime):
        base = os.path.join(runtime, FOLDER)
    else:
        base = os.path.join(tempfile.gettempdir(), f"{FOLDER}-{os.getuid()}")
    folder = _prepared(base)
    if folder is not None and not os.path.isdir(folder):
        # Removed while Lain runs (a tmp cleaner): ssh cannot bind its socket there and fails.
        _prepared.cache_clear()
        folder = _prepared(base)
    return folder


@lru_cache(maxsize=8)
def _prepared(path: str) -> Path | None:
    if len(path) > MAX_DIR_CHARS:
        return None
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
        return None
    return Path(path)


def sockets(folder: Path) -> list[Path]:
    """The sockets in ``folder`` (the masters, live or dead)."""
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
        f"ControlPath={folder}/%C",
        "-o",
        f"ControlPersist={PERSIST_SECONDS}",
    ]


@cache
def _log_once(message: str) -> None:
    log.debug(message)


def close_all(ssh_binary: str, timeout_s: float) -> bool:
    """Stop every master in ``control_dir()`` within ``timeout_s``; False when time ran out.

    ``ssh -O stop`` (``-S``: the socket itself; the host only fills the argument) makes the master
    remove its socket at once and exit when no session is left: another Lain window's transfer
    still ends. A dead socket fails and is skipped. Never raises."""
    folder = control_dir()
    found = sockets(folder) if folder is not None else []
    deadline = time.monotonic() + timeout_s
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
            return False
        except (OSError, ValueError) as exc:  # no ssh to run: the masters end by themselves
            log.warning("ssh: cannot stop the shared connections (%s)", exc)
            return True
    return True
