"""What "Criar cálculo" will write (spec 26 R4.1, R4.6): the text of each file (editable in the
``avancado`` mode only, spec 39 R2) and the "Arquivos" tab with every file of the new folder and the
warnings."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ....core.calc_create.preview import changed_lines, file_rows
from ....core.calc_create.types import PlannedFile
from ....core.qe.input_lexer import LintIssue
from ...theme.manager import ThemeManager
from ...widgets.code_view import CodeView
from ...widgets.common import set_variant
from ...widgets.highlighters import (
    InputHighlighter,
    PlainHighlighter,
    ShellHighlighter,
    ThemedHighlighter,
)
from .labels import message_label, show_message

CHANGED_ROW = "diff_change_bg"  # lines that differ from the SCF: the input diff's color


class FilePreview(CodeView):
    """One file as it will be written, with the lines a derived input changed from the SCF painted.
    Read-only, except in the ``avancado`` mode (``set_editable``, spec 39 R2): what the user types
    comes out as ``edited``, never what ``set_text`` shows."""

    edited = pyqtSignal(str)  # the whole text, after an edit by the user

    def __init__(self, theme: ThemeManager, kind: str, parent: QWidget | None = None):
        super().__init__(theme, parent)
        self.kind = kind
        self.setPlaceholderText("")
        self._setting = False  # inside ``set_text``: not the user's edit
        # The text last shown or typed: a re-highlight (new issues, the theme) ends in an edit block,
        # so ``textChanged`` fires with the text unchanged.
        self._known = ""
        document = self.text_document()
        if kind == "qsub":
            self.highlighter: ThemedHighlighter = ShellHighlighter(document, theme)
        elif kind == "report":  # Markdown, never linted: no colors
            self.highlighter = PlainHighlighter(document, theme)
        else:
            self.highlighter = InputHighlighter(document, theme)
        self.textChanged.connect(self._on_text_changed)

    def set_editable(self, editable: bool) -> None:
        self.set_read_only(not editable)

    def set_text(self, text: str, changed: Sequence[int] = ()) -> None:
        """Show ``text``, keeping the scroll position (it changes on every edit of a field)."""
        if text != self.toPlainText():
            vertical, horizontal = self.verticalScrollBar(), self.horizontalScrollBar()
            position = (
                vertical.value() if vertical is not None else 0,
                horizontal.value() if horizontal is not None else 0,
            )
            self._setting = True
            try:
                self.setPlainText(text)
            finally:
                self._setting = False
            self._known = self.toPlainText()
            if vertical is not None:
                vertical.setValue(position[0])
            if horizontal is not None:
                horizontal.setValue(position[1])
        self.set_row_backgrounds(dict.fromkeys(changed, CHANGED_ROW))

    def show_derived(self, text: str, original: str) -> None:
        """Show ``text``, a generated file: a pw.x input gets the lines that differ from ``original``
        (the SCF) painted."""
        self.set_text(text, self._changes(text, original))

    def paint_changes(self, original: str) -> None:
        """Paint again the lines that differ from ``original``, of the text as it is now (typed)."""
        rows = self._changes(self.toPlainText(), original)
        self.set_row_backgrounds(dict.fromkeys(rows, CHANGED_ROW))

    def _changes(self, text: str, original: str) -> list[int]:
        derived = self.kind == "pw_input" and text != original
        return changed_lines(original, text) if derived else []

    def _on_text_changed(self) -> None:
        if self._setting or self.isReadOnly():
            return
        text = self.toPlainText()
        if text != self._known:
            self._known = text
            self.edited.emit(text)

    def show_issues(self, issues: Sequence[LintIssue]) -> None:
        """The write problems of the text: wavy underline and margin marks, as in the viewer."""
        self.highlighter.set_issues(self.issues_by_block(issues))
        self.set_diagnostics(issues)

    def changed_rows(self) -> list[int]:
        return sorted(self._row_tokens)


class FilesView(QWidget):
    """The "Arquivos" tab: where the folder goes, what it will hold, the warnings and errors."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.target = set_variant(message_label(), "mono")
        self.target.setWordWrap(True)
        self.note = message_label()
        self.tree = QTreeWidget()
        self.tree.setObjectName("calcFiles")
        self.tree.setHeaderLabels(["Arquivo", "Tipo", "Tamanho"])
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.warnings = message_label("warning")
        self.errors = message_label("error")
        layout = QVBoxLayout(self)
        layout.addWidget(self.target)
        layout.addWidget(self.note)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.errors)
        layout.addWidget(self.warnings)

    def show_files(
        self,
        folder: Path,
        asked: str,
        files: Sequence[PlannedFile],
        warnings: Sequence[str],
        errors: Sequence[str],
        edited: Collection[str] = (),
    ) -> None:
        """``folder`` is where it goes now (``preview_name``), ``asked`` the name typed; ``edited``
        the keys of the files edited by hand."""
        show_message(self.target, f"Pasta: {folder}")
        name = folder.name
        if name != asked:
            note = f"Já existe {asked}: a nova pasta será {name}"
        else:
            note = f"Se {name} já existir ao criar, a nova pasta será {name}_1 (nada é sobrescrito)"
        show_message(self.note, note)
        self.tree.clear()
        for row in file_rows(files, edited):
            self.tree.addTopLevelItem(QTreeWidgetItem([row.name, row.kind, row.size]))
        show_message(self.errors, "\n".join(f"• {e}" for e in errors))
        show_message(self.warnings, "\n".join(f"• {w}" for w in warnings))

    def names(self) -> list[str]:
        return [
            item.text(0)
            for index in range(self.tree.topLevelItemCount())
            if (item := self.tree.topLevelItem(index)) is not None
        ]
