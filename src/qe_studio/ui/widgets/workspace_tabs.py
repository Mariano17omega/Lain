"""Tab strip of the workspace: close with the middle button, context menu per tab (spec 10 R5)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import QMenu, QTabBar, QTabWidget, QWidget


def add_action(menu: QMenu, text: str, slot: Callable[[], object], enabled: bool = True) -> None:
    action = menu.addAction(text)
    assert action is not None
    action.setEnabled(enabled)
    action.triggered.connect(lambda _checked=False: slot())


class TabBar(QTabBar):
    middle_clicked = pyqtSignal(int)  # tab index
    menu_requested = pyqtSignal(int, QPoint)  # tab index, global position

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0:
                event.accept()
                self.middle_clicked.emit(index)
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        index = self.tabAt(event.pos()) if event is not None else -1
        if event is None or index < 0:
            super().contextMenuEvent(event)
            return
        event.accept()
        self.menu_requested.emit(index, event.globalPos())


class DocumentTabs(QTabWidget):
    """A ``QTabWidget`` with our tab bar (``setTabBar`` is protected: it is set from inside)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.bar = TabBar()
        self.setTabBar(self.bar)
