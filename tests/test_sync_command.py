"""A command on the cluster other than rsync (spec 64 R1): ``run_command`` returns the output and
the code, kills its child at the time limit or when its task is cancelled; ``remote_command`` is
ssh with Lain's options."""

import os
import sys
import time

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.sync.command import remote_command, run_command
from qe_studio.core.tasks import run_task


def sleeper(pidfile) -> list[str]:
    """A child that writes its pid, then sleeps for 30 s."""
    code = f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(30)"
    return [sys.executable, "-c", code]


def wait_pid(pidfile, timeout=10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pidfile.exists() and (text := pidfile.read_text()):
            return int(text)
        time.sleep(0.02)
    raise AssertionError("the child never started")


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_output_and_code_of_a_local_command():
    code = "import sys; print('olá'); print('erro', file=sys.stderr); sys.exit(3)"
    result = run_command([sys.executable, "-c", code], dict(os.environ), 30)
    assert (result.code, result.stdout, result.stderr) == (3, "olá\n", "erro\n")
    assert not result.timed_out


def test_undecodable_bytes_are_kept():
    code = "import sys; sys.stdout.buffer.write(b'a\\xffb')"
    result = run_command([sys.executable, "-c", code], dict(os.environ), 30)
    assert result.code == 0 and result.stdout == "a\udcffb"


def test_the_time_limit_kills_the_child(tmp_path):
    pidfile = tmp_path / "pid"
    began = time.monotonic()
    result = run_command(sleeper(pidfile), dict(os.environ), 1.0)
    assert result.timed_out and result.code is None
    assert time.monotonic() - began < 5
    assert gone(wait_pid(pidfile))


def test_cancelling_the_task_kills_the_child_at_once(qtbot, tmp_path):
    pidfile = tmp_path / "pid"
    results = []
    handle = run_task(run_command, sleeper(pidfile), dict(os.environ), 60, on_done=results.append)
    pid = wait_pid(pidfile)
    began = time.monotonic()
    handle.cancel()
    assert handle.wait(1.0)
    assert time.monotonic() - began < 1.0
    assert gone(pid)
    qtbot.wait(50)
    assert results == []  # a cancelled task never calls back


def test_a_program_that_does_not_exist_raises():
    with pytest.raises(OSError):
        run_command(["/no/such/ssh"], dict(os.environ), 5)


def test_the_remote_command_is_ssh_with_the_options_of_lain():
    config = parse_config(
        {"cluster": {"host": "hpc.example", "user": "me", "port": 2222, "connect_timeout": 7}}
    )
    argv = remote_command(config, "qstatus -a")
    assert argv[0] == "ssh" and argv[-2:] == ["me@hpc.example", "qstatus -a"]
    for option in ("StrictHostKeyChecking=yes", "ConnectTimeout=7", "BatchMode=yes"):
        assert option in argv
    assert argv[argv.index("-p") + 1] == "2222"
