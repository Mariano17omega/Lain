"""Whether a pull (PRD §5), a push (spec 27) or the copy of a remote plot (spec 66) can start, and
from where: checked before any dialog or process. The scope's wording (spec 17 R1) is here too: the Rsync button, the menu and the
dialog say it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...i18n import _
from ..config import AppConfig
from ..scratch import SCRATCH_DIR, scratch_of
from .rsync import Endpoint, remote_dir_for, remote_dir_of

NOT_CONFIGURED = _(
    "Configure cluster.host, cluster.user e paths.remote_root no config.yaml para sincronizar."
)
SYNC_OFF = _("Sincronização desligada: configure cluster.host, cluster.user e paths.remote_root")
PUSH_ROOT = _("Escolha uma pasta de cálculo; a pasta raiz inteira não é enviada.")
PUSH_PROJECT = _("Escolha uma pasta de cálculo; o projeto inteiro não é enviado.")  # spec 31 R5.2
SYNC_RUNNING = _("Há uma sincronização em andamento. Espere terminar ou cancele.")
PLOT_ROOT = _("Escolha uma pasta de cálculo para plotar; a raiz não é copiada.")  # spec 66 R3.1
PLOT_PROJECT = _("Escolha uma pasta de cálculo para plotar; o projeto inteiro não é copiado.")
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
    """A push of one calculation folder (never the root nor a whole project)."""


@dataclass(frozen=True)
class SyncRefusal:
    level: str  # "info": sync is not configured; "warning": this folder cannot be synced
    message: str


def prepare_sync(
    config: AppConfig, folder: Path, *, resolved_root: Path | None = None
) -> SyncRequest | SyncRefusal:
    """The pull of ``folder`` (the whole project when it is the root), or why there is none.

    ``resolved_root``: ``paths.local_root.resolve()`` when the caller keeps it (here and below)."""
    if not config.sync_enabled:
        return SyncRefusal("info", NOT_CONFIGURED)
    try:
        remote_dir = remote_dir_for(folder, config, resolved_root=resolved_root)
    except ValueError as exc:
        return SyncRefusal("warning", str(exc))
    cluster = config.cluster
    needs_password = cluster.auth == "password" and cluster.resolve_password() is None
    return SyncRequest(
        Path(folder), Endpoint(remote_dir, cluster.host, cluster.user), needs_password
    )


def prepare_push(
    config: AppConfig, folder: Path, *, resolved_root: Path | None = None
) -> PushRequest | SyncRefusal:
    """The push of ``folder`` (spec 27 R4.1): like a pull's, but never of the root nor of a project
    (a first-level folder: an accidental push of everything) and only of a folder that exists."""
    root = _root(config, resolved_root)
    request = prepare_sync(config, folder, resolved_root=root)
    if isinstance(request, SyncRefusal):
        return request
    path = Path(folder)
    resolved = path.resolve()
    if resolved == root:
        return SyncRefusal("warning", PUSH_ROOT)
    if not path.is_dir():
        return SyncRefusal("warning", _("Pasta não encontrada: {path}").format(path=path))
    if resolved.parent == root:
        return SyncRefusal("warning", PUSH_PROJECT)
    return PushRequest(request.folder, request.endpoint, request.needs_password)


def prepare_scratch(
    config: AppConfig, mirror: Path, *, resolved_root: Path | None = None
) -> SyncRequest | SyncRefusal:
    """The copy of ``mirror``'s cluster side into ``mirror/tmp_remote``, to plot it (spec 66 R3.1):
    the request's folder is the copy, its endpoint the mirror's. Like a push, never of the root
    nor of a project (it would copy every calculation). ``mirror`` need not exist yet."""
    root = _root(config, resolved_root)
    request = prepare_sync(config, mirror, resolved_root=root)
    if isinstance(request, SyncRefusal):
        return request
    resolved = Path(mirror).resolve()
    if resolved == root:
        return SyncRefusal("warning", PLOT_ROOT)
    if resolved.parent == root:
        return SyncRefusal("warning", PLOT_PROJECT)
    return SyncRequest(scratch_of(request.folder), request.endpoint, request.needs_password)


def push_availability(config: AppConfig, folder: Path, *, resolved_root: Path | None = None) -> str:
    """ "" when ``folder`` can be pushed, else why not (the tooltip of the disabled menu item)."""
    request = prepare_push(config, folder, resolved_root=resolved_root)
    if not isinstance(request, SyncRefusal):
        return ""
    return SYNC_OFF if request.level == "info" else request.message


@dataclass(frozen=True)
class SyncScope:
    """What a pull (or a push) of one folder covers, in words."""

    relative: str  # the folder relative to the root folder, "" for the root itself
    remote: str = ""  # Endpoint.spec() of its cluster side; "" when it has none
    enabled: bool = True
    direction: Direction = Direction.PULL
    project: str = ""  # the project's name when this is what "Sincronizar projeto" covers (spec 31)
    file: str = ""  # the one file of the folder a "Baixar" of the cluster mode pulls (spec 65 R5.2)
    scratch: bool = False  # the copy of the folder into its ``tmp_remote/``, to plot it (spec 66)

    @property
    def push(self) -> bool:
        return self.direction is Direction.PUSH

    @property
    def whole_project(self) -> bool:
        """The root folder itself: everything ("Todos os projetos")."""
        return not self.relative

    @property
    def at_project(self) -> bool:
        """A first-level folder of the root: a project (spec 31)."""
        return bool(self.relative) and "/" not in self.relative

    @property
    def available(self) -> bool:
        """Whether it can start: sync on and, for a push, neither the root nor a project."""
        return self.enabled and not (self.push and (self.whole_project or self.at_project))

    @property
    def label(self) -> str:
        if self.file:
            return self.local_text
        if self.whole_project:
            return _("tudo")
        if self.project:
            return _("projeto {project}").format(project=self.project)
        return _("{relative} (e subpastas)").format(relative=self.relative)

    @property
    def title(self) -> str:
        if self.scratch:
            return _("Baixando para plotar: {label}").format(label=self.label)
        if self.push:
            return _("Enviar para o cluster: {label}").format(label=self.label)
        return _("Baixar do cluster: {label}").format(label=self.label)

    @property
    def tooltip(self) -> str:
        if not self.enabled:
            return SYNC_OFF
        if self.push and self.whole_project:
            return PUSH_ROOT
        return PUSH_PROJECT if self.push and self.at_project else self.title

    @property
    def menu_text(self) -> str:
        if self.push:
            if self.whole_project or self.at_project:
                return _("Enviar pasta ao cluster…")
            return _("Enviar {elide_start} ao cluster…").format(
                elide_start=_elide_start(self.relative, MENU_PATH_MAX)
            )
        if self.whole_project:
            return _("Sincronizar tudo")
        if self.project:
            return _("Sincronizar projeto {project}").format(project=self.project)
        return _("Sincronizar {elide_start}").format(
            elide_start=_elide_start(self.relative, MENU_PATH_MAX)
        )

    @property
    def window_title(self) -> str:
        return _("Enviando para o cluster") if self.push else _("Sincronizando com o cluster")

    @property
    def confirm_text(self) -> str:
        """The preview's button that starts the transfer."""
        return _("Enviar") if self.push else _("Baixar")

    @property
    def local_text(self) -> str:
        if self.scratch:
            return f"{self.relative}/{SCRATCH_DIR}" if self.relative else SCRATCH_DIR
        if self.file:
            return f"{self.relative}/{self.file}" if self.relative else self.file
        return self.relative or "."


def sync_scope(
    config: AppConfig,
    folder: Path,
    endpoint: Endpoint | None = None,
    direction: Direction = Direction.PULL,
    *,
    resolved_root: Path | None = None,
    project: str = "",
) -> SyncScope:
    """The scope of pulling (or pushing) ``folder``; ``endpoint`` (of a run already prepared)
    wins over the one the config gives. It resolves ``folder`` once (``resolved_root``: see
    ``prepare_sync``). ``project``: ``folder`` is that project's (spec 31), which the words say."""
    root = _root(config, resolved_root)
    resolved = Path(folder).resolve()
    if resolved.is_relative_to(root):
        relative = resolved.relative_to(root).as_posix()
        relative = "" if relative == "." else relative
        if endpoint is None and config.sync_enabled:
            cluster = config.cluster
            remote_dir = remote_dir_of(resolved, root, config.paths.remote_root)
            endpoint = Endpoint(remote_dir, cluster.host, cluster.user)
    else:
        relative = str(folder)  # prepare_sync refuses it: still say which folder it is
    remote = endpoint.spec() if endpoint is not None else ""
    return SyncScope(relative, remote, config.sync_enabled, direction, project)


def _root(config: AppConfig, resolved_root: Path | None) -> Path:
    return resolved_root if resolved_root is not None else config.paths.local_root.resolve()


def _elide_start(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…" + text[-(limit - 1) :]
