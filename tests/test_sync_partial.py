"""What comes through when part of a sync cannot: folders nobody can read, files that vanish, what a
killed rsync leaves, and names the cluster's shell must not expand. The real rsync; no cluster."""

import os
import shutil
import stat
from contextlib import contextmanager

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote.listing import list_remote
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.partial import remove_temp_files
from qe_studio.core.sync.push import PushController
from qe_studio.core.sync.rsync import Endpoint

from sync_helpers import T0, run_push, run_sync, write

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
needs_permissions = pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")

# What sshd does with a command: ssh's options dropped, then a real shell, which expands wildcards.
# ``tests/ssh_server.py`` has no shell, so it cannot tell a quoted path from a bare one.
FAKE_SSH = """#!/bin/sh
while [ "$1" != "127.0.0.1" ]; do shift; done
shift
exec sh -c "$*"
"""


def by_date():
    return parse_config({"sync": {"checksum": False}})  # a dry run that opens no file


@pytest.fixture
def dirs(tmp_path):
    remote = tmp_path / "cluster" / "run"
    remote.mkdir(parents=True)
    return remote, tmp_path / "local" / "run"


@contextmanager
def no_access(path):
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(0)
    try:
        yield
    finally:
        path.chmod(mode)


def pull(qtbot, remote, local, **kwargs):
    return run_sync(qtbot, SyncController(by_date()), local, Endpoint(str(remote)), **kwargs)[0]


@needs_permissions
def test_an_unreadable_folder_is_left_out_and_the_rest_comes(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    write(remote, "locked/b.out", "b")
    with no_access(remote / "locked"):
        report = pull(qtbot, remote, local)
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == ["a.out"]
    assert report.not_read == (str(remote / "locked"),) and report.left_out
    assert "1 item não pôde ser lido e ficou de fora." in report.message
    assert "1 item não pôde ser lido" in report.headline
    assert str(remote / "locked") in report.details
    assert not report.auth_failed


@needs_permissions
def test_up_to_date_but_for_an_unreadable_folder_says_so(qtbot, dirs):
    remote, local = dirs
    write(remote, "locked/b.out", "b")
    with no_access(remote / "locked"):
        report = pull(qtbot, remote, local)
    assert report.status is SyncStatus.UP_TO_DATE, report.error
    assert report.left_out and "ficou de fora" in report.message


@needs_permissions
def test_an_unreadable_folder_to_sync_is_a_failure_and_no_refused_login(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    with no_access(remote):
        report = pull(qtbot, remote, local)
    assert report.status is SyncStatus.FAILED
    assert "Permission denied" in report.error and not report.auth_failed


def test_a_missing_folder_is_still_not_found(qtbot, dirs):
    remote, local = dirs
    report = pull(qtbot, remote / "gone", local)
    assert report.status is SyncStatus.FAILED and "não encontrada" in report.error


@needs_permissions
def test_a_file_that_cannot_be_read_fails_and_says_what_arrived(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    write(remote, "z.out", "z")
    with no_access(remote / "z.out"):
        report = pull(qtbot, remote, local)
    assert report.status is SyncStatus.FAILED and not report.auth_failed
    assert report.transferred == ["a.out"] and (local / "a.out").read_text() == "a"
    assert "1 de 2 arquivos não foi transferido: " in report.error
    assert "1 arquivo baixado antes da falha." in report.message


@needs_permissions
def test_a_push_says_what_went_up_before_it_failed(qtbot, dirs):
    remote, local = dirs
    local.mkdir(parents=True)
    write(local, "a.in", "a")
    write(local, "z.in", "z")
    with no_access(local / "z.in"):
        report = run_push(qtbot, PushController(by_date()), local, Endpoint(str(remote)))
    assert report.status is SyncStatus.FAILED
    assert report.transferred == ["a.in"] and (remote / "a.in").exists()
    assert "1 arquivo enviado antes da falha." in report.message


def test_a_file_gone_before_the_transfer_does_not_fail_the_others(qtbot, dirs):
    remote, local = dirs
    write(remote, "a.out", "a")
    write(remote, "b.out", "b")
    report = pull(qtbot, remote, local, before_confirm=lambda _plan: (remote / "b.out").unlink())
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == ["a.out"] and report.not_read == ("b.out",)


def test_a_name_that_is_not_utf8_is_pulled(qtbot, dirs):
    remote, local = dirs
    name = os.fsdecode(b"caf\xe9.in")
    write(remote, name, "x")
    report = pull(qtbot, remote, local)
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == [name] and (local / name).read_text() == "x"


def test_the_cleanup_keeps_a_user_file_of_the_same_shape(tmp_path):
    write(tmp_path, ".a.in.backup", "mine", T0 - 1000)
    write(tmp_path, ".a.in.Ab12Cd", "rsync's", T0)
    remove_temp_files(["a.in"], tmp_path, since=T0)
    assert [path.name for path in tmp_path.iterdir()] == [".a.in.backup"]


# -- names the cluster's shell would expand -------------------------------------------------------
@pytest.fixture
def shell_config(tmp_path):
    script = tmp_path / "fake-ssh"
    script.write_text(FAKE_SSH)
    script.chmod(0o700)
    return parse_config(
        {
            "sync": {"ssh_binary": str(script), "checksum": False},
            "cluster": {"host": "127.0.0.1", "user": "me"},
        }
    )


@pytest.mark.parametrize("name", ["run[1]", "a b*", "it's $HOME?"])
def test_a_pull_reads_the_folder_of_that_very_name(qtbot, tmp_path, shell_config, name):
    base = tmp_path / "r"
    write(base, f"{name}/right.out", "right")
    write(base, "run1/wrong.out", "wrong")  # what ``run[1]`` expands to
    write(base, "a bc/wrong.out", "wrong")
    endpoint = Endpoint(str(base / name), "127.0.0.1", "me")
    report, _ = run_sync(qtbot, SyncController(shell_config), tmp_path / "pulled", endpoint)
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == ["right.out"]


def test_a_push_writes_into_the_folder_of_that_very_name(qtbot, tmp_path, shell_config):
    base = tmp_path / "r"
    write(base, "run[1]/old.out", "x")
    write(base, "run1/wrong.out", "wrong")
    write(tmp_path, "l/scf.in", "input")
    endpoint = Endpoint(str(base / "run[1]"), "127.0.0.1", "me")
    report = run_push(qtbot, PushController(shell_config), tmp_path / "l", endpoint)
    assert report.status is SyncStatus.DONE, report.error
    assert (base / "run[1]" / "scf.in").read_text() == "input"
    assert not (base / "run1" / "scf.in").exists()


def test_a_listing_reads_the_folder_of_that_very_name(tmp_path, shell_config):
    base = tmp_path / "r"
    write(base, "run[1]/right.out", "right")
    write(base, "run1/wrong.out", "wrong")
    found = list_remote(shell_config, str(base / "run[1]"))
    assert [entry.name for entry in found] == ["right.out"]  # type: ignore[union-attr]
