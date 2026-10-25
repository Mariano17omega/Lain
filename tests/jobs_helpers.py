"""Shared pieces of the cluster jobs tests (spec 64): the two listings of the spec, a fake
``fetch_jobs`` and a window with a cluster."""

from __future__ import annotations

import threading

from qe_studio.core import cancel
from qe_studio.core.cluster_jobs import parse_qstatus
from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.sync import monitor
from qe_studio.ui import jobs_controller

USER = "usuario"

# ``qstatus -a`` and ``qstatus`` of the user's cluster, as in the spec (logins of others replaced).
QSTATUS_ALL = """\
Running jobs:
 job-ID  # name                      owner      start time          running in
------------------------------------------------------------------------------
  23538 32 Nd2Fe14B-4f-129           usuario_a  10/15/2026 17:53:02 physica.q
  23591 32 hBN+Sm-1                  usuario_b  10/20/2026 11:29:17 physica.q
  23592 32 hBN+Eu-1                  usuario_b  10/22/2026 08:34:47 physica.q

Waiting jobs:
 job-ID  # name                      owner      submit time
-------------------------------------------------------------------
  23542 32 Sm3NbO8-HP-130            usuario_a  10/15/2026 18:05:21
  23543 32 BNNT90-S-375              usuario_a  10/15/2026 18:07:00
"""

QSTATUS_MINE = """\
Waiting jobs for user: usuario
 job-ID  # name                      submit time
--------------------------------------------------------
  23644 32 Bands-kao-b               10/22/2026 23:39:04
  23645 32 PDS-B                     10/22/2026 23:43:43
  23646 32 Bands-kao-001-p           10/22/2026 23:46:20
"""

EMPTY = "Running jobs:\n\nWaiting jobs:\n"


def with_mine(*names: str, waiting: int = 0) -> str:
    """``QSTATUS_ALL`` with running jobs of ``USER`` named ``names`` (after the others) and
    ``waiting`` of theirs in the queue."""
    running, queue = QSTATUS_ALL.split("\nWaiting jobs:\n")
    lines = [
        f"  {24000 + i} 16 {name:<25} {USER:<10} 10/24/2026 09:0{i}:00 physica.q"
        for i, name in enumerate(names)
    ]
    queued = [
        f"  {25000 + i} 16 Queued-{i:<18} {USER:<10} 10/24/2026 10:00:0{i}" for i in range(waiting)
    ]
    head = running.rstrip("\n") + "\n" + "".join(f"{line}\n" for line in lines)
    return head + "\nWaiting jobs:\n" + queue + "".join(f"{line}\n" for line in queued)


def snapshot(text: str = QSTATUS_ALL):
    return parse_qstatus(text, fetched_at=1_761_400_000.0)


class FakeFetch:
    """``fetch_jobs`` of the tests: answers ``result`` (a value, or a callable of the config and the
    password) and keeps the password of every call. ``hold()`` makes the next calls wait for
    ``release()``, or for their task to be cancelled."""

    def __init__(self, result=None):
        self.result = snapshot() if result is None else result
        self.calls: list[str | None] = []
        self._gate = threading.Event()
        self._gate.set()
        self.exited = threading.Event()  # a held call is over (released or cancelled)

    def hold(self) -> None:
        self._gate.clear()
        self.exited.clear()

    def release(self) -> None:
        self._gate.set()

    def __call__(self, config, password=None):
        self.calls.append(password)
        try:
            while not self._gate.wait(0.02):
                cancel.check()
        finally:
            self.exited.set()
        return self.result(config, password) if callable(self.result) else self.result


def cluster_window(window_factory, demo_project, monkeypatch, fetch, reachable=True, **cluster):
    """A window whose config has a cluster (``cluster`` overrides its keys); ``fetch`` stands in
    for ``fetch_jobs`` and the reachability probe answers ``reachable`` without the network."""
    monkeypatch.setattr(jobs_controller, "fetch_jobs", fetch)
    monkeypatch.setattr(monitor, "probe", lambda *_args, **_kwargs: reachable)
    settings = {"host": "hpc.example", "user": USER, **cluster}
    paths = {"local_root": str(demo_project), "remote_root": "/scratch/usuario"}
    config = parse_config({"paths": paths, "cluster": settings})
    return window_factory(loaded=LoadedConfig(config, None))
