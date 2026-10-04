"""Whether a pull can start, and from where (PRD §5): checked before any dialog or process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from .rsync import Endpoint, remote_dir_for

NOT_CONFIGURED = (
    "Configure cluster.host, cluster.user e paths.remote_root no config.yaml para sincronizar."
)


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
