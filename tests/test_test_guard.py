"""The guard that keeps every test away from the cluster (spec 69 R7, ``tests/cluster_guard.py``).

Each case clears what it recorded on purpose, so the guard's own teardown does not fail it.
"""

import ast
import importlib
import subprocess
from pathlib import Path

import pytest
from PyQt6.QtCore import QProcess

import qe_studio
from qe_studio.core import config as core_config
from qe_studio.core.config import parse_config
from qe_studio.core.sync import monitor
from qe_studio.core.sync.command import remote_command, run_command
from qe_studio.core.sync.controller import SyncController
from qe_studio.core.sync.rsync import Endpoint

from cluster_guard import FIND_CONFIG_MODULES, ClusterGuardError, hosts_in, is_test_host
from ssh_server import HOST_ALIAS

REAL = "cluster.real.org"


def config(host: str = REAL):
    return parse_config({"cluster": {"host": host, "user": "usuario"}})


@pytest.fixture
def popen_calls(monkeypatch):
    calls = []
    real = subprocess.Popen

    def spy(argv, *args, **kwargs):
        calls.append(list(argv))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    return calls


def test_run_command_never_starts_ssh_to_another_host(_cluster_guard, popen_calls):
    with pytest.raises(ClusterGuardError, match=REAL):
        run_command(remote_command(config(), "true"), {}, 5)
    assert popen_calls == []  # no process was born
    assert len(_cluster_guard.violations) == 1
    _cluster_guard.violations.clear()


def test_a_local_command_runs(_cluster_guard, popen_calls):
    result = run_command(["true"], {}, 5)
    assert result.code == 0 and popen_calls == [["true"]]
    assert _cluster_guard.violations == []


def test_the_probe_never_connects_to_another_host(_cluster_guard, monkeypatch):
    connects = []
    monkeypatch.setattr(monitor.socket, "create_connection", lambda *a, **k: connects.append(a))
    assert monitor.probe(REAL, 22) is False
    assert connects == [] and len(_cluster_guard.violations) == 1
    _cluster_guard.violations.clear()


def test_rsync_never_starts_for_another_host(_cluster_guard, monkeypatch, tmp_path):
    starts = []
    monkeypatch.setattr(QProcess, "start", lambda self, *args: starts.append(args))
    run = SyncController(config())
    run.start(tmp_path, Endpoint("/scratch/usuario/run", REAL, "usuario"))
    assert starts == [] and not run.running  # the stage failed before the QProcess
    assert len(_cluster_guard.violations) == 1 and REAL in _cluster_guard.violations[0]
    _cluster_guard.violations.clear()


def test_a_config_outside_the_test_folders_is_refused(_cluster_guard, tmp_path):
    checkout = tmp_path / "checkout"  # a copy of the repository's layout, not the user's file
    (checkout / "tests").mkdir(parents=True)
    (checkout / "config.yaml").write_text("cluster:\n  host: cluster.real.org\n")
    _cluster_guard.config_roots = [checkout / "tests"]  # the temporary folders are "real" here
    with pytest.raises(ClusterGuardError, match="config.yaml real"):
        core_config.find_config(None, {}, cwd=checkout, checkout=tmp_path / "none")
    assert len(_cluster_guard.violations) == 1
    _cluster_guard.violations.clear()


def test_a_config_in_a_temporary_folder_is_allowed(_cluster_guard, tmp_path):
    (tmp_path / "config.yaml").write_text("ui: {}\n")
    assert core_config.find_config(None, {}, cwd=tmp_path, checkout=tmp_path / "none") == (
        tmp_path / "config.yaml"
    )
    assert _cluster_guard.violations == []


def find_config_binders() -> set[str]:
    """The modules of ``src/`` that bind ``find_config`` with ``from …config import``, by the AST: a
    module path moved without the guard's list would read the real config.yaml unguarded."""
    package = Path(qe_studio.__file__).parent
    found = set()
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[-1] == "config"
                and any(alias.name == "find_config" for alias in node.names)
            ):
                parts = path.relative_to(package).with_suffix("").parts
                found.add(".".join(("qe_studio", *parts)).removesuffix(".__init__"))
    return found


def test_the_guard_patches_every_module_that_binds_find_config(_cluster_guard):
    """Spec 78.5 R1.4: the guard swaps ``find_config`` in every module that binds the name, and only
    there; ``core.config`` defines it."""
    assert find_config_binders() | {"qe_studio.core.config"} == set(FIND_CONFIG_MODULES)
    for name in FIND_CONFIG_MODULES:
        assert importlib.import_module(name).find_config.__name__ == "guarded_find", name


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", HOST_ALIAS, "hpc.example", "x.invalid"])
def test_the_test_hosts_pass(host):
    assert is_test_host(host)


@pytest.mark.parametrize("host", [REAL, "hpc", "h", "10.0.0.1", "cluster.example.org"])
def test_other_hosts_do_not(host):
    assert not is_test_host(host)


def test_the_hosts_of_an_argv():
    ssh = remote_command(config("hpc.example"), "cd '/a b' && qsub x.qsub")
    assert hosts_in(ssh) == ["hpc.example"]
    rsync = ["rsync", "-e", "ssh -p 22 -o X=y", "--list-only", "me@h:/r/x/", "/local/"]
    assert hosts_in(rsync) == ["h"]
    assert hosts_in(["rsync", "--version"]) == []
