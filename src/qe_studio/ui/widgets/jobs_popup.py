"""The cluster's queue under the jobs indicator (spec 64 R5): a popup, not a ``QMenu``.

It shows what ``ui/jobs_controller.py`` gives it, one of four pages: querying (before the first
answer), the failure and "Tentar de novo", an empty queue, or the jobs in two sections, "Em execução"
and "Na fila", each under a coloured bar, with the user's own jobs in bold and the accent colour.
A click outside or Esc closes it.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.cluster_jobs import Job, JobsSnapshot
from ...i18n import _
from ..theme.manager import ThemeManager
from ..theme.scale import scaled
from .spinner import CircularProgress

WIDTH = 600  # px at scale 1
INDENT = 14  # px at scale 1: the jobs sit inside their bar
MAX_ROWS = 14  # rows shown before the table scrolls
CORES = 3  # the column of the "#" of the qstatus listing
LOADING, FAILURE, EMPTY, TABLE = range(4)
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def clock(epoch: float) -> str:
    """``14:05``: when a listing was fetched, in local time."""
    return time.strftime("%H:%M", time.localtime(epoch))


class JobsPopup(QFrame):
    refresh_requested = pyqtSignal()  # "Atualizar" or "Tentar de novo"

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("jobsPopup")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # A click on the indicator while open only closes it (no replayed click to reopen it).
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        self._shown: tuple[JobsSnapshot, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title = QLabel(_("Fila do cluster"))
        self.title.setObjectName("jobsTitle")
        self.updated = QLabel()
        self.updated.setObjectName("jobsNote")
        self.refresh_button = QPushButton(_("Atualizar"))
        self.refresh_button.clicked.connect(self.refresh_requested)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.updated)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        # One page shown at a time; a hidden one takes no room, so the popup is as tall as it.
        self.empty = QLabel(_("Nenhum job no cluster."))
        self.empty.setObjectName("jobsNote")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tree = self._table()
        self._pages = [self._loading_page(), self._failure_page(), self.empty, self.tree]
        for page in self._pages:
            layout.addWidget(page)
        self._page = LOADING
        self._set_page(LOADING)
        self.setFixedWidth(scaled(WIDTH))
        theme.theme_changed.connect(self._on_theme_changed)
        theme.scale_changed.connect(self._on_scale_changed)

    def _loading_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.addStretch(1)
        self.spinner = CircularProgress(self.theme, 16)
        row.addWidget(self.spinner)
        loading = QLabel(_("Consultando o cluster…"))
        loading.setObjectName("jobsNote")
        row.addWidget(loading)
        row.addStretch(1)
        return page

    def _failure_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        self.failure = QLabel()
        self.failure.setObjectName("jobsFailure")
        self.failure.setWordWrap(True)
        self.failure.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.retry_button = QPushButton(_("Tentar de novo"))
        self.retry_button.clicked.connect(self.refresh_requested)
        column.addWidget(self.failure)
        column.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignLeft)
        return page

    def _table(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("jobsTable")
        tree.setColumnCount(4)
        tree.setHeaderLabels([_("Nome"), _("Dono"), _("Envio / início"), _("Núcleos")])
        header_item = tree.headerItem()
        assert header_item is not None
        header_item.setTextAlignment(CORES, RIGHT)
        tree.setRootIsDecorated(False)
        tree.setIndentation(scaled(INDENT))
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        header = tree.header()
        assert header is not None
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    # -- content -----------------------------------------------------------------------------
    def page(self) -> int:
        """``LOADING``, ``FAILURE``, ``EMPTY`` or ``TABLE``."""
        return self._page

    def show_loading(self) -> None:
        self._shown = None
        self.updated.setText("")
        self._set_page(LOADING)

    def show_failure(self, message: str) -> None:
        self._shown = None
        self.updated.setText("")
        self.failure.setText(message)
        self._set_page(FAILURE)

    def show_snapshot(self, snapshot: JobsSnapshot, user: str) -> None:
        """The jobs of ``snapshot``; those of ``user`` stand out."""
        self._shown = (snapshot, user)
        self.updated.setText(_("Atualizado às {time}").format(time=clock(snapshot.fetched_at)))
        self.tree.clear()
        if not snapshot.running and not snapshot.waiting:
            self._set_page(EMPTY)
            return
        for title, jobs, bar in (
            (_("Em execução ({n})"), snapshot.running, "job_running"),
            (_("Na fila ({n})"), snapshot.waiting, "job_queued"),
        ):
            self._section(title.format(n=len(jobs)), jobs, user, bar)
        self.tree.expandAll()
        self._set_page(TABLE)

    def set_busy(self, busy: bool) -> None:
        """A query is running: "Atualizar" waits for it (the listing shown stays)."""
        self.refresh_button.setEnabled(not busy)
        self.retry_button.setEnabled(not busy)
        if busy and self._shown is not None:
            self.updated.setText(_("Atualizando…"))
        elif self._shown is not None:
            self.updated.setText(
                _("Atualizado às {time}").format(time=clock(self._shown[0].fetched_at))
            )

    def _section(self, title: str, jobs: tuple[Job, ...], user: str, bar: str) -> None:
        """A bar painted with the ``<bar>_bg`` and ``<bar>_fg`` tokens, and its jobs under it."""
        section = QTreeWidgetItem([title])
        section.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = section.font(0)
        font.setBold(True)
        section.setFont(0, font)
        section.setBackground(0, self.theme.color(f"{bar}_bg"))
        section.setForeground(0, self.theme.color(f"{bar}_fg"))
        self.tree.addTopLevelItem(section)
        section.setFirstColumnSpanned(True)
        accent = self.theme.color("accent_text")
        for job in jobs:
            row = QTreeWidgetItem([job.name, job.owner or "", job.short_date, str(job.slots)])
            row.setFlags(Qt.ItemFlag.ItemIsEnabled)
            row.setTextAlignment(CORES, RIGHT)
            # What the columns leave out: the queue ("running in") and the date as written.
            parts = [_("job-ID {job_id}").format(job_id=job.job_id), job.queue, job.date]
            tip = " · ".join(part for part in parts if part)
            for column in range(4):
                row.setToolTip(column, tip)
                if job.owner == user:
                    bold = row.font(column)
                    bold.setBold(True)
                    row.setFont(column, bold)
                    row.setForeground(column, accent)
            section.addChild(row)

    def _set_page(self, page: int) -> None:
        self._page = page
        for index, widget in enumerate(self._pages):
            widget.setVisible(index == page)
        self._fit()

    def _fit(self) -> None:
        """The table as tall as its rows, up to ``MAX_ROWS``; the popup follows."""
        if self._page == TABLE:
            sections = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
            rows = sum(1 + item.childCount() for item in sections if item is not None)
            height = max(self.tree.sizeHintForRow(0), scaled(20))
            header = self.tree.header()
            top = header.sizeHint().height() if header is not None else 0
            self.tree.setFixedHeight(top + min(rows, MAX_ROWS) * height + 4)
        self.adjustSize()

    def _on_theme_changed(self, _name: str) -> None:
        if self._shown is not None:
            self.show_snapshot(*self._shown)

    def _on_scale_changed(self, _scale: float) -> None:
        self.setFixedWidth(scaled(WIDTH))
        self.tree.setIndentation(scaled(INDENT))
        self._fit()

    # -- showing -----------------------------------------------------------------------------
    def popup_below(self, anchor: QWidget) -> None:
        """Open under ``anchor``, its right edge on the anchor's, inside the screen."""
        self._fit()
        corner = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height() + 4))
        x, y = corner.x() - self.width(), corner.y()
        screen = anchor.screen()
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left(), min(x, area.right() - self.width()))
            y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.setFocus()
