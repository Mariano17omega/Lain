"""``install.sh`` on a terminal: the portrait, the colors and the arrow-key menus.

The script runs on a pseudo-terminal with ``--config-only``, in a temp folder: nothing is installed
or contacted. ``test_install_script.py`` covers the run without a terminal, which stays plain.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")
fcntl = pytest.importorskip("fcntl")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.sh"
EXAMPLE = ROOT / "config.example.yaml"
SYSTEM_PATH = "/usr/bin:/bin"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="install.sh needs bash")

DOWN = "\x1b[B"
ENTER = "\r"
COLOR = "\x1b[38;5;"
SHOW_CURSOR = "\x1b[?25h"
HIDE_CURSOR = "\x1b[?25l"
PORTRAIT_CHAR = "⣿"

# (what the script has shown, what to type then), in the order it asks.
Dialog = list[tuple[str, str]]

PATHS: Dialog = [
    ("paths.local_root", "\r"),
    ("Create it?", "y"),
    ("paths.remote_root", "\r"),
    ("paths.xcrysden_path", "\r"),
    ("paths.data", "\r"),
    ("cluster.host", "cluster.example\r"),
    ("cluster.port", "\r"),
    ("cluster.user", "alice\r"),
]
TYPED_PATHS: Dialog = [(seen, "y\r" if typed == "y" else typed) for seen, typed in PATHS]
KEY_AND_EMAIL: Dialog = [("cluster.key_path", "\r"), ("jobs.myemail", "\r")]


class Terminal:
    """install.sh on a pseudo-terminal, driven by what it shows."""

    def __init__(
        self, tmp_path: Path, env: dict[str, str] | None, args: tuple[str, ...], piped: bool
    ):
        self.checkout = tmp_path / "lain"
        self.checkout.mkdir()
        shutil.copyfile(EXAMPLE, self.checkout / "config.example.yaml")
        home = tmp_path / "home"
        home.mkdir()
        self.master, self.slave = pty.openpty()
        full_env = {
            "HOME": str(home),
            "PATH": SYSTEM_PATH,
            "LANG": "C.UTF-8",
            "TERM": "xterm-256color",
            **(env or {}),
        }
        # Piped, as `curl ... | bash`: the script comes on stdin, the answers from /dev/tty.
        program = ["bash", "-s", "--"] if piped else ["bash", str(SCRIPT)]
        self.process = subprocess.Popen(
            [*program, "--config-only", str(self.checkout), *args],
            stdin=subprocess.PIPE if piped else self.slave,
            stdout=self.slave,
            stderr=self.slave,
            env=full_env,
            cwd=tmp_path,
            start_new_session=True,
            preexec_fn=self._take_terminal,
        )
        if piped:
            assert self.process.stdin is not None
            self.process.stdin.write(SCRIPT.read_bytes())
            self.process.stdin.close()
        self.output = ""
        self.seen_up_to = 0

    def _take_terminal(self) -> None:
        fcntl.ioctl(self.slave, termios.TIOCSCTTY, 0)

    def pump(self, seconds: float = 0.05) -> bool:
        """Reads what is ready; False once the terminal has nothing more to give."""
        ready, _, _ = select.select([self.master], [], [], seconds)
        if not ready:
            return True
        try:
            data = os.read(self.master, 65536)
        except OSError:
            return False
        self.output += data.decode("utf-8", "replace")
        return bool(data)

    def wait_for(self, text: str, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.output.find(text, self.seen_up_to)
            if found >= 0:
                self.seen_up_to = found + len(text)
                return
            self.pump()
        raise AssertionError(f"never showed {text!r}; output:\n{self.output}")

    def type(self, keys: str) -> None:
        time.sleep(0.05)  # the script's read is set up after the prompt shows
        os.write(self.master, keys.encode())

    def talk(self, dialog: Dialog) -> None:
        for seen, keys in dialog:
            self.wait_for(seen)
            self.type(keys)

    def finish(self) -> int:
        deadline = time.monotonic() + 15
        while self.process.poll() is None and time.monotonic() < deadline:
            self.pump()
        while select.select([self.master], [], [], 0.05)[0]:
            if not self.pump():
                break
        assert self.process.poll() is not None, self.output
        return self.process.returncode

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        os.close(self.master)
        os.close(self.slave)

    def config(self) -> str:
        return (self.checkout / "config.yaml").read_text(encoding="utf-8")


@pytest.fixture
def terminal(tmp_path):
    opened: list[Terminal] = []

    def start(
        env: dict[str, str] | None = None, args: tuple[str, ...] = (), piped: bool = False
    ) -> Terminal:
        opened.append(Terminal(tmp_path, env, args, piped))
        return opened[-1]

    yield start
    for each in opened:
        each.close()


def test_a_terminal_gets_the_portrait_colors_and_a_box(terminal):
    run = terminal()
    run.talk([*PATHS, ("cluster.auth", ENTER), *KEY_AND_EMAIL])
    assert run.finish() == 0, run.output
    assert PORTRAIT_CHAR in run.output
    assert COLOR in run.output
    assert "Lain: QE Studio" in run.output
    shown = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", run.output)
    assert "╭─ config.yaml" in shown  # the top of the box
    assert '  host: "cluster.example"' in run.config()
    assert "auth: key" in run.config()
    assert run.output.count(HIDE_CURSOR) == run.output.count(SHOW_CURSOR)


def test_a_piped_script_gets_the_menus_from_the_terminal(terminal):
    run = terminal(piped=True)
    run.talk([*PATHS, ("cluster.auth", DOWN)])
    run.type(ENTER)
    run.talk([("jobs.myemail", "\r")])
    assert run.finish() == 0, run.output
    assert PORTRAIT_CHAR in run.output
    assert "auth: password" in run.config()


def test_arrow_down_picks_the_password_login(terminal):
    run = terminal()
    run.talk([*PATHS, ("cluster.auth", DOWN)])
    run.type(ENTER)
    run.talk([("jobs.myemail", "\r")])
    assert run.finish() == 0, run.output
    assert "auth: password" in run.config()
    assert "QE_STUDIO_SSH_PASSWORD" in run.output


def test_the_first_letter_picks_an_option(terminal, tmp_path):
    run = terminal()
    dialog = [(seen, "n" if seen == "Create it?" else keys) for seen, keys in PATHS]
    run.talk([*dialog, ("cluster.auth", "p"), ("jobs.myemail", "\r")])
    assert run.finish() == 0, run.output
    assert "auth: password" in run.config()
    assert not (tmp_path / "home" / "Documentos" / "LUCCI").exists()  # "n": not created


def test_no_color_keeps_the_menus_without_colors(terminal):
    run = terminal(env={"NO_COLOR": "1"})
    run.talk([*PATHS, ("cluster.auth", ENTER), *KEY_AND_EMAIL])
    assert run.finish() == 0, run.output
    assert COLOR not in run.output
    assert PORTRAIT_CHAR in run.output


def test_plain_is_ascii_with_typed_answers(terminal):
    run = terminal(args=("--plain",))
    run.talk([*TYPED_PATHS, ("cluster.auth", "password\r"), ("jobs.myemail", "\r")])
    assert run.finish() == 0, run.output
    assert run.output.isascii()
    assert "\x1b" not in run.output
    assert "auth: password" in run.config()


def test_a_terminal_without_utf8_stays_ascii(terminal):
    run = terminal(env={"LANG": "C"})
    run.talk([*PATHS, ("cluster.auth", ENTER), *KEY_AND_EMAIL])
    assert run.finish() == 0, run.output
    assert run.output.isascii()
    assert COLOR in run.output


def test_ctrl_c_in_a_menu_restores_the_terminal(terminal):
    run = terminal()
    run.talk(PATHS[:1])
    run.wait_for("Create it?")
    run.wait_for(HIDE_CURSOR)
    time.sleep(0.1)
    os.killpg(run.process.pid, signal.SIGINT)
    assert run.finish() == 130, run.output
    assert "Installation interrupted." in run.output
    assert run.output.rfind(SHOW_CURSOR) > run.output.rfind(HIDE_CURSOR)
    assert termios.tcgetattr(run.master)[3] & termios.ECHO  # the keys show again
    assert sorted(p.name for p in run.checkout.iterdir()) == ["config.example.yaml"]
