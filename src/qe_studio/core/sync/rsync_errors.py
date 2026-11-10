"""What a failed rsync or ssh said: its cause in the user's words, and whether what it did is still
worth using. Reads the English stderr of ssh and rsync (``child_env`` sets the locale). Pure."""

from __future__ import annotations

import errno
import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from ...i18n import _

SSH_FAILED = 255  # ssh's code, and rsync's when the remote shell failed (a refused login, say)
PARTIAL = 23  # rsync's code when the source could not be read
VANISHED = 24  # rsync's code when some files vanished while they were copied

AUTH_DENIED = "Permission denied"
HOST_KEY = "Host key verification failed"
NO_REMOTE_RSYNC = _("rsync não está instalado no cluster.")

FAILURE_HINTS = (
    (HOST_KEY, _("Chave do host desconhecida. Conecte-se uma vez pelo "
     "terminal (ssh usuario@host) para confirmar a identidade do cluster.")),
    (AUTH_DENIED, _("Autenticação recusada pelo cluster (verifique usuário, chave ou senha).")),
    ("Could not resolve hostname", _("Endereço do cluster não encontrado (verifique cluster.host).")),
    ("Connection timed out", _("Cluster inacessível (tempo de conexão esgotado).")),
    ("Connection refused", _("Conexão recusada pelo cluster (verifique a porta SSH).")),
    ("No route to host", _("Cluster inacessível (sem rota; verifique a rede/VPN).")),
    ("Network is unreachable", _("Rede indisponível.")),
    ("No such file or directory", _("Pasta não encontrada no cluster.")),
    ("timeout in data send/receive", _("Conexão interrompida (sem resposta do cluster).")),
)  # fmt: skip

# rsync's last words when the stream ends early. It also trails real causes (host key refused,
# authentication, rsync missing on the cluster), so it only counts when nothing explains the failure.
INTERRUPTED = "connection unexpectedly closed"

CONNECTION_NEEDLES = (
    "Connection timed out",
    "Connection refused",
    "No route to host",
    "Network is unreachable",
    "Could not resolve hostname",
    "timeout in data send/receive",
    "Connection closed",
)

# bash ("qsub: command not found"), dash ("qsub: not found") and csh ("qsub: Command not found.")
_NOT_FOUND = re.compile(r"([^\s:]+): (?:command )?not found", re.IGNORECASE)
# rsync's ``opendir "<path>" failed: <why> (<errno>)``, ``readdir("<path>"): <why> (<errno>)``,
# ``send_files failed to open "<path>": <why> (<errno>)`` and the like
_FAILED = re.compile(r'"(.+)"\)?(?: failed)?: .*\((\d+)\)\s*$')
_TRAILER = "rsync error:"  # rsync's summary of a failure, always after the line that says why
_ROOT_UNREAD = "change_dir"  # only the folder of the command is entered this way


def not_found(stderr: str, programs: Iterable[str]) -> str:
    """Which of ``programs`` the cluster's shell could not find; "" when none. Another program
    missing (a login script's ``module``, say) says nothing about this command."""
    wanted = set(programs)
    names = (PurePosixPath(match[1]).name for match in _NOT_FOUND.finditer(stderr))
    return next((name for name in names if name in wanted), "")


def _first_cause(stderr: str) -> tuple[str, str] | None:
    """The first known cause (its needle and hint) found in ``stderr``."""
    cause = next(((needle, hint) for needle, hint in FAILURE_HINTS if needle in stderr), None)
    if cause is None and not_found(stderr, ("rsync",)):
        return "rsync", NO_REMOTE_RSYNC
    return cause


def known_cause(stderr: str) -> str | None:
    """The explanation of the first known cause found in ``stderr`` (ssh's, or rsync's), if any."""
    cause = _first_cause(stderr)
    return cause[1] if cause is not None else None


def is_auth_failure(exit_code: int, stderr: str) -> bool:
    """The cluster refused the credentials (the remembered password is then wrong): ssh's own code
    and the authentication as the first known cause. rsync says "Permission denied" for a file it
    cannot read too, with another code, and that says nothing about the password."""
    cause = _first_cause(stderr)
    return exit_code == SSH_FAILED and cause is not None and cause[0] == AUTH_DENIED


def is_connection_failure(exit_code: int, stderr: str) -> bool:
    """ssh could not reach/keep the cluster (as opposed to a remote error). A refused login or host
    key means that the cluster answered."""
    return (
        any(needle in stderr for needle in CONNECTION_NEEDLES)
        or (exit_code == SSH_FAILED and AUTH_DENIED not in stderr and HOST_KEY not in stderr)
        or (INTERRUPTED in stderr and _first_cause(stderr) is None)
    )


def cause_line(stderr: str) -> str:
    """The line of ``stderr`` that says what went wrong: rsync's first complaint (what follows it is
    its consequence), else the last line other than rsync's closing summary."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    first = next((line for line in lines if line.startswith("rsync: ")), None)
    if first is not None:
        return first
    return next((ln for ln in reversed(lines) if not ln.startswith(_TRAILER)), "".join(lines[-1:]))


def explain_failure(exit_code: int, stderr: str) -> str:
    cause = _first_cause(stderr)
    if cause is not None and (cause[0] != AUTH_DENIED or exit_code == SSH_FAILED):
        return cause[1]
    if INTERRUPTED in stderr:
        return _("Conexão interrompida (o cluster encerrou a conexão durante a transferência).")
    last = cause_line(stderr)
    return _("rsync terminou com código {exit_code}").format(exit_code=exit_code) + (
        f": {last}" if last else "."
    )


def read_failures(stderr: str) -> tuple[list[tuple[str, int]], bool]:
    """What rsync says it could not read: ``(path, errno)`` per failure, and whether one of its
    lines could not be understood. Failures count by their number: the cluster's rsync may speak
    another language."""
    failures = []
    unknown = False
    for line in stderr.splitlines():
        if match := _FAILED.search(line):
            failures.append((match[1], int(match[2])))
        elif line.startswith("rsync: "):
            unknown = True
    return failures, unknown


def unread_paths(code: int | None, stderr: str) -> tuple[str, ...] | None:
    """What a walk that ended with code 23 or 24 could not read; one path that vanished during it is
    not among them. None when it cannot be told: another code, nothing says what failed, or a
    failure could not be understood."""
    if code not in (PARTIAL, VANISHED):
        return None
    failures, unknown = read_failures(stderr)
    if unknown or (code == PARTIAL and not failures):
        return None
    return tuple(dict.fromkeys(path for path, number in failures if number != errno.ENOENT))


def dry_run_gaps(code: int, stderr: str) -> tuple[str, ...] | None:
    """What a dry run with code 23 or 24 left out of its listing, the rest of which is good. None
    when the run failed: as ``unread_paths``, or the folder itself could not be read."""
    failures, _unknown = read_failures(stderr)
    if _ROOT_UNREAD in stderr or any(path.endswith("/.") for path, _number in failures):
        return None
    return unread_paths(code, stderr)


def only_vanished(code: int, stderr: str) -> bool:
    """A transfer's only problem was files gone from the source: code 24, or the 23 of a name of
    ``--files-from`` that no longer exists."""
    if code == VANISHED:
        return True
    failures, unknown = read_failures(stderr)
    return (
        code == PARTIAL
        and bool(failures)
        and not unknown
        and all(number == errno.ENOENT for _path, number in failures)
    )
