"""Whether a pull can start, and from where (PRD §5): checked before any dialog or process. The
scope's wording (spec 17 R1) is here too: the Rsync button, the menu and the dialog say it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from .rsync import Endpoint, remote_dir_for

NOT_CONFIGURED = (
    "Configure cluster.host, cluster.user e paths.remote_root no config.yaml para sincronizar."
)
SYNC_OFF = "Sincronização desligada: configure cluster.host, cluster.user e paths.remote_root"
MENU_PATH_MAX = 40  # longer relative paths keep their end in the menu text


@dataclass(frozen=True)
class SyncRequest:
    folder: Path
    endpoint: Endpoint
    needs_password: bool  # auth: password without one in the config: ask (once per session)


@dataclass(frozen=True)
class SyncRefusal:
    level: str  # "info": sync is not configured; "warning": this folder cannot be synced
    message: str


def prepare_sync(config: AppConfig, folder: Path) -> SyncRequest | SyncRefusal:
    """The pull of ``folder`` (the whole project when it is the root), or why there is none."""
    if not config.sync_enabled:
        return SyncRefusal("info", NOT_CONFIGURED)
    try:
        remote_dir = remote_dir_for(folder, config)
    except ValueError as exc:
        return SyncRefusal("warning", str(exc))
    cluster = config.cluster
    needs_password = cluster.auth == "password" and cluster.resolve_password() is None
    return SyncRequest(
        Path(folder), Endpoint(remote_dir, cluster.host, cluster.user), needs_password
    )


@dataclass(frozen=True)
class SyncScope:
    """What a pull of one folder covers, in words."""

    relative: str  # the folder relative to the project root, "" for the root itself
    remote: str = ""  # Endpoint.spec() of its cluster side; "" when it has none
    enabled: bool = True

    @property
    def whole_project(self) -> bool:
        return not self.relative

    @property
    def label(self) -> str:
        return "projeto inteiro" if self.whole_project else f"{self.relative} (e subpastas)"

    @property
    def title(self) -> str:
        return f"Baixar do cluster: {self.label}"

    @property
    def tooltip(self) -> str:
        return self.title if self.enabled else SYNC_OFF

    @property
    def menu_text(self) -> str:
        if self.whole_project:
            return "Sincronizar projeto inteiro"
        return f"Sincronizar {_elide_start(self.relative, MENU_PATH_MAX)}"

    @property
    def local_text(self) -> str:
        return self.relative or "."


def sync_scope(config: AppConfig, folder: Path, endpoint: Endpoint | None = None) -> SyncScope:
    """The scope of pulling ``folder``; ``endpoint`` (of a run already prepared) wins over the
    one the config gives."""
    root = config.paths.local_root.resolve()
    resolved = Path(folder).resolve()
    if resolved.is_relative_to(root):
        relative = resolved.relative_to(root).as_posix()
        relative = "" if relative == "." else relative
    else:
        relative = str(folder)  # prepare_sync refuses it: still say which folder it is
    if endpoint is None:
        request = prepare_sync(config, folder)
        endpoint = request.endpoint if isinstance(request, SyncRequest) else None
    remote = endpoint.spec() if endpoint is not None else ""
    return SyncScope(relative, remote, config.sync_enabled)


def _elide_start(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…" + text[-(limit - 1) :]
