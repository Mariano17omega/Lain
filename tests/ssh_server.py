"""A local SSH server (paramiko) standing in for the cluster in sync tests (spec 7, R7).

It listens on ``127.0.0.1`` and serves a temp folder as the "remote" side: ``exec`` requests run
as local subprocesses (``rsync --server …`` is what rsync sends), so the **real** ``ssh`` and
``rsync`` binaries and the options ``core/sync/rsync.py`` builds are exercised end to end.

Only a short allowlist of commands runs (``rsync --server …``, ``true``, ``echo``); anything else
gets exit status 127 and is logged, never executed. No SFTP, no shell, no pty: Lain only uses
``exec``. The one compound command is a push's ``mkdir -p <dir> && rsync --server …`` (spec 27,
``--rsync-path``): ``<dir>`` is made in Python, only inside the served folder, then rsync runs.

The ``ssh`` client never reads the real ``~/.ssh`` (OpenSSH uses the passwd home, not ``$HOME``):
``LocalSSHServer.ssh_binary()`` writes a throwaway ``ssh_config`` and ``known_hosts`` and returns
the value for ``sync.ssh_binary`` (``"ssh -F <tmp>/ssh_config"``).
"""

from __future__ import annotations

import contextlib
import os
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import paramiko

USER = "lain-test"
PASSWORD = "lain-test-password"
HOST_ALIAS = "lain-test-host"
PROBE_COMMANDS = ("true", "echo")
CHUNK = 32768

KnownHosts = Literal["server", "empty", "other"]
Strict = Literal["yes", "ask", "no", "accept-new"]  # the test ssh_config may be permissive


@dataclass
class ServerKeys:
    """Key material shared by a whole test session (RSA generation is not free)."""

    host_key: paramiko.PKey
    other_host_key: paramiko.PKey  # what a "changed host key" looks like
    client_key: paramiko.PKey
    client_key_path: Path

    @classmethod
    def generate(cls, directory: Path) -> ServerKeys:
        directory.mkdir(parents=True, exist_ok=True)
        client = paramiko.RSAKey.generate(2048)
        path = directory / "client_key"
        client.write_private_key_file(str(path))
        path.chmod(0o600)  # ssh refuses keys readable by others
        return cls(paramiko.RSAKey.generate(2048), paramiko.RSAKey.generate(2048), client, path)


@dataclass(frozen=True)
class AuthAttempt:
    user: str
    method: str  # publickey | password
    accepted: bool


@dataclass
class ExecRecord:
    """One ``exec`` request: who ran what, how they authenticated and how it ended."""

    user: str
    method: str  # authentication method that opened the connection
    command: str
    status: int | None = None  # exit status sent to the client; None = connection dropped
    allowed: bool = True


@dataclass
class _Session:
    user: str = ""
    method: str = ""


class _Transport(paramiko.Transport):
    """Lets the exec worker wait until paramiko has sent "request ok" for its channel.

    paramiko replies to ``exec`` only after ``check_channel_exec_request`` returns, and a worker
    started from there can finish first (a refused command does): its exit status and close
    would reach the client before the reply, which ssh and paramiko both treat as a failure.
    """

    def __init__(self, sock: socket.socket):
        super().__init__(sock)
        self._acks: dict[int, threading.Event] = {}
        self._acks_lock = threading.Lock()

    def ack_event(self, chanid: int) -> threading.Event:
        with self._acks_lock:
            return self._acks.setdefault(chanid, threading.Event())

    def _send_user_message(self, data) -> None:
        super()._send_user_message(data)
        raw = data.asbytes()
        if raw[:1] == bytes([paramiko.common.MSG_CHANNEL_SUCCESS]):
            self.ack_event(int.from_bytes(raw[1:5], "big")).set()


class _Interface(paramiko.ServerInterface):
    def __init__(self, server: LocalSSHServer):
        self.server = server
        self.session = _Session()

    def get_allowed_auths(self, username: str) -> str:
        return "publickey,password"

    def check_auth_password(self, username: str, password: str) -> int:
        accepted = (
            not self.server.reject_auth and username == USER and password == self.server.password
        )
        self.server._attempt(AuthAttempt(username, "password", accepted))
        if accepted:
            self.session = _Session(username, "password")
        return paramiko.AUTH_SUCCESSFUL if accepted else paramiko.AUTH_FAILED

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        accepted = (
            not self.server.reject_auth
            and username == USER
            and key.asbytes() == self.server.keys.client_key.asbytes()
        )
        self.server._attempt(AuthAttempt(username, "publickey", accepted))
        if accepted:
            self.session = _Session(username, "publickey")
        return paramiko.AUTH_SUCCESSFUL if accepted else paramiko.AUTH_FAILED

    def check_channel_request(self, kind: str, chanid: int) -> int:
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        # Runs on the transport thread: only hand the work to a thread of its own.
        text = command.decode("utf-8", "surrogateescape")
        self.server._spawn(self.server._serve_exec, channel, text, self.session)
        return True


class LocalSSHServer:
    """Threaded paramiko server. ``drop_after_bytes``, ``reject_auth`` and ``stall_banner`` are
    failure modes a test switches on before connecting."""

    def __init__(self, root: Path, keys: ServerKeys, workdir: Path):
        self.root = root
        self.keys = keys
        self.workdir = workdir
        self.password = PASSWORD
        self.reject_auth = False
        self.stall_banner = False
        self.drop_after_bytes: int | None = None
        self.log: list[ExecRecord] = []
        self.attempts: list[AuthAttempt] = []
        self._lock = threading.Lock()
        self._closing = threading.Event()
        self._threads: list[threading.Thread] = []
        self._transports: list[paramiko.Transport] = []
        self._procs: list[subprocess.Popen] = []
        self._held: list[socket.socket] = []  # sockets of stalled connections
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(16)
        self._listener.settimeout(0.2)  # close() does not wake a blocked accept(): poll instead
        self.host = "127.0.0.1"
        self.port: int = self._listener.getsockname()[1]
        self._spawn(self._accept_loop)

    # -- client side helpers -------------------------------------------------------------------
    def ssh_binary(
        self,
        known_hosts: KnownHosts = "server",
        strict: Strict = "yes",
        auth: Literal["key", "password"] = "key",
    ) -> str:
        """``sync.ssh_binary`` value: ssh pinned to a temp ``ssh_config`` (never ``~/.ssh``)."""
        hosts = self.workdir / "known_hosts"
        key = {"server": self.keys.host_key, "other": self.keys.other_host_key}.get(known_hosts)
        hosts.write_text(
            f"[{self.host}]:{self.port} {key.get_name()} {key.get_base64()}\n" if key else ""
        )
        config = self.workdir / "ssh_config"
        config.write_text(
            f"Host {HOST_ALIAS}\n"
            f"  HostName {self.host}\n"
            f"  Port {self.port}\n"
            f"  UserKnownHostsFile {hosts}\n"
            "  GlobalKnownHostsFile /dev/null\n"
            f"  StrictHostKeyChecking {strict}\n"
            "  UpdateHostKeys no\n"
            # No default identities, no agent: only what the test passes (-i) is offered.
            f"  IdentityFile {self.workdir / 'no_such_identity'}\n"
            "  IdentityAgent none\n"
            f"  PreferredAuthentications {'publickey' if auth == 'key' else 'password'}\n"
        )
        return f"ssh -F {shlex.quote(str(config))}"

    def config_data(
        self,
        known_hosts: KnownHosts = "server",
        strict: Strict = "yes",
        auth: Literal["key", "password"] = "key",
        **cluster,
    ) -> dict:
        """Config dict (``parse_config`` input) pointing Lain at this server."""
        settings = {
            "host": HOST_ALIAS,
            "port": self.port,
            "user": USER,
            "auth": auth,
            "connect_timeout": 5,
        }
        if auth == "key":
            settings["key_path"] = str(self.keys.client_key_path)
        settings.update(cluster)
        return {
            "paths": {"remote_root": str(self.root)},
            "cluster": settings,
            "sync": {"ssh_binary": self.ssh_binary(known_hosts, strict, auth)},
        }

    # -- inspection ----------------------------------------------------------------------------
    def commands(self, allowed_only: bool = True) -> list[str]:
        with self._lock:
            return [r.command for r in self.log if r.allowed or not allowed_only]

    def alive_threads(self) -> list[str]:
        with self._lock:
            threads = [*self._threads, *self._transports]
        return [t.name for t in threads if t.is_alive()]

    # -- lifecycle -----------------------------------------------------------------------------
    def close(self, timeout: float = 5.0) -> None:
        self._closing.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        deadline = time.monotonic() + timeout
        while True:
            # Re-read every round: a connection that is being served can still start workers.
            with self._lock:
                transports, procs, held = (
                    list(self._transports),
                    list(self._procs),
                    list(self._held),
                )
                pending = [t for t in [*self._threads, *transports] if t.is_alive()]
            for proc in procs:
                if proc.poll() is None:
                    proc.kill()
            for transport in transports:
                transport.close()
            for sock in held:
                sock.close()
            if not pending or time.monotonic() > deadline:
                return
            for thread in pending:
                thread.join(0.05)

    def __enter__(self) -> LocalSSHServer:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- internals -----------------------------------------------------------------------------
    def _spawn(self, target, *args) -> threading.Thread:
        thread = threading.Thread(
            target=target, args=args, daemon=True, name=f"lain-ssh-{target.__name__.strip('_')}"
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()
        return thread

    def _attempt(self, attempt: AuthAttempt) -> None:
        with self._lock:
            self.attempts.append(attempt)

    def _accept_loop(self) -> None:
        while not self._closing.is_set():
            try:
                sock, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            sock.settimeout(None)
            if self.stall_banner:  # TCP is up, the SSH banner never comes
                with self._lock:
                    self._held.append(sock)
                continue
            self._spawn(self._serve_connection, sock)

    def _serve_connection(self, sock: socket.socket) -> None:
        transport = _Transport(sock)
        transport.add_server_key(self.keys.host_key)
        with self._lock:
            self._transports.append(transport)
        try:
            transport.start_server(server=_Interface(self))
            while transport.is_active() and not self._closing.is_set():
                transport.join(0.2)
        except (paramiko.SSHException, EOFError, OSError):
            pass  # client gave up during the handshake (host key refused, probe, timeout)
        finally:
            transport.close()

    def _serve_exec(self, channel: paramiko.Channel, command: str, session: _Session) -> None:
        try:
            argv = shlex.split(command)
        except ValueError:
            argv = []
        mkdir = None
        if argv[:2] == ["mkdir", "-p"] and argv[3:4] == ["&&"]:  # a push's --rsync-path
            mkdir, argv = self._inside_root(argv[2]), argv[4:]
            allowed = mkdir is not None and argv[:2] == ["rsync", "--server"]
        else:
            allowed = argv[:2] == ["rsync", "--server"] or bool(argv and argv[0] in PROBE_COMMANDS)
        record = ExecRecord(session.user, session.method, command, allowed=allowed)
        channel.get_transport().ack_event(channel.remote_chanid).wait(5)
        with self._lock:
            self.log.append(record)
        try:
            if not allowed:
                channel.send_stderr(f"lain-test: command not allowed: {command}\n".encode())
                record.status = 127
                channel.send_exit_status(127)
                return
            if mkdir is not None:
                mkdir.mkdir(parents=True, exist_ok=True)
            record.status = self._run(channel, argv)
            if record.status is not None:
                channel.send_exit_status(record.status)
        except (OSError, EOFError, paramiko.SSHException):
            pass  # client went away mid-command
        finally:
            channel.close()

    def _inside_root(self, folder: str) -> Path | None:
        """``folder`` (relative ones from the served folder), or None when it lies outside it."""
        root = self.root.resolve()
        path = (root / folder).resolve()
        return path if path.is_relative_to(root) else None

    def _run(self, channel: paramiko.Channel, argv: list[str]) -> int | None:
        """Run ``argv`` in the served folder wired to ``channel``. None = dropped on purpose."""
        proc = subprocess.Popen(
            argv,
            cwd=self.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with self._lock:
            self._procs.append(proc)
        feeder = self._spawn(self._feed_stdin, channel, proc)
        errors = self._spawn(self._forward_stderr, channel, proc)
        sent = 0
        limit = self.drop_after_bytes
        assert proc.stdout is not None
        while data := os.read(proc.stdout.fileno(), CHUNK):
            if limit is not None and sent + len(data) >= limit:
                channel.sendall(data[: limit - sent])
                proc.kill()  # the "cable is pulled": no exit status, no goodbye
                proc.wait()
                return None
            channel.sendall(data)
            sent += len(data)
        code = proc.wait()
        errors.join(5)
        feeder.join(0.1)  # blocked in recv until the client closes; the channel close frees it
        return code

    @staticmethod
    def _feed_stdin(channel: paramiko.Channel, proc: subprocess.Popen) -> None:
        assert proc.stdin is not None
        try:
            while data := channel.recv(CHUNK):
                proc.stdin.write(data)
                proc.stdin.flush()
        except (OSError, EOFError, ValueError):  # process gone or channel closed
            pass
        finally:
            with contextlib.suppress(OSError):
                proc.stdin.close()

    @staticmethod
    def _forward_stderr(channel: paramiko.Channel, proc: subprocess.Popen) -> None:
        assert proc.stderr is not None
        try:
            while data := os.read(proc.stderr.fileno(), CHUNK):
                channel.sendall_stderr(data)
        except (OSError, EOFError, paramiko.SSHException):
            pass
