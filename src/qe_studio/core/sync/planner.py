"""Pure sync planning: rsync dry-run records + local file stats → what to do (PRD §5.2–5.4).

Reading of PRD §5.2 ("cluster newer → download, local newer → no transfer + warning"):
timestamps are compared per file, only for files present on both sides. A directory counts as
"local newer" when it has differing shared files, all newer locally, and nothing new or newer
on the cluster. Files that exist only locally (e.g. figures in ``plots/``) never take part, so
generating plots does not block future pulls.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

from .rsync import DryRunItem

MTIME_TOLERANCE = 2.0  # seconds; FAT/NTFS and rsync --modify-window slack


class Action(StrEnum):
    NEW = "novo"
    UPDATE = "atualizar"  # cluster copy is newer (or differs): overwriting needs confirmation
    LOCAL_NEWER = "local mais recente"


@dataclass(frozen=True)
class PlanItem:
    path: str
    action: Action
    size: int
    remote_mtime: float
    local_mtime: float | None = None

    @property
    def folder(self) -> str:
        return str(PurePosixPath(self.path).parent)


class PlanStatus(StrEnum):
    UP_TO_DATE = "up_to_date"
    LOCAL_NEWER = "local_newer"
    PENDING = "pending"


@dataclass
class SyncPlan:
    items: list[PlanItem] = field(default_factory=list)

    def _with(self, action: Action) -> list[PlanItem]:
        return [item for item in self.items if item.action is action]

    @property
    def new(self) -> list[PlanItem]:
        return self._with(Action.NEW)

    @property
    def conflicts(self) -> list[PlanItem]:
        return self._with(Action.UPDATE)

    @property
    def local_newer(self) -> list[PlanItem]:
        return self._with(Action.LOCAL_NEWER)

    @property
    def local_newer_folders(self) -> list[str]:
        """Folders whose differing files are all newer locally (PRD 'local is newer')."""
        folders: dict[str, set[Action]] = {}
        for item in self.items:
            folders.setdefault(item.folder, set()).add(item.action)
        return sorted(f for f, actions in folders.items() if actions == {Action.LOCAL_NEWER})

    @property
    def status(self) -> PlanStatus:
        if self.new or self.conflicts:
            return PlanStatus.PENDING
        return PlanStatus.LOCAL_NEWER if self.local_newer else PlanStatus.UP_TO_DATE


def build_plan(
    records: Iterable[DryRunItem], local_dir: Path, tolerance: float = MTIME_TOLERANCE
) -> SyncPlan:
    plan = SyncPlan()
    for record in records:
        if not record.is_file:
            continue
        try:
            local = (Path(local_dir) / record.path).stat()
        except FileNotFoundError:
            plan.items.append(PlanItem(record.path, Action.NEW, record.size, record.mtime))
            continue
        except OSError:
            continue
        if local.st_mtime > record.mtime + tolerance:
            action = Action.LOCAL_NEWER
        elif record.mtime > local.st_mtime + tolerance or local.st_size != record.size:
            action = Action.UPDATE
        else:
            continue  # same file within tolerance
        plan.items.append(PlanItem(record.path, action, record.size, record.mtime, local.st_mtime))
    return plan


class Decision(StrEnum):
    OVERWRITE = "overwrite"
    OVERWRITE_FOLDER = "overwrite_folder"
    SKIP = "skip"
    CANCEL = "cancel"


class ConflictResolver:
    """Walks the conflicts one at a time applying the user's decisions (PRD §5.4)."""

    def __init__(self, conflicts: list[PlanItem]):
        self._pending = list(conflicts)
        self._overwrite_folders: set[str] = set()
        self.approved: list[PlanItem] = []
        self.skipped: list[PlanItem] = []
        self.cancelled = False

    def next_conflict(self) -> PlanItem | None:
        """Next conflict needing a decision; auto-approves folders the user chose 'all'."""
        while self._pending and not self.cancelled:
            item = self._pending[0]
            if item.folder in self._overwrite_folders:
                self.approved.append(self._pending.pop(0))
                continue
            return item
        return None

    def resolve(self, decision: Decision) -> None:
        if not self._pending:
            raise RuntimeError("no pending conflict")
        item = self._pending.pop(0)
        if decision is Decision.CANCEL:
            self.cancelled = True
            self._pending.insert(0, item)
        elif decision is Decision.SKIP:
            self.skipped.append(item)
        else:
            if decision is Decision.OVERWRITE_FOLDER:
                self._overwrite_folders.add(item.folder)
            self.approved.append(item)

    @property
    def done(self) -> bool:
        return self.cancelled or self.next_conflict() is None
