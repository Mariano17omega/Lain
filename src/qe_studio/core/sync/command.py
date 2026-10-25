"""One command on the cluster over ssh, other than rsync (spec 64 R1): the job list.

``run_command`` runs a child process to its end, its time limit or the cancellation of the task it
runs in (``core/cancel.py``), and kills it in the last two cases: a hung ssh never outlives the
query that started it. The child has no stdin and no controlling terminal (a new session), so ssh
never asks for a password on the terminal Lain was started from; a password reaches it only through
``SSH_ASKPASS`` in ``env`` (``rsync.child_env``).

The text of a remote command comes from ``config.yaml`` only: nothing read from the cluster ever
goes into one.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from dataclasses import dataclass

from .. import cancel
from ..config import AppConfig
from .rsync import ssh_command

POLL_SECONDS = 0.2  # how often the wait looks at the cancellation and the deadline
REAP_SECONDS = 2.0  # what a killed child gets to close its pipes


@dataclass(frozen=True)
class CommandResult:
    code: int | None  # None: killed (time limit)
    stdout: str
    stderr: str
    timed_out: bool = False


def remote_command(config: AppConfig, command: str) -> list[str]:
    """``ssh`` with Lain's options (``ssh_command``) running ``command`` on the cluster."""
    cluster = config.cluster
    return [
        *ssh_command(cluster, config.sync.ssh_binary),
        f"{cluster.user}@{cluster.host}",
        command,
    ]


def run_command(argv: list[str], env: dict[str, str], timeout_s: float) -> CommandResult:
    """Run ``argv`` and return its output (UTF-8, undecodable bytes kept as surrogates).

    Raises ``cancel.Cancelled`` when the task was cancelled, after the child is gone; ``OSError``
    when ``argv[0]`` cannot be run."""
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        encoding="utf-8",
        errors="surrogateescape",
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            # Retrying after TimeoutExpired loses no output (subprocess documents the pattern).
            stdout, stderr = proc.communicate(timeout=POLL_SECONDS)
            return CommandResult(proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            pass
        if cancel.is_cancelled():
            _kill(proc)
            raise cancel.Cancelled
        if time.monotonic() >= deadline:
            stdout, stderr = _kill(proc)
            return CommandResult(None, stdout, stderr, timed_out=True)


def _kill(proc: subprocess.Popen) -> tuple[str, str]:
    """Kill ``proc`` with its session (a ``ProxyCommand`` of ssh too) and reap it; what it wrote."""
    with contextlib.suppress(ProcessLookupError):
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)  # the child leads its own session: pgid == pid
        else:
            proc.kill()
    try:
        stdout, stderr = proc.communicate(timeout=REAP_SECONDS)
    except subprocess.TimeoutExpired:  # a grandchild of its own session still holds the pipes
        proc.wait()
        return "", ""
    return stdout or "", stderr or ""
