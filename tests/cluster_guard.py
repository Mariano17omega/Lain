"""The cluster is production (spec 69 R7): no test ever reaches it.

``tests/conftest.py`` installs a ``Guard`` around every test. It watches the three ways Lain reaches
the network, before anything starts:

- ``run_command`` (``core/sync/command.py``): the module's ``subprocess`` is a proxy whose ``Popen``
  checks the hosts in the argv first. Every caller goes through it, however and whenever it imported
  ``run_command`` (the job list, the listings, the actions on the cluster);
- ``RsyncRun._launch`` (``core/sync/_process.py``): its endpoint and argv, before the ``QProcess``;
- ``monitor.probe`` (``core/sync/monitor.py``): the host of the TCP probe.

A host that is not a test one (``127.0.0.1``, ``localhost``, ``ssh_server.HOST_ALIAS`` or a name under
the reserved ``.invalid``, ``.example`` and ``.test``, RFC 2606/6761) is a violation: it is recorded,
nothing is started, and the test fails at teardown even when it happened in a worker. ``find_config``
is watched too: a ``config.yaml`` outside the pytest temporary folders and ``tests/`` (the real one
of the checkout, or of the user's home) is a violation; the committed ``config.example.yaml`` is not.

The guard is never loosened for a test to pass: a test talks to ``tests/ssh_server.py`` or a fake.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ssh_server import HOST_ALIAS

TEST_HOSTS = frozenset({"127.0.0.1", "localhost", HOST_ALIAS})
RESERVED_DOMAINS = (".invalid", ".example", ".test")
_CHECKOUT = Path(__file__).resolve().parents[1]
EXAMPLES = frozenset(  # the two copies of config.example.yaml (tests/test_config.py reads them)
    {
        _CHECKOUT / "config.example.yaml",
        _CHECKOUT / "src" / "qe_studio" / "resources" / "config.example.yaml",
    }
)

_SSH_TARGET = re.compile(r"^[^@\s/:]*@([^@\s/:]+)$")  # user@host, the last ssh argument
_RSYNC_TARGET = re.compile(r"^(?:[^@\s/:]*@)?([^@\s/:]+):")  # [user@]host:path (Endpoint.spec)


class ClusterGuardError(AssertionError):
    """A test tried to reach a host that is not a test one, or read the real config.yaml. An
    ``Exception``: a worker reports it through its ``on_error``, a sync stage ends FAILED."""


def is_test_host(host: str) -> bool:
    name = host.strip().strip("[]").rstrip(".").lower()
    return name in TEST_HOSTS or name.endswith(RESERVED_DOMAINS)


def hosts_in(argv: Sequence[str]) -> list[str]:
    """The hosts an ssh or rsync argv contacts: its ``user@host`` and ``[user@]host:path`` tokens.
    Options, absolute paths and texts with spaces (``-e "ssh …"``, a remote command) are none."""
    hosts = []
    for token in list(argv)[1:]:
        if token.startswith("-"):
            continue
        match = _SSH_TARGET.match(token) or _RSYNC_TARGET.match(token)
        if match:
            hosts.append(match.group(1))
    return hosts


class _GuardedSubprocess:
    """``subprocess`` for ``core/sync/command.py``: the same module, with ``Popen`` checked first."""

    def __init__(self, guard: Guard):
        self._guard = guard

    def Popen(self, argv, *args, **kwargs):  # noqa: N802 (the name it stands for)
        for host in hosts_in(argv):
            self._guard.check_host(host)
        return subprocess.Popen(argv, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(subprocess, name)


class Guard:
    def __init__(self, config_roots: list[Path]):
        self.config_roots = config_roots  # where a test's config.yaml may be
        self.violations: list[str] = []

    def violation(self, message: str) -> ClusterGuardError:
        self.violations.append(message)
        return ClusterGuardError(message)

    def check_host(self, host: str | None) -> None:
        """Raise unless ``host`` is a test one; None (a local endpoint) passes."""
        if host is not None and not is_test_host(host):
            message = (
                f"Um teste tentou falar com {host}: os testes nunca chegam ao cluster (spec 69 R7)."
            )
            raise self.violation(message)

    def check_config(self, path: Path | None) -> None:
        if path is None:
            return
        resolved = Path(path).resolve()
        if resolved in EXAMPLES:
            return  # committed, with cluster.example.org: never the user's
        if not any(resolved.is_relative_to(root.resolve()) for root in self.config_roots):
            message = (
                f"Um teste leu o config.yaml real ({path}): o cluster é ambiente de produção "
                "(spec 69 R7)."
            )
            raise self.violation(message)

    def install(self, monkeypatch) -> None:
        from qe_studio.core import config, language
        from qe_studio.core.sync import _process, command, monitor

        monkeypatch.setattr(command, "subprocess", _GuardedSubprocess(self))

        launch = _process.RsyncRun._launch

        def guarded_launch(run, argv, *args, **kwargs):
            self.check_host(run._remote.host)
            for host in hosts_in(argv):
                self.check_host(host)
            return launch(run, argv, *args, **kwargs)

        monkeypatch.setattr(_process.RsyncRun, "_launch", guarded_launch)

        probe = monitor.probe

        def guarded_probe(host: str, port: int, *args, **kwargs) -> bool:
            try:
                self.check_host(host)
            except ClusterGuardError:
                return False  # a daemon thread: recorded, never connected
            return probe(host, port, *args, **kwargs)

        monkeypatch.setattr(monitor, "probe", guarded_probe)

        find = config.find_config

        def guarded_find(*args, **kwargs) -> Path | None:
            path = find(*args, **kwargs)
            self.check_config(path)
            return path

        for module in (config, language):
            monkeypatch.setattr(module, "find_config", guarded_find)
