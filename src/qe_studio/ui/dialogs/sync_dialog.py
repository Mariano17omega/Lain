"""Modal progress while syncing (PRD §5.5) and per-file conflict prompts (PRD §5.4)."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.file_kinds import human_size
from ...core.sync.controller import SyncController
from ...core.sync.planner import Decision, PlanItem
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from ..widgets.spinner import CircularProgress


def _when(epoch: float | None) -> str:
    return datetime.fromtimestamp(epoch).strftime("%d/%m/%Y %H:%M:%S") if epoch else "—"


class SyncDialog(QDialog):
    """Locks the window while rsync runs; the only way out is Cancelar (or completion)."""

    def __init__(
        self,
        theme: ThemeManager,
        controller: SyncController,
        source: str,
        target: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("syncDialog")
        self.setWindowTitle("Sincronizando com o cluster")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(460)
        self.controller = controller
        self.spinner = CircularProgress(theme)
        self.stage = QLabel("Preparando…")
        self.stage.setObjectName("syncStage")
        self.detail = QLabel("")
        self.detail.setObjectName("syncDetail")
        self.detail.setWordWrap(True)
        paths = set_variant(QLabel(f"{source}\n→ {target}"), "mono")
        paths.setWordWrap(True)
        self.cancel_button = set_variant(QPushButton("Cancelar"), "danger")
        self.cancel_button.clicked.connect(self.request_cancel)

        text = QVBoxLayout()
        text.addWidget(self.stage)
        text.addWidget(self.detail)
        text.addWidget(paths)
        top = QHBoxLayout()
        top.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignTop)
        top.addSpacing(12)
        top.addLayout(text, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(buttons)

        controller.stage_changed.connect(self.stage.setText)
        controller.progress_changed.connect(self._progress)
        controller.finished.connect(self._finished)

    def _progress(self, percent: int, detail: str) -> None:
        self.spinner.set_percent(percent)
        self.detail.setText(detail)

    def request_cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.stage.setText("Cancelando…")
        self.controller.cancel()

    def reject(self) -> None:  # Esc: cancel the transfer, close when rsync has stopped
        if self.controller.running:
            self.request_cancel()
        else:
            super().reject()

    def _finished(self, _report) -> None:
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
        grid.addWidget(QLabel(f"{_when(item.remote_mtime)} · {human_size(item.size)}"), 0, 1)
        grid.addWidget(QLabel("Local:"), 1, 0)
        grid.addWidget(QLabel(_when(item.local_mtime)), 1, 1)
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
