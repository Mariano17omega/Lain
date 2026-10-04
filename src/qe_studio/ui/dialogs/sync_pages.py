"""The three pages of the sync window (spec 17 R2.3): listing on the cluster, plan preview and
transfer. They only lay out what ``core/sync`` says; ``SyncDialog`` switches between them."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
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
from ...core.sync.planner import SyncPlan
from ...core.sync.preview import Preview, PreviewRow, PreviewSection, describe_plan
from ...core.sync.push_plan import PushPlan
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from ..widgets.spinner import CircularProgress

COLUMNS = ("Arquivo", "Tamanho", "Data no cluster", "Nota")  # the date's header: the plan's
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

    def set_plan(self, plan: SyncPlan | PushPlan) -> None:
        self.show_preview(describe_plan(plan))

    def show_preview(self, preview: Preview) -> None:
        """Lay out what ``core/sync/preview`` says: sections → folders → files."""
        self.summary.setText(preview.summary)
        self.large.setText(preview.large or "")
        self.large.setVisible(preview.large is not None)
        self.tree.setHeaderLabels([*COLUMNS[:2], preview.date_header, COLUMNS[3]])
        self.tree.clear()
        for section in preview.sections:
            parent = self._section_row(section)
            for group in section.groups:
                row = QTreeWidgetItem(parent, [group.label, human_size(group.size), "", ""])
                row.setTextAlignment(SIZE_COLUMN, RIGHT)
                for item in group.rows:
                    self._file_row(row, item, preview.large_tip)
                row.setExpanded(group.has_large)  # a folder with a large file opens by itself
                self._dim(row, section)
            parent.setExpanded(section.expanded)

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

    def _section_row(self, section: PreviewSection) -> QTreeWidgetItem:
        row = QTreeWidgetItem([section.title, human_size(section.size), "", section.note])
        row.setTextAlignment(SIZE_COLUMN, RIGHT)
        font = row.font(0)
        font.setBold(True)
        row.setFont(0, font)
        self.tree.addTopLevelItem(row)
        self._dim(row, section)
        return row

    def _file_row(self, parent: QTreeWidgetItem, item: PreviewRow, tip: str) -> QTreeWidgetItem:
        row = QTreeWidgetItem(parent, [item.name, human_size(item.size), item.when, item.note])
        row.setTextAlignment(SIZE_COLUMN, RIGHT)
        row.setToolTip(0, item.path)
        if item.large:
            row.setIcon(0, self.theme.icon("warning", "warning", size=14))
            font = row.font(SIZE_COLUMN)
            font.setBold(True)
            row.setFont(SIZE_COLUMN, font)
            row.setToolTip(0, f"{item.path}\n{tip}")
            for column in range(1, len(COLUMNS)):
                row.setToolTip(column, tip)
        return row

    def _dim(self, row: QTreeWidgetItem, section: PreviewSection) -> None:
        """Rows of an informative section (files the push leaves alone) in the metadata color."""
        if not section.dimmed:
            return
        brush = QBrush(self.theme.color("text_meta"))
        for item in (row, *(row.child(i) for i in range(row.childCount()))):
            if item is not None:
                for column in range(len(COLUMNS)):
                    item.setForeground(column, brush)


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
