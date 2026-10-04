"""Clickable path of the current folder in the top bar (spec 16 R1).

One button per level, from the project down to the folder, separated by "›". When the row does not
fit, the middle levels next to the project collapse into a "…" button with a menu of them; the
project and the current folder always stay visible.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from ...core.navigation import Segment, breadcrumb_segments, collapse_count
from ..theme.scale import scaled
from .common import set_variant
from .workspace_tabs import add_action

SEPARATOR = "›"
MAX_WIDTH = 560  # the row never takes more than this of the top bar


class Breadcrumb(QWidget):
    folder_requested = pyqtSignal(Path)
    path_copied = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("breadcrumb")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._root: Path | None = None
        self._folder: Path | None = None
        self._segments: list[Segment] = []
        self._buttons: list[QToolButton] = []
        self._separators: list[QLabel] = []
        self._hidden = 0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.more = set_variant(QToolButton(), "crumb")
        self.more.setText("…")
        self.more.setToolTip("Níveis ocultos")
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more.setMenu(QMenu(self.more))
        self.more.hide()
        self._more_separator = self._make_separator()
        self._more_separator.hide()

    # -- content ---------------------------------------------------------------------------------
    @property
    def folder(self) -> Path | None:
        return self._folder

    @property
    def segments(self) -> list[Segment]:
        return list(self._segments)

    def set_root(self, root: Path) -> None:
        self._root = Path(root)

    def set_path(self, folder: Path) -> None:
        """Show ``folder`` (the project root is the first segment)."""
        assert self._root is not None, "set_root first"
        self._folder = Path(folder)
        self.setToolTip(str(folder))
        self._segments = breadcrumb_segments(self._root, self._folder)
        self._rebuild()
        self.updateGeometry()
        # Lay the bar out now: the new path may need more room than the old one had, and
        # collapsing it for one event-loop turn until the resize arrives would flicker.
        parent = self.parentWidget()
        if parent is not None and (parent_layout := parent.layout()) is not None:
            parent_layout.activate()
        self.relayout()

    def hidden_segments(self) -> list[Segment]:
        """The levels now behind the "…" button, root side first."""
        return self._segments[1 : 1 + self._hidden]

    def visible_names(self) -> list[str]:
        return [b.text() for b in self._buttons if not b.isHidden()]

    def _make_separator(self) -> QLabel:
        label = QLabel(SEPARATOR)
        label.setObjectName("crumbSeparator")
        return label

    def _rebuild(self) -> None:
        while (item := self._layout.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None and widget not in (self.more, self._more_separator):
                widget.hide()  # deleteLater waits for the event loop; do not show meanwhile
                widget.deleteLater()
        self._buttons, self._separators = [], []
        last = len(self._segments) - 1
        for position, segment in enumerate(self._segments):
            button = set_variant(QToolButton(), "crumb")
            button.setText(segment.name)
            button.setToolTip(str(segment.path))
            button.setProperty("current", position == last)
            button.clicked.connect(
                lambda _checked=False, p=segment.path: self.folder_requested.emit(p)
            )
            self._buttons.append(button)
            self._layout.addWidget(button)
            if position < last:
                separator = self._make_separator()
                self._separators.append(separator)
                self._layout.addWidget(separator)
            if position == 0 and last > 1:  # "…" goes right after the project's separator
                self._layout.addWidget(self.more)
                self._layout.addWidget(self._more_separator)
        self._layout.addStretch(1)

    # -- layout ----------------------------------------------------------------------------------
    def _widths(self) -> tuple[list[int], int, int]:
        widths = [b.sizeHint().width() for b in self._buttons]
        separator = self._more_separator.sizeHint().width()
        return widths, separator, self.more.sizeHint().width()

    def sizeHint(self) -> QSize:
        widths, separator, _more = self._widths()
        full = sum(widths) + separator * max(len(widths) - 1, 0)
        return QSize(min(full, MAX_WIDTH), scaled(26))

    def minimumSizeHint(self) -> QSize:
        widths, separator, more = self._widths()
        if len(widths) <= 2:
            return QSize(min(sum(widths), 80), scaled(26))
        shown = [widths[0], more, widths[-1]]
        return QSize(min(sum(shown) + separator * 2, 240), scaled(26))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def relayout(self) -> None:
        """Hide as many middle levels as the current width asks for, and fill the "…" menu."""
        if not self._buttons:
            return
        widths, separator, more = self._widths()
        hidden = collapse_count(widths, self.width(), separator, more)
        self._hidden = hidden
        for position, button in enumerate(self._buttons):
            gone = 1 <= position <= hidden
            button.setVisible(not gone)
            if position < len(self._separators):
                self._separators[position].setVisible(not gone)
        self.more.setVisible(hidden > 0)
        self._more_separator.setVisible(hidden > 0)
        menu = self.more.menu()
        assert menu is not None
        menu.clear()
        for segment in self.hidden_segments():
            add_action(menu, segment.name, lambda p=segment.path: self.folder_requested.emit(p))

    # -- right click -----------------------------------------------------------------------------
    def _on_context_menu(self, pos: QPoint) -> None:
        if self._folder is None:
            return
        menu = QMenu(self)
        add_action(menu, "Copiar caminho", self.copy_path)
        menu.exec(self.mapToGlobal(pos))
        menu.deleteLater()

    def copy_path(self) -> None:
        """The absolute path of the current folder on the clipboard."""
        if self._folder is None:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(self._folder))
        self.path_copied.emit(str(self._folder))
