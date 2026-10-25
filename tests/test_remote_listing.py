"""Listing a folder of the cluster (spec 65 R1): the ``rsync --list-only`` output read, its failures
told apart, and the real thing through the test SSH server."""

import calendar
import os
import shlex

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote import listing
from qe_studio.core.remote.listing import (
    NO_ACCESS,
    NOT_FOUND,
    RemoteEntry,
    RemoteFailure,
    classify,
    list_remote,
    parse_listing,
)
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.rsync import list_command

# What rsync 3.5.0 printed (LC_ALL=C.UTF-8, TZ=UTC, --no-h), measured for the spec, plus a link in
# its ``-l`` form and a name with a non-printable byte.
LISTING = """\
drwxrwxr-x         280 2026/10/25 06:39:38 .
-rw-rw-r--           1 2026/10/25 06:39:38 .hidden
-rw-rw-r--           1 2026/10/25 06:39:38 a[1].in
-rw-rw-r--     1234567 2026/10/25 06:39:38 big.dat
-rw-rw-r--           1 2026/10/25 06:39:38 com espaço.out
lrwxrwxrwx           7 2026/10/25 06:39:38 link -> big.dat
-rw-rw-r--           1 2026/10/25 06:39:38 w\\#001x
-rw-rw-r--           1 2026/10/25 06:39:38 run10.out
-rw-rw-r--           1 2026/10/25 06:39:38 run2.out
drwxrwxr-x          40 2026/10/25 06:39:38 .git
drwxrwxr-x          40 2026/10/25 06:39:38 com espaço
drwxrwxr-x          80 2026/10/25 06:39:38 sub
drwxrwxr-x          40 2026/10/25 06:39:38 tmp
drwxrwxr-x          40 2026/10/25 06:39:38 al.save
"""
T = float(calendar.timegm((2026, 10, 25, 6, 39, 38, 0, 0, 0)))
HIDDEN = ["tmp", "*.save"]


def config(**sync):
    return parse_config(
        {
            "paths": {"remote_root": "/scratch/u"},
            "cluster": {"host": "hpc", "user": "u"},
            "sync": sync,
        }
    )


def test_the_measured_listing_is_read():
    entries = parse_listing(LISTING, HIDDEN)
    assert [entry.name for entry in entries] == [
        "com espaço",
        "sub",
        "a[1].in",
        "big.dat",
        "com espaço.out",
        "link",
        "run2.out",
        "run10.out",
        "w\x01x",
    ]
    by_name = {entry.name: entry for entry in entries}
    assert by_name["big.dat"] == RemoteEntry("big.dat", False, 1234567, T)
    assert by_name["sub"] == RemoteEntry("sub", True, 80, T)
    assert by_name["link"].link and not by_name["link"].is_dir


def test_dots_hidden_folders_and_other_lines_are_left_out():
    text = "receiving incremental file list\n" + LISTING + "\nsent 10 bytes\n"
    names = {entry.name for entry in parse_listing(text, HIDDEN)}
    assert not names & {".", ".hidden", ".git", "tmp", "al.save"}
    assert "tmp" in {entry.name for entry in parse_listing(LISTING, [])}  # only by the config


def test_a_link_without_its_target_is_still_a_link():
    entry = parse_listing("lrwxrwxrwx 7 2026/10/25 06:39:38 link\n", [])[0]
    assert entry == RemoteEntry("link", False, 7, T, link=True)


def test_the_list_command():
    argv = list_command(config(), "/scratch/u/a b", (3, 5, 0))
    assert argv[:2] == ["rsync", "--list-only"]
    assert "--no-h" in argv and argv[-1] == "u@hpc:/scratch/u/a b/"
    assert "--protect-args" not in argv
    ssh = shlex.split(argv[argv.index("-e") + 1])
    assert "StrictHostKeyChecking=yes" in ssh
    old = list_command(config(), "/scratch/u", (3, 2, 3))
    assert "--protect-args" in old  # names read from the cluster never reach a remote shell


def result(code, stderr="", stdout="", timed_out=False):
    return CommandResult(code, stdout, stderr, timed_out)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            result(23, 'rsync: [sender] change_dir "/x" failed: No such file or directory (2)'),
            RemoteFailure(NOT_FOUND, missing=True),
        ),
        (
            result(23, 'rsync: [sender] opendir "/x" failed: Permission denied (13)'),
            RemoteFailure(NO_ACCESS),
        ),
        (result(None, timed_out=True), RemoteFailure(listing.TIMED_OUT, connection=True)),
    ],
)
def test_failures_are_told_apart(answer, expected):
    assert classify(answer, []) == expected


def test_a_refused_login_is_ssh_s():
    refused = (
        "u@hpc: Permission denied (publickey,password).\nrsync: connection unexpectedly closed"
    )
    failure = classify(result(255, refused), [])
    assert isinstance(failure, RemoteFailure) and failure.auth and not failure.connection
    unreachable = classify(result(255, "ssh: connect to host hpc port 22: Connection refused"), [])
    assert isinstance(unreachable, RemoteFailure) and unreachable.connection


def test_a_local_rsync_that_cannot_run(monkeypatch):
    monkeypatch.setattr(listing, "_versions", {})
    failure = list_remote(config(rsync_binary="/no/such/rsync"), "/scratch/u")
    assert isinstance(failure, RemoteFailure) and failure.local
    assert "rsync" in failure.message  # it could not be started: "Não foi possível executar…"


# -- through ssh ----------------------------------------------------------------------------------
def test_listing_through_ssh(ssh_server):
    server, remote = ssh_server
    (remote / "Analise 1" / "Bandas").mkdir(parents=True)
    (remote / "tmp").mkdir()
    (remote / "a[1].in").write_text("x")
    (remote / "scf.out").write_bytes(b"0" * 1234)
    os.utime(remote / "scf.out", (T, T))
    cfg = parse_config(server.config_data())

    entries = list_remote(cfg, str(remote))
    assert entries == [
        RemoteEntry("Analise 1", True, entries[0].size, entries[0].mtime),
        RemoteEntry("a[1].in", False, 1, entries[1].mtime),
        RemoteEntry("scf.out", False, 1234, T),
    ]
    inner = list_remote(cfg, str(remote / "Analise 1"))
    assert [entry.name for entry in inner] == ["Bandas"]
    assert all(command.startswith("rsync --server") for command in server.commands())

    missing = list_remote(cfg, str(remote / "nada"))
    assert missing == RemoteFailure(NOT_FOUND, missing=True)
