"""Tab "Resumo · <arquivo>": the facts of a QE output, extracted when the tab opens (spec 12 R3).

``core/qe/summary`` does the extraction in a worker; this widget lays the result out. Nothing is
saved: closing the tab drops the summary, "Atualizar" reads the file again.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.qe.summary import OutputSummary, summarize, to_text
from ...core.tasks import TaskHandle, run_task
from ..theme.manager import ThemeManager
from .summary_widgets import SummarySectionWidget

log = logging.getLogger(__name__)

MESSAGE, CONTENT = 0, 1  # pages of the stack


def summary_key(path: Path) -> str:
    """Key of the workspace tab that summarizes ``path``."""
    return f"summary:{path}"


def _tool(text: str, tip: str) -> QToolButton:
    button = QToolButton()
    button.setProperty("variant", "viewerTool")
    button.setText(text)
    button.setToolTip(tip)
    return button


class SummaryView(QWidget):
    """Sections of label/value rows. A double click on a row with a line opens the output there."""

    loaded = pyqtSignal()  # the read finished (or failed)
    open_output_requested = pyqtSignal(Path, int)  # file, line (0: just open it)

    def __init__(self, path: Path, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.theme = theme
        self.summary: OutputSummary | None = None
        self._task: TaskHandle | None = None  # the read in progress (cancelled when we die)
        self.setObjectName("summaryView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.bar = QWidget()
        self.bar.setObjectName("summaryBar")
        self.bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self.bar)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(4)
        self.copy_button = _tool("Copiar", "Copiar o resumo como texto")
        self.open_button = _tool("Abrir saída", "Abrir o arquivo no visualizador de texto")
        self.refresh_button = _tool("Atualizar", "Ler o arquivo de novo (o job pode estar rodando)")
        for button in (self.copy_button, self.open_button, self.refresh_button):
            row.addWidget(button)
        row.addStretch(1)
        layout.addWidget(self.bar)

        self.message = QLabel()
        self.message.setObjectName("summaryMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.area = QScrollArea()
        self.area.setObjectName("summaryScroll")
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.message)
        self.stack.addWidget(self.area)
        layout.addWidget(self.stack, 1)

        self.copy_button.clicked.connect(self.copy_summary)
        self.open_button.clicked.connect(self._open_output)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    @property
    def sections(self) -> list[SummarySectionWidget]:
        body = self.area.widget()
        return body.findChildren(SummarySectionWidget) if body is not None else []

    # -- loading -----------------------------------------------------------------------------
    def refresh(self) -> None:
        """Read the file again; the result of an earlier, slower read is dropped."""
        self.copy_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self._show_message(f"Lendo {self.path.name}…")
        if self._task is not None:
            self._task.cancel()
        self._task = run_task(summarize, self.path, on_done=self._on_done, on_error=self._on_failed)

    def _on_done(self, summary: OutputSummary) -> None:
        self.summary = summary
        body = QWidget()
        body.setObjectName("summaryBody")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for section in summary.sections:
            widget = SummarySectionWidget(section, self.theme)
            widget.activated.connect(self._open_line)
            column.addWidget(widget)
        column.addStretch(1)
        self.area.setWidget(body)
        self.stack.setCurrentIndex(CONTENT)
        self.copy_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.loaded.emit()

    def _on_failed(self, error: Exception) -> None:
        if not isinstance(error, OSError):  # a parser bug must not leave the tab on "Lendo…"
            log.error("summary of %s failed", self.path, exc_info=error)
        self.summary = None
        self._show_message(f"Não foi possível ler o arquivo: {error}")
        self.refresh_button.setEnabled(True)
        self.loaded.emit()

    def _show_message(self, text: str) -> None:
        self.message.setText(text)
        self.stack.setCurrentIndex(MESSAGE)

    # -- actions -----------------------------------------------------------------------------
    def copy_summary(self) -> None:
        if self.summary is None:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(to_text(self.summary))

    def _open_output(self) -> None:
        self.open_output_requested.emit(self.path, 0)

    def _open_line(self, line: int) -> None:
        self.open_output_requested.emit(self.path, line)
