"""What the plan preview shows before a pull (spec 17 R2.3): the summary line, the warning about
large files and the items grouped by action and folder, largest first. The dialog only lays
these out; what counts as large is ``planner.LARGE_FILE_BYTES``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..file_kinds import human_size
from .planner import Action, PlanItem, SyncPlan, total_size

ACTION_ORDER = (Action.NEW, Action.UPDATE, Action.LOCAL_NEWER)
ACTION_TITLES = {
    Action.NEW: "Novos",
    Action.UPDATE: "A atualizar",
    Action.LOCAL_NEWER: "Mais recentes no computador",
}
ACTION_NOTES = {
    Action.NEW: "",
    Action.UPDATE: "pedirá confirmação",
    Action.LOCAL_NEWER: "não será alterado",
}
SYNCED_FOLDER = "(pasta sincronizada)"  # label of the items right in the folder being pulled
LARGE_TIP = "Arquivo grande: confira o espaço em disco antes de baixar"


@dataclass(frozen=True)
class PlanGroup:
    action: Action
    folder: str  # relative to the synced folder, "." for the folder itself
    items: tuple[PlanItem, ...]  # largest first

    @property
    def size(self) -> int:
        return total_size(self.items)

    @property
    def has_large(self) -> bool:
        return any(item.is_large for item in self.items)

    @property
    def label(self) -> str:
        return SYNCED_FOLDER if self.folder == "." else f"{self.folder}/"


def plan_groups(plan: SyncPlan) -> list[PlanGroup]:
    """Groups by action (new, update, local newer), then folder; items by size, descending."""
    groups = []
    for action in ACTION_ORDER:
        folders: dict[str, list[PlanItem]] = {}
        for item in plan.items:
            if item.action is action:
                folders.setdefault(item.folder, []).append(item)
        for folder in sorted(folders, key=lambda f: (f != ".", f)):
            items = sorted(folders[folder], key=lambda item: (-item.size, item.path))
            groups.append(PlanGroup(action, folder, tuple(items)))
    return groups


def plan_summary(plan: SyncPlan) -> str:
    """ "12 arquivos novos (35.2 MB) · 3 a atualizar (1.1 MB) · 2 mais recentes no computador
    (não serão alterados)"; parts without items are left out."""
    parts = []
    if new := plan.new:
        what = "arquivo novo" if len(new) == 1 else "arquivos novos"
        parts.append(f"{len(new)} {what} ({human_size(total_size(new))})")
    if updates := plan.conflicts:
        parts.append(f"{len(updates)} a atualizar ({human_size(total_size(updates))})")
    if newer := plan.local_newer:
        if len(newer) == 1:
            parts.append("1 mais recente no computador (não será alterado)")
        else:
            parts.append(f"{len(newer)} mais recentes no computador (não serão alterados)")
    return " · ".join(parts) or "Nada a transferir."


def large_summary(plan: SyncPlan) -> str | None:
    """ "2 arquivos grandes somam 14.3 GB", or None when no file is large."""
    large = plan.large
    if not large:
        return None
    size = human_size(total_size(large))
    if len(large) == 1:
        return f"1 arquivo grande soma {size}"
    return f"{len(large)} arquivos grandes somam {size}"


def format_mtime(epoch: float | None) -> str:
    return datetime.fromtimestamp(epoch).strftime("%d/%m/%Y %H:%M:%S") if epoch else "—"
