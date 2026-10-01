"""Read-only text view with a line number margin, search highlights and diagnostics (specs 10, 11).

The margin follows the Qt "Code Editor" example. Numbers come from a ``LineMap`` so a truncated
file keeps its real line numbers after the omitted stretch. Diagnostics (the write errors of an
input) get a colored circle in the margin and a tooltip over the circle or the marked text; the
wavy underline itself is the syntax highlighter's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import (
    QHelpEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

from ...core.qe.input_lexer import LintIssue
from ...core.textfile import LineMap
from ..theme.manager import ThemeManager

MAX_MATCHES = 5000  # a search past this stops: the counter shows "5000+"
GUTTER_PADDING = 8
MIN_DIGITS = 3
MARKER_WIDTH = 16  # extra margin column, only while there are diagnostics
MARKER_RADIUS = 4


class LineNumberArea(QWidget):
    def __init__(self, view: CodeView):
        super().__init__(view)
        self.view = view

    def sizeHint(self) -> QSize:
        return QSize(self.view.gutter_width(), 0)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if event is not None:
            self.view.paint_gutter(event)

    def event(self, event: QEvent | None) -> bool:
        if isinstance(event, QHelpEvent) and event.type() == QEvent.Type.ToolTip:
            self.view.show_marker_tip(event)
            return True
        return super().event(event)


class CodeView(QPlainTextEdit):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("textViewer")
        self.setReadOnly(True)
        # Read-only keeps the mouse selection only: the keyboard (caret, Ctrl+Home/End) is wanted too.
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText("Carregando…")
        self.text_document().setDocumentMargin(8)
        self._line_map = LineMap()
        self._numbers: Sequence[int | None] | None = None
        self._diagnostics: dict[int, list[LintIssue]] = {}
        self._row_tokens: dict[int, str] = {}
        self._matches: list[tuple[int, int]] = []
        self._current = -1
        self.gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._scroll_gutter)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        theme.theme_changed.connect(self._on_theme)
        self._update_margin()

    def text_document(self) -> QTextDocument:
        """``document()`` without the ``None`` its stub allows: a view always has one."""
        document = self.document()
        assert document is not None
        return document

    # -- line numbers ------------------------------------------------------------------------
    @property
    def line_map(self) -> LineMap:
        return self._line_map

    def set_line_map(self, line_map: LineMap) -> None:
        self._line_map = line_map
        self._update_margin()
        self.gutter.update()

    def set_numbers(self, numbers: Sequence[int | None] | None) -> None:
        """Number each block as given (None: no number), for views whose blocks are not the lines of
        one file: padded side-by-side diffs. ``None`` goes back to the ``LineMap``."""
        self._numbers = numbers
        self._update_margin()
        self.gutter.update()

    def number_at(self, block: int) -> int | None:
        """Real line number the margin shows for ``block`` (None: no number)."""
        if self._numbers is not None:
            return self._numbers[block] if 0 <= block < len(self._numbers) else None
        return self._line_map.number(block)

    def last_number(self) -> int:
        count = self.blockCount()
        if self._numbers is not None:
            return max((n for n in self._numbers if n is not None), default=count)
        # The last block can be the marker's: look back for the last one with a number.
        for block in range(count - 1, max(count - 1 - self._line_map.marker_blocks, -1), -1):
            number = self._line_map.number(block)
            if number is not None:
                return number
        return count

    def gutter_width(self) -> int:
        digits = max(MIN_DIGITS, len(str(self.last_number())))
        marker = MARKER_WIDTH if self._diagnostics else 0
        return marker + 2 * GUTTER_PADDING + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, *_args) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        self._place_gutter()

    def _place_gutter(self) -> None:
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def _scroll_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        viewport = self.viewport()
        if viewport is not None and rect.contains(viewport.rect()):
            self._update_margin()

    def _on_cursor_moved(self) -> None:
        self.gutter.update()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._place_gutter()

    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if event is not None and event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._update_margin()

    def paint_gutter(self, event: QPaintEvent) -> None:
        painter = QPainter(self.gutter)
        theme = self.theme
        painter.fillRect(event.rect(), theme.color("gutter_bg"))
        painter.setPen(theme.color("border"))
        painter.drawLine(
            self.gutter.width() - 1,
            event.rect().top(),
            self.gutter.width() - 1,
            event.rect().bottom(),
        )
        painter.setFont(self.font())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        normal, active = theme.color("gutter_fg"), theme.color("gutter_current_fg")
        current = self.textCursor().blockNumber()
        height = self.fontMetrics().height()
        width = self.gutter.width() - GUTTER_PADDING
        block = self.firstVisibleBlock()
        index = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = self.number_at(index)
                if number is not None:
                    painter.setPen(active if index == current else normal)
                    painter.drawText(
                        0, top, width, height, Qt.AlignmentFlag.AlignRight, str(number)
                    )
                issues = self._diagnostics.get(index)
                if issues:
                    severity = "error" if any(i.severity == "error" for i in issues) else "warning"
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(theme.color(severity))
                    painter.drawEllipse(
                        QPoint(MARKER_WIDTH // 2, top + height // 2), MARKER_RADIUS, MARKER_RADIUS
                    )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            index += 1
        painter.end()

    # -- diagnostics -------------------------------------------------------------------------
    def issues_by_block(self, issues: Sequence[LintIssue]) -> dict[int, list[LintIssue]]:
        """Group ``issues`` by the block of their (real) line; lines that are not shown are left out."""
        grouped: dict[int, list[LintIssue]] = {}
        for issue in issues:
            block = self._line_map.block(issue.line)
            if block is not None:
                grouped.setdefault(block, []).append(issue)
        return grouped

    def set_diagnostics(self, issues: Sequence[LintIssue]) -> None:
        """Mark ``issues`` in the margin; they also answer the tooltip. Empty clears them."""
        self._diagnostics = self.issues_by_block(issues)
        self._update_margin()
        self.gutter.update()

    @property
    def diagnostics(self) -> dict[int, list[LintIssue]]:
        return self._diagnostics

    def show_marker_tip(self, event: QHelpEvent) -> None:
        """Tooltip of the margin: every message of the line under the pointer."""
        block = self.cursorForPosition(QPoint(0, event.pos().y())).blockNumber()
        self._show_tip(event, self._diagnostics.get(block, []), self.gutter)

    def viewportEvent(self, event: QEvent | None) -> bool:
        if isinstance(event, QHelpEvent) and event.type() == QEvent.Type.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            column = cursor.positionInBlock()
            # The caret is the nearest gap between characters: left of it, the pointer is on the
            # previous character.
            if event.pos().x() < self.cursorRect(cursor).x():
                column -= 1
            issues = [
                i
                for i in self._diagnostics.get(cursor.blockNumber(), [])
                if i.col_start <= column < i.col_end
            ]
            viewport = self.viewport()
            if viewport is not None:
                self._show_tip(event, issues, viewport)
            return True
        return super().viewportEvent(event)

    @staticmethod
    def _show_tip(event: QHelpEvent, issues: Sequence[LintIssue], widget: QWidget) -> None:
        if issues:
            QToolTip.showText(event.globalPos(), "\n".join(i.message for i in issues), widget)
        else:
            QToolTip.hideText()
            event.ignore()

    # -- navigation --------------------------------------------------------------------------
    def go_start(self) -> None:
        self.moveCursor(QTextCursor.MoveOperation.Start)

    def go_end(self) -> None:
        self.moveCursor(QTextCursor.MoveOperation.End)

    def go_to_line(self, number: int) -> int:
        """Show real line ``number``, centered. An omitted line lands on the marker. Returns the
        block shown."""
        block = self._line_map.block(number)
        if block is None:
            marker = self._line_map.marker_start
            block = (marker if marker is not None else 0) + 1
        block = min(max(block, 0), self.blockCount() - 1)
        cursor = QTextCursor(self.text_document().findBlockByNumber(block))
        self.setTextCursor(cursor)
        self.centerCursor()
        return block

    # -- search ------------------------------------------------------------------------------
    @property
    def match_count(self) -> int:
        return len(self._matches)

    @property
    def current_match(self) -> int:
        return self._current

    def set_search(self, needle: str, case_sensitive: bool = False) -> tuple[int, bool]:
        """Highlight every occurrence of ``needle``: (count, stopped at MAX_MATCHES)."""
        self._matches, self._current = [], -1
        capped = False
        if needle:
            flags = (
                QTextDocument.FindFlag.FindCaseSensitively
                if case_sensitive
                else QTextDocument.FindFlag(0)
            )
            document = self.text_document()
            cursor = QTextCursor(document)
            while True:
                cursor = document.find(needle, cursor, flags)
                if cursor.isNull():
                    break
                if len(self._matches) == MAX_MATCHES:
                    capped = True
                    break
                self._matches.append((cursor.selectionStart(), cursor.selectionEnd()))
        self._apply_selections()
        return len(self._matches), capped

    def nearest_match(self) -> int:
        """Index of the first match from the caret on (wrapping to the first); -1 without any."""
        if not self._matches:
            return -1
        position = self.textCursor().selectionStart()
        return next((i for i, (start, _end) in enumerate(self._matches) if start >= position), 0)

    def goto_match(self, index: int) -> None:
        if not self._matches:
            return
        self._current = index % len(self._matches)
        start, _end = self._matches[self._current]
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._apply_selections()

    def clear_search(self) -> None:
        self._matches, self._current = [], -1
        self._apply_selections()

    def set_row_backgrounds(self, tokens: Mapping[int, str]) -> None:
        """Paint whole lines (``{block: theme token}``): the rows of a diff."""
        self._row_tokens = dict(tokens)
        self._apply_selections()

    def _apply_selections(self) -> None:
        match, current = QTextCharFormat(), QTextCharFormat()
        match.setBackground(self.theme.color("search_match_bg"))
        current.setBackground(self.theme.color("search_current_bg"))
        selections = []
        for block, token in self._row_tokens.items():  # under the search hits
            target = self.text_document().findBlockByNumber(block)
            if not target.isValid():
                continue
            row = QTextEdit.ExtraSelection()
            row.cursor = QTextCursor(target)
            row.format = QTextCharFormat()
            row.format.setBackground(self.theme.color(token))
            row.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(row)
        for i, (start, end) in enumerate(self._matches):
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = current if i == self._current else match
            selections.append(selection)
        self.setExtraSelections(selections)

    def setPlainText(self, text: str | None) -> None:
        self._row_tokens = {}
        self.clear_search()  # offsets belong to the old document
        if self._diagnostics:
            self.set_diagnostics([])
        super().setPlainText(text)

    def _on_theme(self, _name: str = "") -> None:
        self._apply_selections()
        self.gutter.update()
