"""Quick filter row of the explorer and the file grid (spec 16 R3): a name field, a "Filtrar ▾"
menu of categories and the ticked ones as removable chips.

Hidden until Ctrl+F. Esc clears everything and hides it again. The bar only reports what is
asked for (``name_text``, ``category_filter``); the panels hand it to their proxy model.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeyEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.filtering import CategoryFilter
from .common import set_variant
from .flow_layout import FlowLayout

TYPING_DELAY_MS = 150
# (group key of ``CategoryFilter``, menu title, values): what the menu offers.
Group = tuple[str, str, Sequence[str]]


class _FilterField(QLineEdit):
    escaped = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None and event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)


class FilterBar(QWidget):
    changed = pyqtSignal()  # name or categories changed (typing is debounced)
    closed = pyqtSignal()  # Esc: everything cleared, the bar hidden; focus goes back to the list
    accepted = pyqtSignal()  # Enter in the field: the caller moves the focus to its list

    def __init__(self, placeholder: str, groups: Sequence[Group], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("filterBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._actions: dict[tuple[str, str], QAction] = {}  # (group, value) → checkable action
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 4, 8, 4)
        column.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.field = _FilterField()
        self.field.setPlaceholderText(placeholder)
        self.field.setClearButtonEnabled(True)
        self.menu_button = set_variant(QToolButton(), "filterTool")
        self.menu_button.setText("Filtrar ▾")
        self.menu_button.setToolTip("Filtrar por tipo ou estado")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setMenu(self._build_menu(groups))
        row.addWidget(self.field, 1)
        row.addWidget(self.menu_button)
        column.addLayout(row)
        self.chips_host = QWidget()
        self.chips_layout = FlowLayout(self.chips_host)
        self.chips_host.hide()
        column.addWidget(self.chips_host)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TYPING_DELAY_MS)
        self._timer.timeout.connect(self.changed)
        self.field.textChanged.connect(self._timer.start)
        self.field.escaped.connect(self._on_escape)
        self.field.returnPressed.connect(self.accepted)
        self.hide()

    def _build_menu(self, groups: Sequence[Group]) -> QMenu:
        menu = QMenu(self)
        for position, (key, title, values) in enumerate(groups):
            if position:
                menu.addSeparator()
            header = menu.addAction(title)
            assert header is not None
            header.setEnabled(False)
            for value in values:
                action = menu.addAction(value)
                assert action is not None
                action.setCheckable(True)
                action.toggled.connect(self._on_category_toggled)
                self._actions[(key, value)] = action
        return menu

    # -- what is asked for -------------------------------------------------------------------------
    def name_text(self) -> str:
        return self.field.text()

    def checked(self, group: str) -> frozenset[str]:
        return frozenset(
            v for (g, v), action in self._actions.items() if g == group and action.isChecked()
        )

    def category_filter(self) -> CategoryFilter:
        return CategoryFilter(
            badges=self.checked("badges"),
            states=self.checked("states"),
            visuals=self.checked("visuals"),
        )

    @property
    def is_active(self) -> bool:
        return bool(self.field.text()) or self.category_filter().active

    def flush(self) -> None:
        """Apply the typing the debounce is still holding back."""
        if self._timer.isActive():
            self._timer.stop()
            self.changed.emit()

    # -- open / close ------------------------------------------------------------------------------
    def open(self) -> None:
        self.show()
        self.field.setFocus()
        self.field.selectAll()

    def _on_escape(self) -> None:
        self.dismiss()
        self.closed.emit()

    def dismiss(self) -> None:
        """Clear the name and the categories and hide the bar; ``closed`` is for Esc only."""
        was_active = self.is_active
        self._timer.stop()
        self.field.clear()
        self._timer.stop()  # clearing started it
        for action in self._actions.values():
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        self._refresh_chips()
        self.hide()
        if was_active:
            self.changed.emit()

    # -- categories --------------------------------------------------------------------------------
    def _on_category_toggled(self, _checked: bool) -> None:
        self._refresh_chips()
        self.changed.emit()

    def _refresh_chips(self) -> None:
        while (item := self.chips_layout.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for (_group, value), action in self._actions.items():
            if not action.isChecked():
                continue
            chip = set_variant(QToolButton(), "chip")
            chip.setText(f"{value} ×")
            chip.setToolTip("Remover filtro")
            chip.clicked.connect(lambda _checked=False, a=action: a.setChecked(False))
            self.chips_layout.addWidget(chip)
        self.chips_host.setVisible(self.chips_layout.count() > 0)
