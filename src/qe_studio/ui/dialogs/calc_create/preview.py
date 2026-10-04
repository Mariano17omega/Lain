"""What "Criar cálculo" will write (spec 26 R4.1, R4.6): the read-only text of each file and the
"Arquivos" tab with every file of the new folder and the warnings."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ....core.calc_create.preview import file_rows
from ....core.calc_create.types import PlannedFile
from ...theme.manager import ThemeManager
from ...widgets.code_view import CodeView
from ...widgets.common import set_variant
from ...widgets.highlighters import InputHighlighter, ShellHighlighter
from .labels import message_label, show_message

CHANGED_ROW = "diff_change_bg"  # lines that differ from the SCF: the input diff's color


class FilePreview(CodeView):
    """One file as it will be written: never editable (the user fills fields, spec R4.1), with
    the lines a derived input changed from the SCF painted."""

    def __init__(self, theme: ThemeManager, kind: str, parent: QWidget | None = None):
        super().__init__(theme, parent)
        self.setPlaceholderText("")
        document = self.text_document()
        if kind == "qsub":
            self.highlighter: ShellHighlighter | InputHighlighter = ShellHighlighter(
                document, theme
            )
        else:
            self.highlighter = InputHighlighter(document, theme)

    def set_text(self, text: str, changed: Sequence[int] = ()) -> None:
        """Show ``text``, keeping the scroll position (it changes on every edit of a field)."""
        if text != self.toPlainText():
            vertical, horizontal = self.verticalScrollBar(), self.horizontalScrollBar()
            position = (
                vertical.value() if vertical is not None else 0,
                horizontal.value() if horizontal is not None else 0,
            )
            self.setPlainText(text)
            if vertical is not None:
                vertical.setValue(position[0])
            if horizontal is not None:
                horizontal.setValue(position[1])
        self.set_row_backgrounds(dict.fromkeys(changed, CHANGED_ROW))

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
    ) -> None:
        """``folder`` is where it goes now (``preview_name``), ``asked`` the name typed."""
        show_message(self.target, f"Pasta: {folder}")
        name = folder.name
        if name != asked:
            note = f"Já existe {asked}: a nova pasta será {name}"
        else:
            note = f"Se {name} já existir ao criar, a nova pasta será {name}_1 (nada é sobrescrito)"
        show_message(self.note, note)
        self.tree.clear()
        for row in file_rows(files):
            self.tree.addTopLevelItem(QTreeWidgetItem([row.name, row.kind, row.size]))
        show_message(self.errors, "\n".join(f"• {e}" for e in errors))
        show_message(self.warnings, "\n".join(f"• {w}" for w in warnings))

    def names(self) -> list[str]:
        return [
            item.text(0)
            for index in range(self.tree.topLevelItemCount())
            if (item := self.tree.topLevelItem(index)) is not None
        ]
