"""Search bar of the text viewer (spec 10 R1): field, previous/next, case option, counter."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from .code_view import MAX_MATCHES, CodeView

TYPING_DELAY_MS = 200


class _SearchField(QLineEdit):
    """Enter goes to the next match, Shift+Enter to the previous one, Esc closes the bar."""

    step = pyqtSignal(int)  # +1 / -1
    escaped = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                self.step.emit(-1 if shift else 1)
                return
            if event.key() == Qt.Key.Key_Escape:
                self.escaped.emit()
                return
        super().keyPressEvent(event)


class SearchBar(QWidget):
    closed = pyqtSignal()

    def __init__(self, view: CodeView, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.view = view
        self._capped = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)
        self.field = _SearchField()
        self.field.setPlaceholderText("Buscar no texto")
        self.field.setMinimumWidth(220)
        self.previous = self._button("Anterior", "Anterior (Shift+Enter, Shift+F3)")
        self.next = self._button("Próximo", "Próximo (Enter, F3)")
        self.case = QCheckBox("Diferenciar maiúsculas")
        self.counter = QLabel()
        self.counter.setObjectName("searchCounter")
        self.close_button = self._button("Fechar", "Fechar (Esc)")
        for widget in (self.field, self.previous, self.next, self.case):
            layout.addWidget(widget)
        layout.addWidget(self.counter, 1)
        layout.addWidget(self.close_button)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TYPING_DELAY_MS)
        self._timer.timeout.connect(self.search)
        self.field.textChanged.connect(self._timer.start)
        self.field.step.connect(self.step)
        self.field.escaped.connect(self.dismiss)
        self.case.toggled.connect(self.search)
        self.previous.clicked.connect(self.previous_match)
        self.next.clicked.connect(self.next_match)
        self.close_button.clicked.connect(self.dismiss)
        self.hide()

    @staticmethod
    def _button(text: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setProperty("variant", "viewerTool")
        button.setText(text)
        button.setToolTip(tip)
        return button

    # -- open / close ------------------------------------------------------------------------
    def open(self) -> None:
        """Show the bar with the caret in the field; an old text is searched again."""
        self.show()
        self.field.setFocus()
        self.field.selectAll()
        self.search()

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()
        self.view.clear_search()
        self.view.setFocus()
        self.closed.emit()

    def set_busy(self, busy: bool) -> None:
        """Disabled while the text is loading: there is nothing to search."""
        self.setEnabled(not busy)
        if busy:
            self._timer.stop()
            self.view.clear_search()
            self._update_counter()

    # -- search ------------------------------------------------------------------------------
    def search(self, *_args) -> None:
        self._timer.stop()
        count, self._capped = self.view.set_search(self.field.text(), self.case.isChecked())
        if count:
            self.view.goto_match(self.view.nearest_match())
        self._update_counter()

    def step(self, delta: int) -> None:
        if self._timer.isActive():  # typed, not searched yet: search first
            self.search()
            if delta > 0:
                return  # the first match is already the current one
        if self.view.match_count:
            self.view.goto_match(self.view.current_match + delta)
            self._update_counter()

    def next_match(self) -> None:
        self.step(1)

    def previous_match(self) -> None:
        self.step(-1)

    def refresh(self) -> None:
        """The text changed under an open bar: search it again."""
        if not self.isHidden():
            self.search()

    def _update_counter(self) -> None:
        count = self.view.match_count
        if not self.field.text():
            text = ""
        elif not count:
            text = "Nenhum resultado"
        else:
            total = f"{MAX_MATCHES}+" if self._capped else str(count)
            text = f"{self.view.current_match + 1} de {total}"
        if text and self.view.line_map.truncated:
            text += " (no trecho carregado)"
        self.counter.setText(text)
