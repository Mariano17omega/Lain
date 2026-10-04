"""The sync window (PRD §5.5, spec 17 R2.3) and per-file conflict prompts (PRD §5.4).

One window from the listing to the progress: a ``QStackedWidget`` of the search, preview and
transfer pages (``sync_pages.py``), switched by the controller's signals, so no dialog opens
or closes between the dry run and the preview. A push (spec 27) uses the same window: its title
and the preview's button come from the scope ("Enviando para o cluster", "Enviar").
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.file_kinds import human_size
from ...core.sync._process import RsyncRun
from ...core.sync.planner import Decision, PlanItem, SyncPlan
from ...core.sync.preview import format_mtime
from ...core.sync.push_plan import PushPlan
from ...core.sync.request import SyncScope
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from .sync_pages import PreviewPage, SearchPage, TransferPage

WAITING_DECISION = "Aguardando sua decisão…"


class SyncDialog(QDialog):
    """Locks the window while a pull (or a push) runs. Cancelar (or Esc, or the close button)
    cancels it; on the preview page it declines the plan. The coordinator closes it (``finish``)
    at the end, and connects the pull's conflict prompts to ``await_decision``."""

    def __init__(
        self,
        theme: ThemeManager,
        controller: RsyncRun,
        scope: SyncScope,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("syncDialog")
        self.setWindowTitle(scope.window_title)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(460)
        self.controller = controller
        title = QLabel(scope.title)
        title.setObjectName("syncScope")
        title.setWordWrap(True)
        self.scope_label = title
        paths = set_variant(QLabel(f"Local: {scope.local_text}\nCluster: {scope.remote}"), "mono")
        paths.setWordWrap(True)
        paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.search = SearchPage(theme)
        self.preview = PreviewPage(theme)
        self.transfer = TransferPage()
        self.pages = QStackedWidget()
        for page in (self.search, self.preview, self.transfer):
            self.pages.addWidget(page)
        self.spinner = self.search.spinner
        self.cancel_button = set_variant(QPushButton("Cancelar"), "danger")
        self.cancel_button.setAutoDefault(False)  # Enter never cancels a pull
        self.cancel_button.clicked.connect(self.request_cancel)
        self.download_button = set_variant(QPushButton(scope.confirm_text), "primary")
        self.download_button.clicked.connect(self.download)
        self.download_button.hide()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.download_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(paths)
        layout.addSpacing(8)
        layout.addWidget(self.pages, 1)
        layout.addLayout(buttons)

        controller.stage_changed.connect(self._stage)
        controller.progress_changed.connect(self._progress)
        controller.plan_ready.connect(self.show_plan)
        controller.transfer_started.connect(self._transfer_started)
        self._show_page(self.search)

    # -- pages ------------------------------------------------------------------------------------
    def show_plan(self, plan: SyncPlan | PushPlan) -> None:
        self.preview.set_plan(plan)
        self._show_page(self.preview)
        self.download_button.setDefault(True)
        self.download_button.setFocus()

    def download(self) -> None:
        """ "Baixar" / "Enviar": conflicts, if any, then the transfer, on the transfer page."""
        self.transfer.stage.setText("Preparando transferência…")
        self._show_page(self.transfer)
        self.controller.confirm_plan(True)

    def await_decision(self, _item: PlanItem) -> None:
        """A pull's conflict prompt opens over the window: say so on the transfer page."""
        self._show_page(self.transfer)
        self.transfer.stage.setText(WAITING_DECISION)

    def _transfer_started(self, _files: int) -> None:
        self._show_page(self.transfer)

    def _show_page(self, page: QWidget) -> None:
        """Only the current page counts for the size, and the window only grows: the preview
        makes it bigger, the progress keeps that size."""
        for index in range(self.pages.count()):
            widget = self.pages.widget(index)
            if widget is not None:
                policy = (
                    QSizePolicy.Policy.Preferred if widget is page else QSizePolicy.Policy.Ignored
                )
                widget.setSizePolicy(policy, policy)
        self.pages.setCurrentWidget(page)
        self.download_button.setVisible(page is self.preview)
        if self.isVisible():  # before the first show, show() takes the size hint by itself
            self._grow()

    def _grow(self) -> None:
        """Grow to fit the current page. The height is asked for the real width: the size
        hint of word-wrapped labels guesses a narrow one, which would make it too tall."""
        width = max(self.width(), self.sizeHint().width())
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            height = layout.totalHeightForWidth(width)
        else:
            height = self.sizeHint().height()
        self.resize(width, max(self.height(), height))

    def current_page(self) -> QWidget | None:
        return self.pages.currentWidget()

    # -- controller -------------------------------------------------------------------------------
    def _stage(self, text: str) -> None:
        page = self.pages.currentWidget()
        if page is self.transfer:
            self.transfer.stage.setText(text)
        elif page is self.search:
            self.search.stage.setText(text)

    def _progress(self, percent: int, detail: str) -> None:
        if self.pages.currentWidget() is self.transfer:
            self.transfer.set_progress(percent, detail)
        else:
            self.search.set_progress(percent, detail)

    def request_cancel(self) -> None:
        if self.pages.currentWidget() is self.preview:
            self.download_button.setEnabled(False)
            self.controller.confirm_plan(False)  # ends as CANCELLED, nothing transferred
            return
        self.cancel_button.setEnabled(False)
        self._stage("Cancelando…")
        self.controller.cancel()

    def reject(self) -> None:  # Esc or close: cancel the run, close when rsync has stopped
        if self.controller.running:
            self.request_cancel()
        else:
            super().reject()

    def finish(self) -> None:
        """The run ended (its report was shown when it needs attention): close."""
        self.spinner.stop()
        self.accept()


class ConflictDialog(QDialog):
    """Would overwrite a local file: ask what to do (never blocks the controller)."""

    decided = pyqtSignal(object)  # Decision

    def __init__(self, item: PlanItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Conflito de sincronização")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.item = item
        self._sent = False
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel("O arquivo local seria sobrescrito"), "dialogTitle"))
        layout.addWidget(set_variant(QLabel(item.path), "mono"))
        grid = QGridLayout()
        grid.addWidget(QLabel("Cluster:"), 0, 0)
        cluster = f"{format_mtime(item.remote_mtime)} · {human_size(item.size)}"
        grid.addWidget(QLabel(cluster), 0, 1)
        grid.addWidget(QLabel("Local:"), 1, 0)
        grid.addWidget(QLabel(format_mtime(item.local_mtime)), 1, 1)
        layout.addLayout(grid)
        row = QHBoxLayout()
        for text, decision, variant in (
            ("Cancelar sincronização", Decision.CANCEL, "danger"),
            ("Manter local", Decision.SKIP, None),
            ("Sobrescrever todos nesta pasta", Decision.OVERWRITE_FOLDER, None),
            ("Sobrescrever este", Decision.OVERWRITE, "primary"),
        ):
            button = QPushButton(text)
            if variant:
                set_variant(button, variant)
            button.clicked.connect(lambda _c=False, d=decision: self.decide(d))
            row.addWidget(button)
        layout.addLayout(row)

    def decide(self, decision: Decision) -> None:
        if self._sent:
            return
        self._sent = True
        self.decided.emit(decision)
        self.accept()

    def reject(self) -> None:  # Esc = skip this file (keeps the local copy)
        self.decide(Decision.SKIP)
