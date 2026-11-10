"""Keyboard shortcuts of the app, searchable (spec 18 R1.1). Not modal: it stays open beside the
window while the user tries the keys."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.search.fuzzy import fold
from ...i18n import _
from ..theme.scale import scaled
from ..widgets.common import hide_vertical_header

HEADERS = (_("Ação"), _("Atalho"), _("Onde"))
ARROWS = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}


def pretty_keys(keys: str) -> str:
    """``Alt+Left`` → ``Alt+←``; text that is not a key sequence ("Botão do meio") is kept."""
    return "+".join(ARROWS.get(part, part) for part in keys.split("+"))


class ShortcutsDialog(QDialog):
    def __init__(self, rows: list[tuple[str, str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.rows = [(action, pretty_keys(keys), where) for action, keys, where in rows]
        self.setWindowTitle(_("Atalhos de teclado"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(scaled(640), scaled(480))
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Buscar ação, atalho ou lugar…"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        hide_vertical_header(self.table)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self._fill)
        self._fill("")
        self.search.setFocus()

    def _fill(self, text: str) -> None:
        needle = fold(text)
        shown = [row for row in self.rows if needle in fold(" ".join(row))]
        self.table.setRowCount(len(shown))
        for r, row in enumerate(shown):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def visible_rows(self) -> list[tuple[str, str, str]]:
        """The rows the table shows now (after the search)."""

        def text(r: int, c: int) -> str:
            item = self.table.item(r, c)
            return item.text() if item else ""

        return [(text(r, 0), text(r, 1), text(r, 2)) for r in range(self.table.rowCount())]
