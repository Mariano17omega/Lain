import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.project_data import PROJECT_DATA_EXCLUDE
from qe_studio.core.sync import askpass
from qe_studio.core.sync.rsync import (
    Endpoint,
    askpass_program,
    child_env,
    decode_rsync_name,
    dry_run_command,
    explain_failure,
    is_auth_failure,
    parse_dry_run,
    parse_itemize_line,
    parse_progress,
    push_dry_run_command,
    push_transfer_command,
    remote_dir_for,
    ssh_command,
    transfer_command,
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
    assert "--no-h" in argv and "--timeout=60" in argv
    assert argv[argv.index("-e") + 1].startswith("ssh -p 2222")
    assert argv[-2:] == ["me@10.0.0.1:/scratch/me/sims/run 1/", "/data/sims/run 1/"]
    assert "--protect-args" not in argv
    assert "--protect-args" in dry_run_command(cfg, remote, Path("/l"), (3, 1, 3))


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
    assert [a for a in on if a != "--checksum"] == off


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
    ("stderr", "fragment"),
    [
        ("Host key verification failed.\r\nrsync: connection unexpectedly closed", "Chave do host"),
        ("me@h: Permission denied (publickey,password).", "Autenticação recusada"),
        ("ssh: connect to host h port 22: Connection timed out", "inacessível"),
        ('rsync: [sender] change_dir "/x" failed: No such file or directory (2)', "não encontrada"),
        (
            "rsync: connection unexpectedly closed (1048576 bytes received so far) [Receiver]\n"
            "rsync error: error in rsync protocol data stream (code 12)",
            "Conexão interrompida (o cluster encerrou",
        ),
        (
            "bash: rsync: command not found\nrsync: connection unexpectedly closed (0 bytes)",
            "rsync não está instalado",
        ),  # the real cause wins over rsync's last words
        ("something odd\n", "código 12: something odd"),
    ],
)
def test_explain_failure(stderr, fragment):
    assert fragment in explain_failure(12, stderr)


@pytest.mark.parametrize(
    ("stderr", "auth"),
    [
        ("me@h: Permission denied (publickey,password).", True),
        ("Host key verification failed.\nme@h: Permission denied", False),  # the first cause wins
        ("ssh: connect to host h port 22: Connection timed out", False),
        ("", False),
    ],
)
def test_is_auth_failure(stderr, auth):
    assert is_auth_failure(stderr) is auth


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
        (23, 'rsync: change_dir "/x" failed: No such file or directory (2)', False),
        (30, "rsync error: timeout in data send/receive (code 30)", True),
        (12, "rsync: connection unexpectedly closed (1048576 bytes received so far)", True),
        (12, "bash: rsync: command not found\nrsync: connection unexpectedly closed (0 b)", False),
        (12, "Permission denied (publickey).\nrsync: connection unexpectedly closed (0 b)", False),
    ],
)
def test_connection_failure_classification(code, stderr, expected):
    from qe_studio.core.sync.rsync import is_connection_failure

    assert is_connection_failure(code, stderr) is expected


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
    assert argv[-2:] == ["/data/sims/run 1/", "me@10.0.0.1:/scratch/me/sims/run 1/"]
    assert "--ignore-existing" not in argv  # the preview names what the cluster already has
    assert not any(a.startswith("--rsync-path") for a in argv)  # nothing made before "Enviar"
    excludes = [a for a in argv if a.startswith("--exclude=")]
    assert excludes == [
        "--exclude=.lain/",  # the root's settings folder, always first (spec 48 R5)
        "--exclude=tmp/",
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
            f"--exclude={PROJECT_DATA_EXCLUDE}"
        ]
    assert PROJECT_DATA_EXCLUDE == ".lain/"


def test_push_transfer_only_adds_files():
    cfg = config()
    remote = Endpoint("/scratch/me/sims/run 1", "10.0.0.1", "me")
    argv = push_transfer_command(cfg, remote, Path("/data/sims/run 1"), (3, 2, 7), ["--x"])
    assert argv[:7] == [
        "rsync",
        "-t",
        "--info=progress2",
        "--files-from=-",
        "--from0",
        "--ignore-existing",
        "--omit-dir-times",
    ]
    assert argv[-3:] == ["--x", "/data/sims/run 1/", "me@10.0.0.1:/scratch/me/sims/run 1/"]
    assert no_forbidden(argv) and "-r" not in argv
    assert argv[argv.index("-e") + 1].startswith("ssh -p 2222")


@pytest.mark.parametrize("folder", ["/scratch/me/sims/run 1", "/scratch/me/it's here", '/s/a"b'])
def test_push_makes_the_remote_folder_with_a_quoted_path(folder):
    argv = push_transfer_command(config(), Endpoint(folder, "10.0.0.1", "me"), Path("/d"))
    (rsync_path,) = [a for a in argv if a.startswith("--rsync-path=")]
    command = rsync_path.removeprefix("--rsync-path=")
    assert command == f"mkdir -p {shlex.quote(folder)} && rsync"
    assert shlex.split(command) == ["mkdir", "-p", folder, "&&", "rsync"]


def test_a_local_push_has_no_rsync_path():
    argv = push_transfer_command(config(), Endpoint("/tmp/cluster"), Path("/d"))
    assert not any(a.startswith("--rsync-path") for a in argv) and "-e" not in argv


def test_push_password_never_in_argv(monkeypatch):
    monkeypatch.setenv("LAIN_PUSH_PW", "s3cr3t-pw")
    cfg = config(auth="password", password_env="LAIN_PUSH_PW")
    remote = Endpoint("/scratch/me/sims", "10.0.0.1", "me")
    for build in (push_dry_run_command, push_transfer_command):
        assert not any("s3cr3t-pw" in arg for arg in build(cfg, remote, Path("/d"), (3, 2, 7)))


def test_push_itemize_codes_are_files():
    sent = parse_itemize_line("<f+++++++++|3|2023/11/14-22:13:20|run/a b.in")
    changed = parse_itemize_line("<f.st......|9|2023/11/14-22:13:20|scf.out")
    folder = parse_itemize_line("cd+++++++++|0|2023/11/14-22:13:20|run")
    assert sent is not None and sent.is_file and sent.path == "run/a b.in"
    assert changed is not None and changed.is_file
    assert folder is not None and not folder.is_file
