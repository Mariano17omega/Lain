"""The three pages of the sync window (spec 17 R2.3): listing on the cluster, plan preview and
transfer. They only lay out what ``core/sync`` says; ``SyncDialog`` switches between them."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.file_kinds import human_size
from ...core.sync.planner import Action, PlanItem, SyncPlan
from ...core.sync.preview import (
    ACTION_NOTES,
    ACTION_TITLES,
    LARGE_TIP,
    PlanGroup,
    format_mtime,
    large_summary,
    plan_groups,
    plan_summary,
)
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from ..widgets.spinner import CircularProgress

COLUMNS = ("Arquivo", "Tamanho", "Data no cluster", "Nota")
SIZE_COLUMN = 1
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _stage_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("syncStage")
    label.setWordWrap(True)
    return label


def _detail_label() -> QLabel:
    label = QLabel("")
    label.setObjectName("syncDetail")
    label.setWordWrap(True)
    return label


class SearchPage(QWidget):
    """Page 0: connecting, listing on the cluster (dry run) and comparing dates."""

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.spinner = CircularProgress(theme)
        self.stage = _stage_label("Preparando…")
        self.detail = _detail_label()
        text = QVBoxLayout()
        text.addWidget(self.stage)
        text.addWidget(self.detail)
        text.addStretch(1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignTop)
        layout.addSpacing(12)
        layout.addLayout(text, 1)

    def set_progress(self, percent: int, detail: str) -> None:
        self.spinner.set_percent(percent)
        self.detail.setText(detail)


class PreviewPage(QWidget):
    """Page 1: what the pull would do, grouped by action and folder, large files first."""

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.summary = set_variant(QLabel(), "dialogText")
        self.summary.setWordWrap(True)
        self.large = set_variant(QLabel(), "dialogWarning")
        self.large.setWordWrap(True)
        self.large.hide()
        self.tree = QTreeWidget()
        self.tree.setObjectName("planTree")
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumSize(600, 260)
        header = self.tree.header()
        assert header is not None
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary)
        layout.addWidget(self.large)
        layout.addWidget(self.tree, 1)

    def set_plan(self, plan: SyncPlan) -> None:
        self.summary.setText(plan_summary(plan))
        warning = large_summary(plan)
        self.large.setText(warning or "")
        self.large.setVisible(warning is not None)
        self.tree.clear()
        groups = plan_groups(plan)
        actions: dict[Action, QTreeWidgetItem] = {}
        for group in groups:
            parent = actions.get(group.action)
            if parent is None:
                parent = actions[group.action] = self._action_row(group.action, groups)
            row = QTreeWidgetItem(parent, [group.label, human_size(group.size), "", ""])
            row.setTextAlignment(SIZE_COLUMN, RIGHT)
            for item in group.items:
                self._file_row(row, item)
            row.setExpanded(group.has_large)  # a folder with a large file opens by itself
        for parent in actions.values():
            parent.setExpanded(True)

    def file_rows(self) -> list[QTreeWidgetItem]:
        """Every file row, in tree order (action → folder → file)."""
        rows = []
        for a in range(self.tree.topLevelItemCount()):
            action = self.tree.topLevelItem(a)
            assert action is not None
            for f in range(action.childCount()):
                folder = action.child(f)
                assert folder is not None
                rows += [folder.child(i) for i in range(folder.childCount())]
        return [row for row in rows if row is not None]

    def _action_row(self, action: Action, groups: list[PlanGroup]) -> QTreeWidgetItem:
        mine = [group for group in groups if group.action is action]
        count = sum(len(group.items) for group in mine)
        size = sum(group.size for group in mine)
        title = f"{ACTION_TITLES[action]} ({count})"
        row = QTreeWidgetItem([title, human_size(size), "", ACTION_NOTES[action]])
        row.setTextAlignment(SIZE_COLUMN, RIGHT)
        font = row.font(0)
        font.setBold(True)
        row.setFont(0, font)
        self.tree.addTopLevelItem(row)
        return row

    def _file_row(self, parent: QTreeWidgetItem, item: PlanItem) -> QTreeWidgetItem:
        when = format_mtime(item.remote_mtime)
        size = human_size(item.size)
        row = QTreeWidgetItem(parent, [item.name, size, when, ACTION_NOTES[item.action]])
        row.setTextAlignment(SIZE_COLUMN, RIGHT)
        row.setToolTip(0, item.path)
        if item.is_large:
            row.setIcon(0, self.theme.icon("warning", "warning", size=14))
            font = row.font(SIZE_COLUMN)
            font.setBold(True)
            row.setFont(SIZE_COLUMN, font)
            row.setToolTip(0, f"{item.path}\n{LARGE_TIP}")
            for column in range(1, len(COLUMNS)):
                row.setToolTip(column, LARGE_TIP)
        return row


class TransferPage(QWidget):
    """Page 2: conflict prompts, then the transfer's progress."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.stage = _stage_label("Preparando transferência…")
        self.bar = QProgressBar()
        self.bar.setObjectName("syncProgress")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.detail = _detail_label()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stage)
        layout.addWidget(self.bar)
        layout.addWidget(self.detail)
        layout.addStretch(1)

    def set_progress(self, percent: int, detail: str) -> None:
        if percent < 0:
            self.bar.setRange(0, 0)  # busy
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(percent)
        self.detail.setText(detail)
