"""Pure planning of a push (spec 27 R2): rsync's dry run from the local folder to the cluster →
what goes up. Only new files are sent; a file the cluster already has (different or not) is
listed as "exists" and never touched, so there is nothing to resolve (PRD §7 data integrity)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

from .planner import LARGE_FILE_BYTES
from .rsync import DryRunItem


class PushAction(StrEnum):
    NEW = "enviar"
    EXISTS = "já existe"  # on the cluster already: informative, never sent


@dataclass(frozen=True)
class PushItem:
    path: str  # relative to the pushed folder
    action: PushAction
    size: int
    mtime: float  # of the local file

    @property
    def folder(self) -> str:
        return str(PurePosixPath(self.path).parent)

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name

    @property
    def is_large(self) -> bool:
        return self.size > LARGE_FILE_BYTES


@dataclass
class PushPlan:
    items: list[PushItem] = field(default_factory=list)

    def _with(self, action: PushAction) -> list[PushItem]:
        return [item for item in self.items if item.action is action]

    @property
    def new(self) -> list[PushItem]:
        return self._with(PushAction.NEW)

    @property
    def exists(self) -> list[PushItem]:
        return self._with(PushAction.EXISTS)

    @property
    def large(self) -> list[PushItem]:
        """Items above ``LARGE_FILE_BYTES``, whatever their action."""
        return [item for item in self.items if item.is_large]

    @property
    def total_bytes(self) -> int:
        """What the push sends."""
        return sum(item.size for item in self.new)


def is_new(code: str) -> bool:
    """``<f+++++++++``: the cluster has nothing at that path."""
    return len(code) > 2 and set(code[2:]) == {"+"}


def build_push_plan(records: Iterable[DryRunItem], local_dir: Path) -> PushPlan:
    """Sizes and dates come from the local files (one stat each, in a worker); a file gone since
    the dry run is left out."""
    plan = PushPlan()
    for record in records:
        if not record.is_file:
            continue
        try:
            local = (Path(local_dir) / record.path).stat()
        except OSError:
            continue
        action = PushAction.NEW if is_new(record.code) else PushAction.EXISTS
        plan.items.append(PushItem(record.path, action, local.st_size, local.st_mtime))
    return plan
