"""Listing a folder of the cluster (spec 65 R1): the ``rsync --list-only`` output read, its failures
told apart, and the real thing through the test SSH server."""

import calendar
import os
import shlex
from types import SimpleNamespace

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote import listing
from qe_studio.core.remote.listing import (
    NO_ACCESS,
    NOT_FOUND,
    RemoteEntry,
    RemoteFailure,
    classify,
    list_outputs,
    list_remote,
    parse_listing,
    parse_outputs,
    sort_entries,
)
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.rsync import list_command, outputs_command

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


def test_entries_sort_by_size_and_date_with_folders_first():
    entries = [
        RemoteEntry("b.out", False, 10, 300.0),
        RemoteEntry("a.out", False, 10, 100.0),
        RemoteEntry("run10", True, 4096, 100.0),
        RemoteEntry("big.dat", False, 999, 200.0),
        RemoteEntry("run2", True, 4096, 400.0),
    ]

    def names(by):
        return [entry.name for entry in sort_entries(entries, by)]

    assert names("name") == ["run2", "run10", "a.out", "b.out", "big.dat"]
    assert names("size") == ["run2", "run10", "big.dat", "a.out", "b.out"]  # ties by name
    assert names("date") == ["run2", "run10", "b.out", "big.dat", "a.out"]  # the newest first
    assert names("size") == [e.name for e in sort_entries(reversed(entries), "size")]


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


def test_the_outputs_command_lists_only_scheduler_outputs_below():
    """Spec 84: the outputs of jobs anywhere in a folder about to go to the trash, in one listing."""
    argv = outputs_command(config(), "/scratch/u/proj", (3, 5, 0))
    assert argv[:3] == ["rsync", "--list-only", "-r"]
    filters = [a for a in argv if a.startswith(("--include", "--exclude"))]
    assert filters == ["--include=*/", "--include=*.o[0-9]*", "--exclude=*"]
    assert argv[-1] == "u@hpc:/scratch/u/proj/"
    assert "--protect-args" in outputs_command(config(), "/scratch/u", (3, 2, 3))


def test_a_silent_walk_is_not_cut_by_rsync_s_own_limit():
    """Finding the outputs reads a whole tree and prints little: the deadline of ``list_outputs`` and
    ssh's keepalive watch it, not ``--timeout``."""
    assert "--timeout=0" in outputs_command(config(), "/scratch/u/proj", (3, 5, 0))
    assert "--timeout=60" in list_command(config(), "/scratch/u/proj", (3, 5, 0))


def test_outputs_are_paths_below_the_folder():
    stdout = (
        "drwxrwxr-x         140 2026/11/01 02:51:51 .\n"
        "-rw-rw-r--           0 2026/11/01 02:51:51 Al.o12\n"
        "drwxrwxr-x          60 2026/11/01 02:51:51 PDOS/orb its\n"
        "-rw-rw-r--           0 2026/11/01 02:51:51 PDOS/orb its/PDOS-Al.o24000\n"
    )
    assert parse_outputs(stdout) == ["Al.o12", "PDOS/orb its/PDOS-Al.o24000"]


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


# -- the scheduler outputs of a tree, when rsync could not read all of it ---------------------------
TOP = "drwxrwxr-x         140 2026/11/01 02:51:51 .\n"
OUTPUT = "-rw-rw-r--           0 2026/11/01 02:51:51 Al.o12\n"
DENIED = 'rsync: [sender] opendir "/scratch/u/proj/locked" failed: Permission denied (13)\n'
GONE = 'rsync: opendir "/scratch/u/proj/old" failed: No such file or directory (2)\n'
ERROR_23 = "rsync error: some files/attrs were not transferred (code 23) at main.c(1394)\n"


@pytest.fixture
def answers(monkeypatch):
    """``run_command`` of the listing: answers ``answers.result``, keeps the deadline it was given."""
    state = SimpleNamespace(result=None, deadlines=[])

    def run(_argv, _env, timeout_s):
        state.deadlines.append(timeout_s)
        return state.result

    monkeypatch.setattr(listing, "run_command", run)
    monkeypatch.setattr(listing, "local_version", lambda *_args: (3, 5, 0))
    return state


def outputs_of(answers, code, stdout="", stderr="", timed_out=False):
    answers.result = CommandResult(code, stdout, stderr, timed_out)
    return list_outputs(config(), "/scratch/u/proj")


def test_a_subfolder_that_cannot_be_read_is_named_and_the_rest_is_kept(answers):
    found = outputs_of(answers, 23, TOP + OUTPUT, DENIED + ERROR_23)
    assert found == listing.Outputs(["Al.o12"], ("/scratch/u/proj/locked",))


def test_a_subfolder_that_vanished_is_no_failure(answers):
    assert outputs_of(answers, 23, TOP + OUTPUT, GONE + ERROR_23) == listing.Outputs(["Al.o12"])
    vanished = 'file has vanished: "/scratch/u/proj/x.o3"\nrsync warning: (code 24)\n'
    assert outputs_of(answers, 24, TOP + OUTPUT, vanished) == listing.Outputs(["Al.o12"])


def test_the_failure_counts_by_its_number_not_its_language(answers):
    translated = 'rsync: opendir "/scratch/u/proj/old" failed: Arquivo inexistente (2)\n'
    assert outputs_of(answers, 23, TOP, translated + ERROR_23) == listing.Outputs([])
    denied = 'rsync: opendir "/scratch/u/proj/locked" failed: Permissão negada (13)\n'
    found = outputs_of(answers, 23, TOP, denied + ERROR_23)
    assert found == listing.Outputs([], ("/scratch/u/proj/locked",))


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            'rsync: change_dir "/scratch/u/proj" failed: No such file or directory (2)\n',
            RemoteFailure(NOT_FOUND, missing=True),
        ),
        (
            'rsync: change_dir "/scratch/u/proj" failed: Permission denied (13)\n',
            RemoteFailure(NO_ACCESS),
        ),
    ],
)
def test_the_folder_itself_not_read_is_still_a_failure(answers, stderr, expected):
    """No ``.`` line: nothing below it was looked at."""
    assert outputs_of(answers, 23, "", stderr + ERROR_23) == expected


def test_a_partial_answer_that_says_nothing_is_a_failure(answers):
    """Code 23 with no line that says what failed: what arrived cannot be called complete."""
    found = outputs_of(answers, 23, TOP + OUTPUT, ERROR_23)
    assert isinstance(found, RemoteFailure)


def test_another_failure_keeps_its_meaning(answers):
    found = outputs_of(answers, 255, "", "ssh: connect to host hpc port 22: Connection refused\n")
    assert isinstance(found, RemoteFailure) and found.connection


def test_a_tree_too_long_to_read_is_not_a_cluster_that_is_down(answers):
    """The cluster answered all along (a dead connection is ssh's keepalive, code 255): the LED must
    not say otherwise, and the listing has much longer than one folder's."""
    assert outputs_of(answers, None, timed_out=True) == RemoteFailure(listing.TOO_LONG)
    assert answers.deadlines == [config().cluster.connect_timeout + listing.OUTPUTS_SECONDS]
    answers.deadlines.clear()
    answers.result = CommandResult(0, TOP, "")
    list_remote(config(), "/scratch/u/proj")
    assert answers.deadlines == [config().cluster.connect_timeout + listing.EXTRA_SECONDS]


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


def test_outputs_through_ssh(ssh_server):
    """Every ``<name>.o<id>`` below, hidden folders and the ones the panels hide included; nothing
    else."""
    server, remote = ssh_server
    (remote / "proj" / "PDOS" / "tmp").mkdir(parents=True)
    (remote / "proj" / ".old").mkdir()
    for name in ("proj/scf.in", "proj/Al.o12", "proj/PDOS/PDOS-Al.o24000", "proj/PDOS/tmp/x.o3"):
        (remote / name).write_text("x")
    (remote / "proj" / ".old" / "Old.o1").write_text("x")
    (remote / "proj" / "PDOS" / "notes.out").write_text("x")
    cfg = parse_config(server.config_data())
    found = list_outputs(cfg, str(remote / "proj"))
    assert isinstance(found, listing.Outputs) and found.unread == ()
    assert sorted(found.found) == [".old/Old.o1", "Al.o12", "PDOS/PDOS-Al.o24000", "PDOS/tmp/x.o3"]
    missing = list_outputs(cfg, str(remote / "nada"))
    assert isinstance(missing, RemoteFailure) and missing.missing


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores modes")
@pytest.mark.parametrize("output", ["Al.o12", "scf.in"], ids=["a match", "no match"])
def test_a_subfolder_that_cannot_be_read_through_ssh(ssh_server, output):
    """The real rsync: its ``.`` line comes with or without a match, and the path says which."""
    server, remote = ssh_server
    locked = remote / "proj" / "locked"
    locked.mkdir(parents=True)
    (remote / "proj" / output).write_text("x")
    locked.chmod(0o000)
    try:
        found = list_outputs(parse_config(server.config_data()), str(remote / "proj"))
    finally:
        locked.chmod(0o755)
    assert isinstance(found, listing.Outputs), found
    assert found.found == ([output] if output == "Al.o12" else [])
    assert len(found.unread) == 1 and found.unread[0].endswith("proj/locked")
