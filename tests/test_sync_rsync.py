import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.project.project_data import PROJECT_DATA_EXCLUDE
from qe_studio.core.remote.failure import classify_failure
from qe_studio.core.remote.scratch import SCRATCH_EXCLUDE
from qe_studio.core.remote.trash_dir import TRASH_EXCLUDE
from qe_studio.core.sync import askpass, mux
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.remote_path import local_arg
from qe_studio.core.sync.rsync import (
    Endpoint,
    askpass_program,
    child_env,
    decode_rsync_name,
    dry_run_command,
    list_command,
    outputs_command,
    parse_delivered,
    parse_dry_run,
    parse_itemize_line,
    parse_progress,
    push_dry_run_command,
    push_transfer_command,
    remote_dir_for,
    small_files_command,
    ssh_command,
    transfer_command,
)
from qe_studio.core.sync.rsync_errors import (
    cause_line,
    dry_run_gaps,
    explain_failure,
    is_auth_failure,
    is_connection_failure,
    only_vanished,
)


def config(sync=None, **cluster):
    return parse_config(
        {
            "paths": {"local_root": "/data/sims", "remote_root": "/scratch/me/sims"},
            "cluster": {"host": "10.0.0.1", "user": "me", "port": 2222, **cluster},
            "sync": {"exclude": ["tmp/", "*.wfc*"], **(sync or {})},
        }
    )


def test_ssh_command_key_auth():
    argv = ssh_command(config(key_path="/k/id").cluster, "ssh")
    assert argv[:3] == ["ssh", "-p", "2222"]
    assert "BatchMode=yes" in argv and "IdentitiesOnly=yes" in argv
    assert argv[argv.index("-i") + 1] == "/k/id"
    assert "ServerAliveInterval=15" in argv and "ConnectTimeout=10" in argv


def test_ssh_command_password_auth():
    argv = ssh_command(config(auth="password").cluster, "ssh")
    assert "BatchMode=yes" not in argv
    assert "NumberOfPasswordPrompts=1" in argv


def test_the_shared_connection_comes_after_the_strict_host_key_check():
    """The master is born with every option of Lain, the host key check included (spec 72 R2)."""
    argv = ssh_command(config(key_path="/k/id").cluster, "ssh")
    folder = mux.control_dir()
    assert folder is not None
    assert argv[-6:] == [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={folder}/{os.getpid()}-%C",
        "-o",
        "ControlPersist=120",
    ]
    assert argv.index("StrictHostKeyChecking=yes") < argv.index("ControlMaster=auto")


@pytest.mark.parametrize(
    ("cluster", "auth"),
    [
        ({"key_path": "/k/id"}, ["-o", "BatchMode=yes", "-i", "/k/id", "-o", "IdentitiesOnly=yes"]),
        ({"auth": "password"}, ["-o", "NumberOfPasswordPrompts=1"]),
    ],
)
def test_without_multiplex_the_ssh_is_the_one_before_spec_72(cluster, auth):
    argv = ssh_command(config(multiplex=False, **cluster).cluster, "ssh")
    assert argv == [
        "ssh",
        "-p",
        "2222",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        *auth,
    ]


def has_option(argv, option):
    return any(a == "-o" and b == option for a, b in zip(argv, argv[1:], strict=False))


@pytest.mark.parametrize("cluster", [{"key_path": "/k/id"}, {"auth": "password"}])
def test_the_host_key_is_always_checked_strictly(cluster):
    """Lain forces it on the command line, so the user's ssh_config cannot loosen it (spec 27-3 R1)."""
    cfg = config(**cluster)
    remote = Endpoint("/scratch/me/sims/run", "10.0.0.1", "me")
    local = Path("/data/sims/run")
    assert has_option(ssh_command(cfg.cluster, "ssh"), "StrictHostKeyChecking=yes")
    for build in (dry_run_command, transfer_command, push_dry_run_command, push_transfer_command):
        argv = build(cfg, remote, local)
        shell = shlex.split(argv[argv.index("-e") + 1])
        assert has_option(shell, "StrictHostKeyChecking=yes"), build.__name__


def test_dry_run_command():
    cfg = config()
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    argv = dry_run_command(cfg, remote, Path("/data/sims/run 1"), (3, 2, 7))
    assert argv[:6] == ["rsync", "-n", "-rt", "--checksum", "-i", "--modify-window=1"]
    assert "--out-format=%i|%l|%M|%n" in argv
    assert "--exclude=tmp/" in argv and "--exclude=*.wfc*" in argv
    assert "--no-h" in argv and "--timeout=0" in argv  # the cluster hashes in silence
    assert argv[argv.index("-e") + 1].startswith("ssh -p 2222")
    assert argv[-2:] == ["me@10.0.0.1:'/scratch/me/sims/run 1'/", "/data/sims/run 1/"]
    assert "--old-args" in argv
    assert "--old-args" not in dry_run_command(cfg, remote, Path("/l"), (3, 1, 3))
    by_date = dry_run_command(config({"checksum": False}), remote, Path("/l"), (3, 2, 7))
    assert "--timeout=60" in by_date


def test_pull_dry_run_compares_content_by_default():
    argv = dry_run_command(config(), Endpoint("/scratch/me/sims", "10.0.0.1", "me"), Path("/d"))
    assert argv[argv.index("-rt") + 1] == "--checksum"  # spec 63 R1


def test_checksum_off_is_todays_command():
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    local = Path("/data/sims/run 1")
    on = dry_run_command(config(), remote, local, (3, 2, 7))
    off = dry_run_command(config({"checksum": False}), remote, local, (3, 2, 7))
    assert "--checksum" not in off
    assert off[:5] == ["rsync", "-n", "-rt", "-i", "--modify-window=1"]
    # The limit is all that differs: nothing arrives while the cluster hashes a file.
    same_limit = ["--timeout=60" if a == "--timeout=0" else a for a in on if a != "--checksum"]
    assert same_limit == off


def test_push_never_uses_checksum():
    cfg = config({"checksum": True})
    remote = Endpoint("/scratch/me/sims", "10.0.0.1", "me")
    for build in (push_dry_run_command, push_transfer_command):
        argv = build(cfg, remote, Path("/d"), (3, 2, 7))
        assert not any("checksum" in a or a == "-c" for a in argv), build.__name__
        assert "--ignore-times" not in argv, build.__name__


def test_the_pull_transfer_sends_what_the_plan_listed_whatever_the_date():
    remote = Endpoint("/scratch/me/sims", "10.0.0.1", "me")
    on = transfer_command(config(), remote, Path("/d"), (3, 2, 7))
    off = transfer_command(config({"checksum": False}), remote, Path("/d"), (3, 2, 7))
    assert "--ignore-times" in on and "--ignore-times" not in off
    assert [a for a in on if a != "--ignore-times"] == off


def test_transfer_command_reads_list_from_stdin():
    argv = transfer_command(config(), Endpoint("/r"), Path("/l"), (3, 2, 7))
    assert {"-t", "--info=progress2", "--files-from=-", "--from0"} <= set(argv)
    assert "-e" not in argv  # local endpoint
    assert not any(a.startswith("--exclude") for a in argv)
    assert argv[-2:] == ["/r/", "/l/"]


def test_child_env():
    base = {"PATH": "/usr/bin", "LANG": "pt_BR.UTF-8", askpass.SECRET_ENV: "stale"}
    env = child_env(config().cluster, base)
    assert env["LC_ALL"] == "C.UTF-8" and env["TZ"] == "UTC"
    assert askpass.SECRET_ENV not in env and "SSH_ASKPASS" not in env
    pw = child_env(config(auth="password").cluster, base, password="s3cret")
    assert pw[askpass.SECRET_ENV] == "s3cret"
    assert pw["SSH_ASKPASS_REQUIRE"] == "force"
    assert Path(pw["SSH_ASKPASS"]).exists()


def test_password_never_in_argv():
    cfg = config(auth="password", password="s3cret")
    remote = Endpoint("/r", "h", "u")
    for argv in (
        dry_run_command(cfg, remote, Path("/l")),
        transfer_command(cfg, remote, Path("/l")),
    ):
        assert not any("s3cret" in arg for arg in argv)


def test_askpass_program_prints_secret():
    env = {**os.environ, askpass.SECRET_ENV: "p@ss word"}
    out = subprocess.run([askpass_program(), "Password:"], env=env, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == "p@ss word\n"


def test_askpass_refuses_host_key_prompts(monkeypatch, capsys):
    monkeypatch.setenv(askpass.SECRET_ENV, "x")
    assert askpass.main(["Are you sure you want to continue connecting (yes/no)?"]) == 0
    assert capsys.readouterr().out == "no\n"
    monkeypatch.delenv(askpass.SECRET_ENV)
    assert askpass.main(["Password:"]) == 1


def test_parse_itemize_lines():
    item = parse_itemize_line(">f+++++++++|1234|2025/01/03-10:05:38|scf.out")
    assert (item.code, item.size, item.path) == (">f+++++++++", 1234, "scf.out")
    assert item.mtime == 1735898738.0
    piped = parse_itemize_line(">f.st......|5|2025/01/03-10:05:38|odd|name.out")
    assert piped.path == "odd|name.out"
    escaped = parse_itemize_line(
        ">f+++++++++|5|2025/01/03-10:05:38|Simula\\#303\\#247\\#303\\#265es/a"
    )
    assert escaped.path == "Simulações/a"
    assert parse_itemize_line("garbage") is None
    records = parse_dry_run(
        "cd+++++++++|4096|2025/01/03-10:05:38|orbitals/\n"
        ">f+++++++++|10|2025/01/03-10:05:38|orbitals/x\n"
        "cL+++++++++|3|2025/01/03-10:05:38|link\n"
    )
    assert [r.path for r in records] == ["orbitals/x"]


def test_decode_plain_name_untouched():
    assert decode_rsync_name("ação.out") == "ação.out"


def test_parse_progress():
    chunk = (
        "      32768   3%    0.00kB/s    0:00:00\r"
        "    1048576  45%   12,34MB/s    0:00:02 (xfr#3, to-chk=5/10)\r"
    )
    progress = parse_progress(chunk)
    assert (progress.percent, progress.files_done, progress.files_total) == (45, 5, 10)
    assert parse_progress("sending incremental file list\n") is None


@pytest.mark.parametrize(
    ("code", "stderr", "fragment"),
    [
        (
            255,
            "Host key verification failed.\r\nrsync: connection unexpectedly closed",
            "Chave do host",
        ),
        (255, "me@h: Permission denied (publickey,password).", "Autenticação recusada"),
        (255, "ssh: connect to host h port 22: Connection timed out", "inacessível"),
        (
            23,
            'rsync: [sender] change_dir "/x" failed: No such file or directory (2)',
            "não encontrada",
        ),
        (
            12,
            "rsync: connection unexpectedly closed (1048576 bytes received so far) [Receiver]\n"
            "rsync error: error in rsync protocol data stream (code 12)",
            "Conexão interrompida (o cluster encerrou",
        ),
        (
            12,
            "bash: rsync: command not found\nrsync: connection unexpectedly closed (0 bytes)",
            "rsync não está instalado",
        ),  # the real cause wins over rsync's last words
        (127, "sh: 1: rsync: not found", "rsync não está instalado"),  # dash
        (127, "rsync: Command not found.", "rsync não está instalado"),  # csh
        (12, "something odd\n", "código 12: something odd"),
        (  # a file rsync cannot read says "Permission denied" too, and is no refused login
            23,
            'rsync: [sender] opendir "/x" failed: Permission denied (13)\n'
            "rsync error: some files/attrs were not transferred (see previous errors) (code 23)",
            'código 23: rsync: [sender] opendir "/x" failed: Permission denied (13)',
        ),
        (  # the cause, not rsync's closing summary
            11,
            'rsync: [receiver] write failed on "/l/a": No space left on device (28)\n'
            "rsync error: error in file IO (code 11) at receiver.c(381)",
            "No space left on device",
        ),
    ],
)
def test_explain_failure(code, stderr, fragment):
    assert fragment in explain_failure(code, stderr)


def test_another_program_missing_is_not_rsync_missing():
    stderr = "bash: module: command not found\nrsync error: unexplained (code 2)"
    assert "rsync não está instalado" not in explain_failure(2, stderr)


@pytest.mark.parametrize(
    ("stderr", "lines"),
    [
        ("", ""),
        ("rsync error: x (code 1)\n", "rsync error: x (code 1)"),  # nothing else was said
        ("banner\nlast\nrsync error: x (code 1)", "last"),
        ('login noise\nrsync: "/a" first (13)\nrsync: "/b" then (32)\n', 'rsync: "/a" first (13)'),
    ],
)
def test_cause_line(stderr, lines):
    assert cause_line(stderr) == lines


@pytest.mark.parametrize(
    ("code", "stderr", "auth"),
    [
        (255, "me@h: Permission denied (publickey,password).", True),
        (255, "Host key verification failed.\nme@h: Permission denied", False),  # first cause wins
        (255, "ssh: connect to host h port 22: Connection timed out", False),
        (255, "", False),
        (23, 'rsync: [sender] opendir "/x" failed: Permission denied (13)', False),
        (11, 'rsync: mkstemp "/l/.a.XXXXXX" failed: Permission denied (13)', False),
    ],
)
def test_is_auth_failure(code, stderr, auth):
    assert is_auth_failure(code, stderr) is auth


def test_remote_dir_for(tmp_path):
    cfg = parse_config({"paths": {"local_root": str(tmp_path), "remote_root": "/scratch/me/sims"}})
    (tmp_path / "a" / "4 DOS").mkdir(parents=True)
    assert remote_dir_for(tmp_path / "a" / "4 DOS", cfg) == "/scratch/me/sims/a/4 DOS"
    assert remote_dir_for(tmp_path, cfg) == "/scratch/me/sims"
    with pytest.raises(ValueError, match="não está dentro"):
        remote_dir_for(Path(sys.prefix), cfg)


def test_endpoint_spec():
    assert Endpoint("/r/x/").spec() == "/r/x/"
    assert Endpoint("/r/x", "h").spec() == "h:/r/x/"
    assert Endpoint("/r/x", "h", "u").spec() == "u@h:/r/x/"


@pytest.mark.parametrize(
    ("code", "stderr", "expected"),
    [
        (255, "ssh: connect to host h port 22: Connection timed out", True),
        (255, "ssh: Could not resolve hostname h", True),
        (255, "me@h: Permission denied (publickey).", False),
        (255, "Host key verification failed.", False),  # the cluster answered
        (23, 'rsync: change_dir "/x" failed: No such file or directory (2)', False),
        (30, "rsync error: timeout in data send/receive (code 30)", True),
        (12, "rsync: connection unexpectedly closed (1048576 bytes received so far)", True),
        (12, "bash: rsync: command not found\nrsync: connection unexpectedly closed (0 b)", False),
        (12, "Permission denied (publickey).\nrsync: connection unexpectedly closed (0 b)", False),
    ],
)
def test_connection_failure_classification(code, stderr, expected):
    assert is_connection_failure(code, stderr) is expected


def test_a_refused_host_key_keeps_its_hint_in_a_cluster_command():
    failure = classify_failure(CommandResult(255, "", "Host key verification failed.\n"), "qstat")
    assert "Chave do host" in failure.message and not failure.connection and not failure.auth


@pytest.mark.parametrize(
    ("code", "stderr", "gaps"),
    [
        (24, 'file has vanished: "/x/a"\n', ()),
        (23, 'rsync: [sender] opendir "/x/sub" failed: Permission denied (13)', ("/x/sub",)),
        (23, 'rsync: [sender] link_stat "/x/a" failed: No such file or directory (2)', ()),
        (23, 'rsync: [sender] change_dir "/x" failed: Permission denied (13)', None),  # the root
        (23, 'rsync: [sender] change_dir "/x" failed: No such file or directory (2)', None),
        (23, 'rsync: [sender] opendir "/x/." failed: Permission denied (13)', None),  # the root
        (23, "rsync: something this code has never seen", None),
        (23, "", None),
        (12, 'rsync: [sender] opendir "/x/sub" failed: Permission denied (13)', None),
    ],
)
def test_dry_run_gaps(code, stderr, gaps):
    assert dry_run_gaps(code, stderr) == gaps


@pytest.mark.parametrize(
    ("code", "stderr", "expected"),
    [
        (24, 'file has vanished: "/x/a"\n', True),
        (23, 'rsync: [sender] link_stat "/x/a" failed: No such file or directory (2)', True),
        (23, 'rsync: [sender] send_files failed to open "/x/a": Permission denied (13)', False),
        (23, "", False),
        (12, 'rsync: [sender] link_stat "/x/a" failed: No such file or directory (2)', False),
    ],
)
def test_only_vanished(code, stderr, expected):
    assert only_vanished(code, stderr) is expected


def test_a_name_that_is_not_utf8_keeps_its_bytes():
    name = decode_rsync_name("caf\\#351.in")
    assert name.encode("utf-8", "surrogateescape") == b"caf\xe9.in"


def test_parse_delivered():
    output = (
        "sent|sub/\n"  # a folder it created: not one of the files
        "sent|a.out\n      1000  50%    1.00MB/s    0:00:01 (xfr#1, to-chk=1/2)\r"
        "sent|caf\\#351.in\nsent|a.out\n"
    )
    assert parse_delivered(output, ["a.out", "caf\udce9.in", "never.out"]) == [
        "a.out",
        "caf\udce9.in",
    ]


def test_a_delivered_name_is_never_read_as_progress():
    assert parse_progress("sent|run 50% done.in\n") is None
    assert parse_progress("0%.in\n") is None  # the end of a name cut by a read


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("/data/sims/run 1", "/data/sims/run 1/"),
        ("/data/sims/", "/data/sims/"),
        ("C:\\Users\\me\\Lain", "/cygdrive/c/Users/me/Lain/"),
        ("d:/runs/a", "/cygdrive/d/runs/a/"),
        ("C:\\", "/cygdrive/c/"),
    ],
)
def test_local_arg(folder, expected):
    assert local_arg(folder, "/cygdrive") == expected


def test_local_arg_for_msys2():
    assert local_arg("C:\\Users\\me", "") == "/c/Users/me/"


def test_the_commands_take_the_cygdrive_prefix_from_the_config():
    argv = dry_run_command(
        config({"cygdrive_prefix": "/mnt"}), Endpoint("/r", "h", "u"), Path("/l"), (3, 2, 7)
    )
    assert argv[-1] == "/l/"  # not a drive path: left alone
    argv = small_files_command(config(), "/r", "C:\\tmp\\x", (3, 2, 7))  # type: ignore[arg-type]
    assert argv[-1] == "/cygdrive/c/tmp/x/"


def test_the_askpass_wrapper_is_repaired_when_it_cannot_run():
    wrapper = Path(askpass_program())
    wrapper.chmod(0o600)
    assert askpass_program() == str(wrapper)
    assert os.access(wrapper, os.X_OK)


# -- push (spec 27 R1) ----------------------------------------------------------------------------
FORBIDDEN = (
    "--delete",
    "--remove-source-files",
    "--remove-sent-files",
    "-u",
    "--update",
    "--inplace",
)


def no_forbidden(argv: list[str]) -> bool:
    """No option that deletes, updates or rewrites in place what the cluster has."""
    return not any(arg.split("=")[0] in FORBIDDEN or arg.startswith("--del") for arg in argv)


def test_push_dry_run_goes_from_the_local_folder_and_lists_existing_files_too():
    cfg = config()
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    argv = push_dry_run_command(cfg, remote, Path("/data/sims/run 1"), (3, 2, 7))
    assert argv[:5] == ["rsync", "-n", "-rt", "-i", "--modify-window=1"]
    assert "--out-format=%i|%l|%M|%n" in argv
    assert argv[-2:] == ["/data/sims/run 1/", "me@10.0.0.1:'/scratch/me/sims/run 1'/"]
    assert "--ignore-existing" not in argv  # the preview names what the cluster already has
    assert not any(a.startswith("--rsync-path") for a in argv)  # nothing made before "Enviar"
    excludes = [a for a in argv if a.startswith("--exclude=")]
    assert excludes == [
        "--exclude=.lain/",  # the root's settings folder, always first (spec 48 R5)
        "--exclude=tmp_remote/",  # the scratch copies of remote plots (spec 66 R2.2)
        "--exclude=tmp/",  # no trash: a folder below the root (spec 84 R3.1)
        "--exclude=*.wfc*",
        "--exclude=plots/",
        "--exclude=*.plot",
    ]
    assert no_forbidden(argv)


def test_the_settings_folder_is_excluded_even_with_empty_lists():
    """``sync.exclude`` and ``push_exclude`` are replaced whole when edited: the settings folder of
    the root is excluded by the code, not by the lists (spec 48 R5.2)."""
    cfg = parse_config(
        {
            "paths": {"local_root": "/data/sims", "remote_root": "/scratch/me/sims"},
            "cluster": {"host": "10.0.0.1", "user": "me"},
            "sync": {"exclude": [], "push_exclude": []},
        }
    )
    remote = Endpoint("/scratch/me/sims", "10.0.0.1", "me")
    for command in (dry_run_command, push_dry_run_command):
        argv = command(cfg, remote, Path("/data/sims"), (3, 2, 7))
        assert [a for a in argv if a.startswith("--exclude")] == [
            f"--exclude={PROJECT_DATA_EXCLUDE}",
            f"--exclude={SCRATCH_EXCLUDE}",
            f"--exclude={TRASH_EXCLUDE}",
        ]
    assert PROJECT_DATA_EXCLUDE == ".lain/"


def test_the_trash_is_never_synced():
    """Spec 84 R3.1: the cluster's trash never comes down in a pull of the root, nor goes up, whatever
    the lists say; the pattern is anchored to the root of the transfer."""
    remote = Endpoint("/scratch/me/sims", "10.0.0.1", "me")
    for command in (dry_run_command, push_dry_run_command):
        argv = command(config(), remote, Path("/data/sims"), (3, 2, 7))
        assert argv.index("--exclude=tmp_remote/") < argv.index("--exclude=/trash/")
        assert "--exclude=trash/" not in argv


@pytest.mark.parametrize("folder", ["/scratch/me/sims/proj", "/scratch/me/sims/trash", "/scratch"])
def test_a_folder_named_trash_below_the_root_is_the_users(folder):
    """Only a transfer of ``remote_root`` itself leaves the trash out: in a project, a subfolder or
    the trash itself (a "Baixar" of it), these commands take a ``trash`` folder like any other.
    ``prepare_push`` is what refuses to send into the cluster's trash."""
    remote = Endpoint(folder, "10.0.0.1", "me")
    for command in (dry_run_command, push_dry_run_command):
        argv = command(config(), remote, Path("/data/sims/x"), (3, 2, 7))
        assert not [a for a in argv if a.startswith("--exclude") and "trash" in a], argv


def test_tmp_remote_is_never_synced():
    """Spec 66 R2.2: the scratch copy of a remote plot never goes up (an upload of its folder) nor
    comes down (a ``tmp_remote`` on the cluster), whatever the lists say."""
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    for command in (dry_run_command, push_dry_run_command):
        argv = command(config(), remote, Path("/data/sims/run 1"), (3, 2, 7))
        assert "--exclude=tmp_remote/" in argv
        assert argv.index("--exclude=tmp_remote/") < argv.index("--exclude=tmp/")
    assert SCRATCH_EXCLUDE == "tmp_remote/"


def test_push_transfer_only_adds_files():
    cfg = config()
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    argv = push_transfer_command(cfg, remote, Path("/data/sims/run 1"), (3, 2, 7), ["--x"])
    assert argv[:8] == [
        "rsync",
        "-t",
        "--info=progress2",
        "--out-format=sent|%n",
        "--files-from=-",
        "--from0",
        "--ignore-existing",
        "--omit-dir-times",
    ]
    assert argv[-3:] == ["--x", "/data/sims/run 1/", "me@10.0.0.1:'/scratch/me/sims/run 1'/"]
    assert no_forbidden(argv) and "-r" not in argv
    assert argv[argv.index("-e") + 1].startswith("ssh -p 2222")


@pytest.mark.parametrize("folder", ["/scratch/me/sims/run 1", "/scratch/me/it's here", '/s/a"b'])
def test_push_makes_the_remote_folder_with_a_quoted_path(folder):
    argv = push_transfer_command(config(), Endpoint(folder, "10.0.0.1", "me"), Path("/d"))
    (rsync_path,) = [a for a in argv if a.startswith("--rsync-path=")]
    command = rsync_path.removeprefix("--rsync-path=")
    assert command == f"mkdir -p {shlex.quote(folder)} && rsync"
    assert shlex.split(command) == ["mkdir", "-p", folder, "&&", "rsync"]


@pytest.mark.parametrize(
    ("folder", "word"),
    [
        ("~/runs/proj", "~/runs/proj"),
        ("~/my runs/proj", "~/'my runs/proj'"),
        ("~", "~"),
        ("~me/runs", "~me/runs"),
        ("/home/me/~/x", "'/home/me/~/x'"),  # only a leading one
        ("~x;y/runs", "'~x;y/runs'"),
    ],
)
def test_push_leaves_a_leading_tilde_to_the_shell(folder, word):
    """rsync leaves a leading ``~`` of the remote path unescaped, so the cluster's shell makes it the
    home: the ``mkdir -p`` before it must name the same folder, not one called ``~``."""
    argv = push_transfer_command(config(), Endpoint(folder, "10.0.0.1", "me"), Path("/d"))
    (rsync_path,) = [a for a in argv if a.startswith("--rsync-path=")]
    assert rsync_path == f"--rsync-path=mkdir -p {word} && rsync"


OLD_CLIENT = (3, 2, 3)  # the last that needs ``--protect-args``
NEW_CLIENTS = [(3, 2, 4), (3, 4, 1), (3, 5, 0), None]  # None: unknown, treated as new
TILDE_COMMANDS = [
    dry_run_command,
    transfer_command,
    push_dry_run_command,
    push_transfer_command,
]


@pytest.mark.parametrize("version", [OLD_CLIENT, *NEW_CLIENTS])
@pytest.mark.parametrize(
    ("folder", "word"),
    [
        ("~/runs/proj", "~/runs/proj"),
        ("~/my runs/proj", "~/'my runs/proj'"),
        ("~", "~"),
        ("~me/runs", "~me/runs"),
    ],
)
def test_a_leading_tilde_is_left_to_the_shell_on_every_client(folder, word, version):
    """Protected arguments (``--protect-args``, or the default of rsync 3.2.4 and later) hide the
    path from the cluster's shell, and then ``~`` is a folder called ``~``: an old client goes
    without ``--protect-args``, a new one gets ``--old-args``."""
    remote = Endpoint(folder, "10.0.0.1", "me")
    spec = f"me@10.0.0.1:{word}/"
    new = version != OLD_CLIENT
    for command in TILDE_COMMANDS:
        argv = command(config(), remote, Path("/d"), version)
        assert "--protect-args" not in argv, command.__name__
        assert ("--old-args" in argv) is new, command.__name__
        assert spec in argv, command.__name__
    for argv in (
        list_command(config(), folder, version),
        outputs_command(config(), folder, version),
        small_files_command(config(), folder, Path("/d"), version),
    ):
        assert "--protect-args" not in argv
        assert ("--old-args" in argv) is new
        assert any(a.endswith(f":{word}/") for a in argv), argv


@pytest.mark.parametrize("command", TILDE_COMMANDS)
def test_every_remote_path_is_quoted_for_the_cluster_s_shell(command):
    """So its ``*``, ``?`` and ``[`` stay literal: ``--protect-args`` leaves them to the remote
    rsync, which expands them, and rsync 3.2.4's default to the shell."""
    plain = Endpoint("/scratch/run[1]/~/x", "10.0.0.1", "me")  # only a leading ``~`` is the shell's
    spec = "me@10.0.0.1:'/scratch/run[1]/~/x'/"
    old = command(config(), plain, Path("/d"), OLD_CLIENT)
    assert "--protect-args" not in old and "--old-args" not in old and spec in old
    for version in NEW_CLIENTS:
        new = command(config(), plain, Path("/d"), version)
        assert "--protect-args" not in new and "--old-args" in new and spec in new
    for version in NEW_CLIENTS:  # a local path: no ssh, no shell
        local = command(config(), Endpoint("~/x"), Path("/d"), version)
        assert "--protect-args" not in local and "--old-args" not in local
        assert "~/x/" in local
