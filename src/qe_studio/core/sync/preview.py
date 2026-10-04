"""What the plan preview shows before a pull (spec 17 R2.3) or a push (spec 27 R4.3): the summary
line, the warning about large files and the items grouped by action and folder, largest first. The
dialog only lays out ``describe_plan``; what counts as large is ``planner.LARGE_FILE_BYTES``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from ..file_kinds import human_size
from .planner import Action, PlanItem, SyncPlan, total_size
from .push_plan import PushAction, PushItem, PushPlan

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
PUSH_ORDER = (PushAction.NEW, PushAction.EXISTS)
PUSH_TITLES = {
    PushAction.NEW: "Serão enviados",
    PushAction.EXISTS: "Já existem no cluster, não serão alterados",
}
PUSH_NOTES = {PushAction.NEW: "", PushAction.EXISTS: "não será alterado"}
SYNCED_FOLDER = "(pasta sincronizada)"  # label of the items right in the folder being pulled
LARGE_TIP = "Arquivo grande: confira o espaço em disco antes de baixar"
PUSH_LARGE_TIP = "Arquivo grande: confira a cota no cluster antes de enviar"
PULL_DATE = "Data no cluster"
PUSH_DATE = "Data local"

Item = PlanItem | PushItem


@dataclass(frozen=True)
class PlanGroup:
    action: Action | PushAction
    folder: str  # relative to the synced folder, "." for the folder itself
    items: tuple[Item, ...]  # largest first

    @property
    def size(self) -> int:
        return sum(item.size for item in self.items)

    @property
    def has_large(self) -> bool:
        return any(item.is_large for item in self.items)

    @property
    def label(self) -> str:
        return SYNCED_FOLDER if self.folder == "." else f"{self.folder}/"


def _grouped(items: Sequence[Item], order: Iterable[Action | PushAction]) -> list[PlanGroup]:
    groups = []
    for action in order:
        folders: dict[str, list[Item]] = {}
        for item in items:
            if item.action is action:
                folders.setdefault(item.folder, []).append(item)
        for folder in sorted(folders, key=lambda f: (f != ".", f)):
            ordered = sorted(folders[folder], key=lambda item: (-item.size, item.path))
            groups.append(PlanGroup(action, folder, tuple(ordered)))
    return groups


def plan_groups(plan: SyncPlan) -> list[PlanGroup]:
    """Groups by action (new, update, local newer), then folder; items by size, descending."""
    return _grouped(plan.items, ACTION_ORDER)


def push_groups(plan: PushPlan) -> list[PlanGroup]:
    """Groups by action (to send, already on the cluster), then folder; items by size."""
    return _grouped(plan.items, PUSH_ORDER)


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


def push_summary(plan: PushPlan) -> str:
    """ "2 arquivos a enviar (3.1 MB) · 1 já existe no cluster (não será alterado)"."""
    parts = []
    if new := plan.new:
        what = "arquivo a enviar" if len(new) == 1 else "arquivos a enviar"
        parts.append(f"{len(new)} {what} ({human_size(plan.total_bytes)})")
    if exists := plan.exists:
        if len(exists) == 1:
            parts.append("1 já existe no cluster (não será alterado)")
        else:
            parts.append(f"{len(exists)} já existem no cluster (não serão alterados)")
    return " · ".join(parts) or "Nada a enviar."


def large_summary(plan: SyncPlan | PushPlan) -> str | None:
    """ "2 arquivos grandes somam 14.3 GB", or None when no file is large."""
    large = plan.large
    if not large:
        return None
    size = human_size(sum(item.size for item in large))
    if len(large) == 1:
        return f"1 arquivo grande soma {size}"
    return f"{len(large)} arquivos grandes somam {size}"


def format_mtime(epoch: float | None) -> str:
    return datetime.fromtimestamp(epoch).strftime("%d/%m/%Y %H:%M:%S") if epoch else "—"


# -- the tree the preview page lays out --------------------------------------------------------
@dataclass(frozen=True)
class PreviewRow:
    name: str
    path: str
    size: int
    when: str
    note: str
    large: bool


@dataclass(frozen=True)
class PreviewGroup:
    label: str
    size: int
    has_large: bool  # the folder opens by itself
    rows: tuple[PreviewRow, ...]


@dataclass(frozen=True)
class PreviewSection:
    title: str  # "Novos (12)", "Serão enviados (2 · 3.1 MB)"
    size: int
    note: str
    groups: tuple[PreviewGroup, ...]
    expanded: bool = True
    dimmed: bool = False  # informative only: drawn in the metadata color


@dataclass(frozen=True)
class Preview:
    summary: str
    large: str | None
    large_tip: str
    date_header: str
    sections: tuple[PreviewSection, ...]


def describe_plan(plan: SyncPlan | PushPlan) -> Preview:
    """The whole preview of a pull or a push plan."""
    if isinstance(plan, PushPlan):
        return _push_preview(plan)
    groups = plan_groups(plan)
    sections = []
    for action in ACTION_ORDER:
        mine = [group for group in groups if group.action is action]
        if mine:
            note = ACTION_NOTES[action]
            title = f"{ACTION_TITLES[action]} ({sum(len(g.items) for g in mine)})"
            rows = tuple(_group(g, note, _remote_mtime) for g in mine)
            sections.append(PreviewSection(title, sum(g.size for g in mine), note, rows))
    return Preview(plan_summary(plan), large_summary(plan), LARGE_TIP, PULL_DATE, tuple(sections))


def _push_preview(plan: PushPlan) -> Preview:
    groups = push_groups(plan)
    sections = []
    for action in PUSH_ORDER:
        mine = [group for group in groups if group.action is action]
        if not mine:
            continue
        count, size = sum(len(g.items) for g in mine), sum(g.size for g in mine)
        exists = action is PushAction.EXISTS
        title = f"{PUSH_TITLES[action]} ({count})"
        if not exists:
            title = f"{PUSH_TITLES[action]} ({count} · {human_size(size)})"
        note = PUSH_NOTES[action]
        rows = tuple(_group(g, note, _local_mtime) for g in mine)
        sections.append(PreviewSection(title, size, note, rows, not exists, exists))
    return Preview(
        push_summary(plan), large_summary(plan), PUSH_LARGE_TIP, PUSH_DATE, tuple(sections)
    )


def _remote_mtime(item: Item) -> float | None:
    return item.remote_mtime if isinstance(item, PlanItem) else None


def _local_mtime(item: Item) -> float | None:
    return item.mtime if isinstance(item, PushItem) else item.local_mtime


def _group(group: PlanGroup, note: str, when: Callable[[Item], float | None]) -> PreviewGroup:
    rows = tuple(
        PreviewRow(item.name, item.path, item.size, format_mtime(when(item)), note, item.is_large)
        for item in group.items
    )
    return PreviewGroup(group.label, group.size, group.has_large, rows)
