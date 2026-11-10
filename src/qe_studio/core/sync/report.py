"""How a pull (PRD §5.5) or a push (spec 27) ended: the status, the one-paragraph message and the
full report that the toast's "Detalhes" shows (spec 17 R3). No Qt: the controller fills it, the UI
shows it."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ...i18n import _, ngettext
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
    auth_failed: bool = False  # the cluster refused the credentials
    # Edited, created or removed locally between the preview and the transfer: left alone (R3.1).
    changed_locally: tuple[str, ...] = ()
    # What rsync could not read (a folder without permission, a file that vanished): left out.
    not_read: tuple[str, ...] = ()

    @property
    def changes_local(self) -> bool:
        """Whether the run may have changed local files (the window refreshes them)."""
        return True

    @property
    def left_out(self) -> bool:
        """Something the sync covers did not come through: the toast warns."""
        return bool(self.changed_locally or self.not_read)

    @property
    def _arrived_note(self) -> str:
        return ngettext(
            "{count} arquivo baixado antes da falha.",
            "{count} arquivos baixados antes da falha.",
            len(self.transferred),
        ).format(count=len(self.transferred))

    def _failure_lines(self, first: str) -> str:
        return "\n".join([first, *([self._arrived_note] if self.transferred else [])])

    @property
    def not_read_note(self) -> str:
        return ngettext(
            "{count} item não pôde ser lido e ficou de fora.",
            "{count} itens não puderam ser lidos e ficaram de fora.",
            len(self.not_read),
        ).format(count=len(self.not_read))

    @property
    def message(self) -> str:
        if self.status is SyncStatus.FAILED:
            return self._failure_lines(
                _("Falha na sincronização: {error}").format(error=self.error)
            )
        if self.status is SyncStatus.CANCELLED:
            return _("Sincronização cancelada.")
        if self.status is SyncStatus.UP_TO_DATE:
            first = _("Pasta já sincronizada: nada a transferir.")
            return "\n".join([first, *([self.not_read_note] if self.not_read else [])])
        lines = []
        if self.status is SyncStatus.LOCAL_NEWER:
            lines.append(
                _("A cópia local é mais recente que a do cluster: nenhuma transferência realizada.")
            )
        else:
            lines.append(
                ngettext(
                    "{count} arquivo baixado.", "{count} arquivos baixados.", len(self.transferred)
                ).format(count=len(self.transferred))
            )
        if self.skipped:
            lines.append(
                ngettext(
                    "{count} conflito mantido na versão local.",
                    "{count} conflitos mantidos na versão local.",
                    len(self.skipped),
                ).format(count=len(self.skipped))
            )
        if self.local_newer and self.status is not SyncStatus.LOCAL_NEWER:
            lines.append(
                ngettext(
                    "{count} arquivo local mais recente mantido.",
                    "{count} arquivos locais mais recentes mantidos.",
                    len(self.local_newer),
                ).format(count=len(self.local_newer))
            )
        if self.changed_locally:
            lines.append(self.changed_note)
        if self.not_read:
            lines.append(self.not_read_note)
        return "\n".join(lines)

    @property
    def changed_note(self) -> str:
        return ngettext(
            "{count} arquivo mudou localmente durante a prévia e não foi baixado.",
            "{count} arquivos mudaram localmente durante a prévia e não foram baixados.",
            len(self.changed_locally),
        ).format(count=len(self.changed_locally))

    @property
    def headline(self) -> str:
        """What the footer and the toast say: the first line, plus the files left alone (they
        show only this; "Detalhes" has the rest)."""
        notes = [self.message.splitlines()[0]]
        if self.changed_locally:
            notes.append(self.changed_note)
        if self.not_read:
            notes.append(self.not_read_note)
        return " ".join(notes)

    @property
    def details(self) -> str:
        """The message, both ends of the pull and every file it touched or left alone."""
        lines = [
            self.message,
            "",
            _("Pasta local: {local_dir}").format(local_dir=self.local_dir),
            _("Cluster: {remote}").format(remote=self.remote.spec()),
        ]
        for title, paths in (
            (_("Baixados"), self.transferred),
            (_("Mantidos na versão local"), self.skipped),
            (_("Mais recentes no computador"), self.local_newer),
            (_("Mudaram localmente (não baixados)"), list(self.changed_locally)),
            (_("Não lidos (ficaram de fora)"), list(self.not_read)),
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
    def _arrived_note(self) -> str:
        return ngettext(
            "{count} arquivo enviado antes da falha.",
            "{count} arquivos enviados antes da falha.",
            len(self.transferred),
        ).format(count=len(self.transferred))

    @property
    def message(self) -> str:
        if self.status is SyncStatus.FAILED:
            return self._failure_lines(_("Falha no envio: {error}").format(error=self.error))
        if self.status is SyncStatus.CANCELLED:
            return _("Envio cancelado.")
        if self.status is SyncStatus.UP_TO_DATE:
            lines = [_("Nada a enviar.")]
        else:
            lines = [
                ngettext(
                    "{count} arquivo enviado.", "{count} arquivos enviados.", len(self.transferred)
                ).format(count=len(self.transferred))
            ]
        if self.existing:
            lines.append(
                ngettext(
                    "{count} já existia no cluster e não foi alterado.",
                    "{count} já existiam no cluster e não foram alterados.",
                    len(self.existing),
                ).format(count=len(self.existing))
            )
        if self.not_read:
            lines.append(self.not_read_note)
        return "\n".join(lines)

    @property
    def details(self) -> str:
        lines = [
            self.message,
            "",
            _("Pasta local: {local_dir}").format(local_dir=self.local_dir),
            _("Cluster: {remote}").format(remote=self.remote.spec()),
        ]
        for title, paths in (
            (_("Enviados"), self.transferred),
            (_("Já existiam no cluster (não alterados)"), self.existing),
            (_("Não lidos (ficaram de fora)"), list(self.not_read)),
        ):
            if paths:
                lines += ["", f"{title} ({len(paths)}):", *_listed(paths)]
        return "\n".join(lines)


def _listed(paths: list[str]) -> list[str]:
    shown = [f"  {path}" for path in sorted(paths)[:DETAILS_MAX_FILES]]
    if len(paths) > DETAILS_MAX_FILES:
        shown.append(_("  … e mais {value}").format(value=len(paths) - DETAILS_MAX_FILES))
    return shown
