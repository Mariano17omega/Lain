"""The sides of a sync in a command. ``Endpoint`` is the cluster's: ``remote_arg`` gives its path as the
cluster's shell reads it, quoted but for a leading ``~`` or ``~user``, which only the shell can make a
home, and ``shell_path`` the same word for a folder alone. The path always goes through that shell, so
``*``, ``?`` and ``[`` in a name stay literal: rsync's own protection does not cover them
(``--protect-args`` leaves them to the remote rsync, which expands them, and the default of 3.2.4 and
later leaves them to the shell). A client of 3.2.4 or later gets ``--old-args``, so that it does not
escape our quotes; an older one needs nothing. ``local_arg`` is the computer's side. Pure: nothing
runs."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, replace
from pathlib import Path

_HOME = re.compile(r"^~(?:[A-Za-z0-9_][A-Za-z0-9._-]*)?(?=/|$)")  # ``~`` or ``~user``, then ``/``
_DRIVE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$", re.DOTALL)  # ``C:\Users\me``


@dataclass(frozen=True)
class Endpoint:
    """Remote side of a sync. ``host=None`` means a local path (used by tests)."""

    path: str
    host: str | None = None
    user: str | None = None

    def spec(self) -> str:
        path = self.path.rstrip("/") + "/"
        if self.host is None:
            return path
        login = f"{self.user}@{self.host}" if self.user else self.host
        return f"{login}:{path}"


def shell_path(path: str) -> str:
    """``path`` as one word of the cluster's shell: ``~/my runs`` → ``~/'my runs'``."""
    home = _HOME.match(path)
    if home is None:
        return shlex.quote(path)
    rest = path[home.end() + 1 :]
    return home.group() + ("/" + shlex.quote(rest) if rest else "")


def _old_client(version: tuple[int, ...] | None) -> bool:
    """A local rsync that passes remote arguments to the shell as they are."""
    return version is not None and version < (3, 2, 4)


def old_args(remote: Endpoint, version: tuple[int, ...] | None) -> bool:
    """Whether the rsync of ``version`` needs ``--old-args`` to send ``remote_arg``'s quotes to the
    cluster's shell as they are (an unknown version counts as a new client)."""
    return remote.host is not None and not _old_client(version)


def remote_arg(remote: Endpoint, version: tuple[int, ...] | None) -> str:
    """The cluster side of a command: ``remote.spec()``, quoted for the shell that reads the path."""
    if remote.host is None:
        return remote.spec()
    return replace(remote, path=shell_path(remote.path.rstrip("/"))).spec()


def local_arg(folder: Path | str, cygdrive_prefix: str) -> str:
    """The computer's side of a command, ending in ``/``. rsync takes ``C:\\Users`` for a host called
    ``C``: a drive path goes in the form of the Cygwin-based Windows builds, ``/cygdrive/c/Users/``
    (``cygdrive_prefix`` is ``sync.cygdrive_prefix``)."""
    text = str(folder).rstrip("/\\")
    drive = _DRIVE.match(text)
    if drive is None:
        return text + "/"
    rest = drive[2].replace("\\", "/")
    return f"{cygdrive_prefix}/{drive[1].lower()}/{rest}".rstrip("/") + "/"
