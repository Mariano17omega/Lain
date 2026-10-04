"""The file grid's list view: extended selection with two additions Qt does not have (spec 16 R5)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QListView, QWidget

from .common import selection_of


class GridView(QListView):
    """``Ctrl``/``Shift`` click, ``Ctrl+A`` and rubber band select several items.

    Qt's Enter key activates only the current item: with several selected, ``enter_many`` is
    emitted instead (the panel knows which of them are files).
    """

    enter_many = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)

    def selected_rows(self) -> list[int]:
        """Rows with a selected item (Ctrl+A also selects the model's hidden columns)."""
        return sorted({index.row() for index in selection_of(self).selectedIndexes()})

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (
            event is not None
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and len(self.selected_rows()) > 1
        ):
            self.enter_many.emit()
            return
        super().keyPressEvent(event)
