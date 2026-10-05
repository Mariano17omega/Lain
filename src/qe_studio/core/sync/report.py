"""How a pull (PRD §5.5) or a push (spec 27) ended: the status, the one-paragraph message and the
full report that the toast's "Detalhes" shows (spec 17 R3). No Qt: the controller fills it, the UI
shows it."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .rsync import Endpoint

DETAILS_MAX_FILES = 200  # per list: a pull of thousands of files is summed up, not listed


class SyncStatus(StrEnum):
    DONE = "done"
    UP_TO_DATE = "up_to_date"
    LOCAL_NEWER = "local_newer"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SyncReport:
    status: SyncStatus
    local_dir: Path
    remote: Endpoint
    transferred: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    local_newer: list[str] = field(default_factory=list)
    local_newer_folders: list[str] = field(default_factory=list)
    error: str | None = None
    connection_failed: bool = False
    # Edited, created or removed locally between the preview and the transfer: left alone (R3.1).
    changed_locally: tuple[str, ...] = ()

    @property
    def changes_local(self) -> bool:
        """Whether the run may have changed local files (the window refreshes them)."""
        return True

    @property
    def message(self) -> str:
        if self.status is SyncStatus.FAILED:
            return f"Falha na sincronização: {self.error}"
        if self.status is SyncStatus.CANCELLED:
            return "Sincronização cancelada."
        if self.status is SyncStatus.UP_TO_DATE:
            return "Pasta já sincronizada: nada a transferir."
        lines = []
        if self.status is SyncStatus.LOCAL_NEWER:
            lines.append(
                "A cópia local é mais recente que a do cluster: nenhuma transferência realizada."
            )
        else:
            lines.append(f"{len(self.transferred)} arquivo(s) baixado(s).")
        if self.skipped:
            lines.append(f"{len(self.skipped)} conflito(s) mantido(s) na versão local.")
        if self.local_newer and self.status is not SyncStatus.LOCAL_NEWER:
            lines.append(
                f"{len(self.local_newer)} arquivo(s) local(is) mais recente(s) mantido(s)."
            )
        if self.changed_locally:
            lines.append(self.changed_note)
        return "\n".join(lines)

    @property
    def changed_note(self) -> str:
        return (
            f"{len(self.changed_locally)} arquivo(s) mudaram localmente durante a prévia "
            "e não foram baixados."
        )

    @property
    def headline(self) -> str:
        """What the footer and the toast say: the first line, plus the files left alone (they
        show only this; "Detalhes" has the rest)."""
        first = self.message.splitlines()[0]
        return f"{first} {self.changed_note}" if self.changed_locally else first

    @property
    def details(self) -> str:
        """The message, both ends of the pull and every file it touched or left alone."""
        lines = [
            self.message,
            "",
            f"Pasta local: {self.local_dir}",
            f"Cluster: {self.remote.spec()}",
        ]
        for title, paths in (
            ("Baixados", self.transferred),
            ("Mantidos na versão local", self.skipped),
            ("Mais recentes no computador", self.local_newer),
            ("Mudaram localmente (não baixados)", list(self.changed_locally)),
        ):
            if paths:
                lines += ["", f"{title} ({len(paths)}):", *_listed(paths)]
        return "\n".join(lines)


@dataclass
class PushReport(SyncReport):
    """A push: ``transferred`` are the files sent, ``existing`` the ones the cluster already had
    (left as they were). Never LOCAL_NEWER, never skipped conflicts."""

    existing: list[str] = field(default_factory=list)

    @property
    def changes_local(self) -> bool:
        return False

    @property
    def message(self) -> str:
        if self.status is SyncStatus.FAILED:
            return f"Falha no envio: {self.error}"
        if self.status is SyncStatus.CANCELLED:
            return "Envio cancelado."
        if self.status is SyncStatus.UP_TO_DATE:
            lines = ["Nada a enviar."]
        else:
            lines = [f"{len(self.transferred)} arquivo(s) enviado(s)."]
        if self.existing:
            lines.append(f"{len(self.existing)} já existiam no cluster e não foram alterados.")
        return "\n".join(lines)

    @property
    def details(self) -> str:
        lines = [
            self.message,
            "",
            f"Pasta local: {self.local_dir}",
            f"Cluster: {self.remote.spec()}",
        ]
        for title, paths in (
            ("Enviados", self.transferred),
            ("Já existiam no cluster (não alterados)", self.existing),
        ):
            if paths:
                lines += ["", f"{title} ({len(paths)}):", *_listed(paths)]
        return "\n".join(lines)


def _listed(paths: list[str]) -> list[str]:
    shown = [f"  {path}" for path in sorted(paths)[:DETAILS_MAX_FILES]]
    if len(paths) > DETAILS_MAX_FILES:
        shown.append(f"  … e mais {len(paths) - DETAILS_MAX_FILES}")
    return shown
