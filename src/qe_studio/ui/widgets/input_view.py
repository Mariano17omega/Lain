"""What the text viewer adds for a QE input (spec 11): write errors, extract strip, comparison.

``InputView`` is one container the ``TextViewer`` embeds, hidden for anything that is not an input.
It holds no parsing: the worker lints the text (``core/qe/input_lint``) and extracts its key
parameters (``core/qe/input_extract``) and hands both to ``bind``; this widget only shows them and
moves the editor's cursor.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.qe.input_extract import Chip
from ...core.qe.input_lint import InputDoc, LintIssue, neighbour_issue
from .code_view import CodeView
from .flow_layout import FlowLayout


def _bar(name: str) -> QWidget:
    bar = QWidget()
    bar.setObjectName(name)
    bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return bar


class InputView(QWidget):
    compare_requested = pyqtSignal()  # "Comparar com…"
    chip_clicked = pyqtSignal(int)  # line of the parameter

    def __init__(self, editor: CodeView, parent: QWidget | None = None):
        super().__init__(parent)
        self.editor = editor
        self.theme = editor.theme
        self.issues: list[LintIssue] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.issues_bar = _bar("viewerIssuesBar")
        row = QHBoxLayout(self.issues_bar)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(6)
        self.issues_label = QLabel()
        self.issues_label.setObjectName("viewerIssues")
        self.first_button = QPushButton("Ir ao primeiro")
        self.first_button.setToolTip("Ir ao primeiro problema (F8: próximo, Shift+F8: anterior)")
        row.addWidget(self.issues_label, 1)
        row.addWidget(self.first_button)
        layout.addWidget(self.issues_bar)

        self.extract_bar = _bar("extractBar")
        column = QVBoxLayout(self.extract_bar)
        column.setContentsMargins(8, 3, 8, 3)
        column.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setProperty("variant", "viewerTool")
        self.toggle.setText("Extrato")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setIconSize(QSize(14, 14))
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolTip("Mostrar ou ocultar o extrato do input")
        self.compare_button = QPushButton("Comparar com…")
        self.compare_button.setToolTip("Comparar este input com outro")
        head.addWidget(self.toggle)
        head.addStretch(1)
        head.addWidget(self.compare_button)
        self.chips_host = QWidget()
        self.chips_layout = FlowLayout(self.chips_host)
        column.addLayout(head)
        column.addWidget(self.chips_host)
        layout.addWidget(self.extract_bar)

        self.first_button.clicked.connect(self.goto_first)
        self.compare_button.clicked.connect(self.compare_requested)
        self.toggle.toggled.connect(self._on_toggled)
        self.theme.theme_changed.connect(self._refresh_icon)
        self._refresh_icon()
        self.bind(None)

    def bind(self, doc: InputDoc | None, chips: Sequence[Chip] = ()) -> None:
        """Show the lint and the extract of an input; ``None`` (not an input, or too big to read)
        hides everything."""
        self.issues = list(doc.issues) if doc is not None else []
        self._set_issues_row()
        self._set_chips(chips)
        self.extract_bar.setVisible(doc is not None)
        self.toggle.setVisible(bool(chips))
        self.setVisible(doc is not None)

    # -- write errors ------------------------------------------------------------------------
    def _set_issues_row(self) -> None:
        count = len(self.issues)
        if not count:
            self.issues_bar.hide()
            return
        level = "error" if any(i.severity == "error" for i in self.issues) else "warning"
        noun = "problema" if count == 1 else "problemas"
        self.issues_label.setText(f"{count} {noun} de escrita no input")
        for widget in (self.issues_bar, self.issues_label):
            widget.setProperty("level", level)
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
        self.issues_bar.show()

    def current_line(self) -> int:
        return self.editor.number_at(self.editor.textCursor().blockNumber()) or 1

    def _go(self, issue: LintIssue | None) -> None:
        if issue is not None:
            self.editor.go_to_line(issue.line)

    def goto_first(self) -> None:
        self._go(self.issues[0] if self.issues else None)

    def goto_next(self) -> None:
        self._go(neighbour_issue(self.issues, self.current_line(), forward=True))

    def goto_previous(self) -> None:
        self._go(neighbour_issue(self.issues, self.current_line(), forward=False))

    # -- extract strip -----------------------------------------------------------------------
    @property
    def chip_buttons(self) -> list[QToolButton]:
        items = (self.chips_layout.itemAt(i) for i in range(self.chips_layout.count()))
        widgets = (item.widget() for item in items if item is not None)
        return [w for w in widgets if isinstance(w, QToolButton)]

    def _set_chips(self, chips: Sequence[Chip]) -> None:
        while (item := self.chips_layout.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for chip in chips:
            button = QToolButton()
            button.setProperty("variant", "chip")
            button.setProperty("dim", chip.is_default)
            button.setProperty("line", chip.line)
            button.setText(chip.text)
            if chip.line is not None:
                button.setToolTip(f"Ir à linha {chip.line}")
            button.setEnabled(chip.line is not None)
            button.clicked.connect(self._on_chip)
            self.chips_layout.addWidget(button)
        self.chips_host.setVisible(bool(chips) and self.toggle.isChecked())

    def _on_chip(self) -> None:
        sender = self.sender()
        line = sender.property("line") if sender is not None else None
        if isinstance(line, int):
            self.editor.go_to_line(line)
            self.chip_clicked.emit(line)

    def _on_toggled(self, expanded: bool) -> None:
        self.chips_host.setVisible(expanded and self.chips_layout.count() > 0)
        self._refresh_icon()

    def _refresh_icon(self, _name: str = "") -> None:
        icon = "expand_more" if self.toggle.isChecked() else "chevron_right"
        self.toggle.setIcon(self.theme.icon(icon, "text_muted", size=14))
