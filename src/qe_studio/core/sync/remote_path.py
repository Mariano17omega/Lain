"""A path of the cluster in a command: the remote side of a sync (``Endpoint``), and that path as the
cluster's shell reads it, quoted but for a leading ``~`` or ``~user``, which only the shell can make a
home. rsync leaves that tilde unescaped, so ``shell_path`` names the folder rsync names; an old client's
``--protect-args`` hides the path from the shell, so a path like this goes without that option. Pure:
nothing runs."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, replace

_HOME = re.compile(r"^~(?:[A-Za-z0-9_][A-Za-z0-9._-]*)?(?=/|$)")  # ``~`` or ``~user``, then ``/``


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
    """A local rsync that does not protect remote arguments by itself."""
    return version is not None and version < (3, 2, 4)


def _home_for_shell(remote: Endpoint, version: tuple[int, ...] | None) -> bool:
    """A leading ``~`` on an old client: with ``--protect-args``, rsync would look for a folder called
    ``~``."""
    return _old_client(version) and remote.host is not None and _HOME.match(remote.path) is not None


def protect_args(remote: Endpoint, version: tuple[int, ...] | None) -> bool:
    """Whether the rsync of ``version`` needs ``--protect-args`` for ``remote``."""
    return _old_client(version) and not _home_for_shell(remote, version)


def remote_arg(remote: Endpoint, version: tuple[int, ...] | None) -> str:
    """The cluster side of a command: ``remote.spec()``, quoted when the shell reads the path."""
    if not _home_for_shell(remote, version):
        return remote.spec()
    return replace(remote, path=shell_path(remote.path.rstrip("/"))).spec()
