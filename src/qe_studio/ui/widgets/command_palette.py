"""The command palette window (spec 18 R2): a search field above a list of rows.

It only shows rows and reports which one was chosen (``activated(key)``); the controller decides
what the rows are and what choosing one does. Keys: ↑/↓ move, Enter chooses, Esc closes.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QModelIndex, QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPainter, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..painting import mono_font, ui_font
from ..theme.manager import ThemeManager

MAX_ROWS = 50
VISIBLE_ROWS = 10
ROW_HEIGHT = 28
WIDTH = 640
ROW_ROLE = Qt.ItemDataRole.UserRole


@dataclass(frozen=True)
class PaletteRow:
    """One line: ``section`` is the category shown before the label ("Ação", "Pasta"…)."""

    key: str
    section: str
    label: str
    icon: str = "bolt"
    shortcut: str = ""
    selectable: bool = True

    @property
    def display(self) -> str:
        return f"{self.label} ({self.shortcut})" if self.shortcut else self.label


class RowDelegate(QStyledItemDelegate):
    def __init__(self, theme: ThemeManager, parent: QObject | None = None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        row: PaletteRow = index.data(ROW_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect
        painter.save()
        if selected:
            painter.fillRect(rect, self.theme.color("accent_soft"))
        dim = not row.selectable
        painter.drawPixmap(
            rect.left() + 10,
            rect.top() + (rect.height() - 16) // 2,
            self.theme.pixmap(row.icon, "text_dim" if dim else "text_muted", 16),
        )
        painter.setFont(mono_font(10))
        painter.setPen(self.theme.color("text_dim"))
        section_width = painter.fontMetrics().horizontalAdvance(row.section) + 12
        painter.drawText(
            QRect(rect.left() + 34, rect.top(), section_width, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            row.section,
        )
        right = rect.right() - 10
        if row.shortcut:
            width = painter.fontMetrics().horizontalAdvance(row.shortcut)
            painter.drawText(
                QRect(right - width, rect.top(), width + 1, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                row.shortcut,
            )
            right -= width + 12
        painter.setFont(ui_font(12))
        painter.setPen(
            self.theme.color("text_dim" if dim else "accent_text" if selected else "text")
        )
        left = rect.left() + 34 + section_width
        text_rect = QRect(left, rect.top(), max(0, right - left), rect.height())
        text = painter.fontMetrics().elidedText(
            row.label, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text
        )
        painter.restore()


class CommandPalette(QFrame):
    activated = pyqtSignal(str)  # the chosen row's key
    query_changed = pyqtSignal(str)

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("commandPalette")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Digite um comando…   > ações   / pastas   @ abas")
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit)
        self.model = QStandardItemModel(self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(RowDelegate(theme, self.view))
        self.view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setFixedHeight(VISIBLE_ROWS * ROW_HEIGHT)
        layout.addWidget(self.view)
        self.setFixedWidth(WIDTH)
        self.edit.textChanged.connect(self.query_changed)
        self.view.clicked.connect(self._on_clicked)

    # -- content ---------------------------------------------------------------------------
    def set_rows(self, rows: list[PaletteRow]) -> None:
        """Replace the list (at most ``MAX_ROWS``); the first selectable row becomes current."""
        self.model.clear()
        for row in rows[:MAX_ROWS]:
            item = QStandardItem(row.display)
            item.setData(row, ROW_ROLE)
            if not row.selectable:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.model.appendRow(item)
        self._select(0, 1)

    def rows(self) -> list[PaletteRow]:
        return [self.model.index(i, 0).data(ROW_ROLE) for i in range(self.model.rowCount())]

    def labels(self) -> list[str]:
        """What each row reads, e.g. ``"Gerar gráfico (Ctrl+G)"``."""
        return [row.display for row in self.rows()]

    def query(self) -> str:
        return self.edit.text()

    def set_query(self, text: str) -> None:
        self.edit.setText(text)

    def current_key(self) -> str | None:
        index = self.view.currentIndex()
        row = index.data(ROW_ROLE) if index.isValid() else None
        return row.key if row is not None and row.selectable else None

    # -- showing ---------------------------------------------------------------------------
    def popup(self, anchor: QWidget) -> None:
        """Show it centred near the top of ``anchor``'s window."""
        window = anchor.window() or anchor
        self.adjustSize()
        top_left = window.mapToGlobal(window.rect().topLeft())
        x = top_left.x() + (window.width() - self.width()) // 2
        y = top_left.y() + max(40, window.height() // 8)
        self.move(x, y)
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    # -- keys ------------------------------------------------------------------------------
    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            obj is self.edit
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
        ):
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._move(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose()
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def choose(self) -> None:
        key = self.current_key()
        if key is not None:
            self.hide()
            self.activated.emit(key)

    def _on_clicked(self, index: QModelIndex) -> None:
        self.view.setCurrentIndex(index)
        self.choose()

    def _move(self, step: int) -> None:
        index = self.view.currentIndex()
        self._select((index.row() if index.isValid() else -1) + step, step)

    def _select(self, start: int, step: int) -> None:
        """Make current the first selectable row from ``start`` going by ``step`` (no wrap)."""
        count = self.model.rowCount()
        row = start
        while 0 <= row < count:
            index = self.model.index(row, 0)
            if self.model.flags(index) & Qt.ItemFlag.ItemIsEnabled:
                self.view.setCurrentIndex(index)
                return
            row += step
