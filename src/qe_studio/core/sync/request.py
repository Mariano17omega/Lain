"""Whether a pull (PRD §5) or a push (spec 27) can start, and from where: checked before any
dialog or process. The scope's wording (spec 17 R1) is here too: the Rsync button, the menu and the
dialog say it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..config import AppConfig
from .rsync import Endpoint, remote_dir_for

NOT_CONFIGURED = (
    "Configure cluster.host, cluster.user e paths.remote_root no config.yaml para sincronizar."
)
SYNC_OFF = "Sincronização desligada: configure cluster.host, cluster.user e paths.remote_root"
PUSH_ROOT = "Escolha uma pasta de cálculo; o projeto inteiro não é enviado."
MENU_PATH_MAX = 40  # longer relative paths keep their end in the menu text


class Direction(StrEnum):
    PULL = "pull"  # cluster → computer
    PUSH = "push"  # computer → cluster, new files only (spec 27)


@dataclass(frozen=True)
class SyncRequest:
    folder: Path
    endpoint: Endpoint
    needs_password: bool  # auth: password without one in the config: ask (once per session)


@dataclass(frozen=True)
class PushRequest(SyncRequest):
    """A push of one calculation folder (never the whole project)."""


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


def prepare_push(config: AppConfig, folder: Path) -> PushRequest | SyncRefusal:
    """The push of ``folder`` (spec 27 R4.1): like a pull's, but never of the project root (an
    accidental push of everything) and only of a folder that exists."""
    request = prepare_sync(config, folder)
    if isinstance(request, SyncRefusal):
        return request
    path = Path(folder)
    if path.resolve() == config.paths.local_root.resolve():
        return SyncRefusal("warning", PUSH_ROOT)
    if not path.is_dir():
        return SyncRefusal("warning", f"Pasta não encontrada: {path}")
    return PushRequest(request.folder, request.endpoint, request.needs_password)


def push_availability(config: AppConfig, folder: Path) -> str:
    """ "" when ``folder`` can be pushed, else why not (the tooltip of the disabled menu item)."""
    request = prepare_push(config, folder)
    if not isinstance(request, SyncRefusal):
        return ""
    return SYNC_OFF if request.message == NOT_CONFIGURED else request.message


@dataclass(frozen=True)
class SyncScope:
    """What a pull (or a push) of one folder covers, in words."""

    relative: str  # the folder relative to the project root, "" for the root itself
    remote: str = ""  # Endpoint.spec() of its cluster side; "" when it has none
    enabled: bool = True
    direction: Direction = Direction.PULL

    @property
    def push(self) -> bool:
        return self.direction is Direction.PUSH

    @property
    def whole_project(self) -> bool:
        return not self.relative

    @property
    def available(self) -> bool:
        """Whether it can start: sync on and, for a push, not the whole project."""
        return self.enabled and not (self.push and self.whole_project)

    @property
    def label(self) -> str:
        return "projeto inteiro" if self.whole_project else f"{self.relative} (e subpastas)"

    @property
    def title(self) -> str:
        if self.push:
            return f"Enviar para o cluster: {self.label}"
        return f"Baixar do cluster: {self.label}"

    @property
    def tooltip(self) -> str:
        if not self.enabled:
            return SYNC_OFF
        return PUSH_ROOT if self.push and self.whole_project else self.title

    @property
    def menu_text(self) -> str:
        if self.push:
            if self.whole_project:
                return "Enviar pasta ao cluster…"
            return f"Enviar {_elide_start(self.relative, MENU_PATH_MAX)} ao cluster…"
        if self.whole_project:
            return "Sincronizar projeto inteiro"
        return f"Sincronizar {_elide_start(self.relative, MENU_PATH_MAX)}"

    @property
    def window_title(self) -> str:
        return "Enviando para o cluster" if self.push else "Sincronizando com o cluster"

    @property
    def confirm_text(self) -> str:
        """The preview's button that starts the transfer."""
        return "Enviar" if self.push else "Baixar"

    @property
    def local_text(self) -> str:
        return self.relative or "."


def sync_scope(
    config: AppConfig,
    folder: Path,
    endpoint: Endpoint | None = None,
    direction: Direction = Direction.PULL,
) -> SyncScope:
    """The scope of pulling (or pushing) ``folder``; ``endpoint`` (of a run already prepared)
    wins over the one the config gives."""
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
    return SyncScope(relative, remote, config.sync_enabled, direction)


def _elide_start(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…" + text[-(limit - 1) :]
