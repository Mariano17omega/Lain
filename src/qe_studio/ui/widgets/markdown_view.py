"""The rendered view of a Markdown file in the text viewer (spec 38 R1).

``QTextDocument.setMarkdown`` with ``GitHub | NoHTML``: tables, task lists and code blocks come out
as structure and raw HTML is shown as the text it is. Two things are deliberate:

- **Theming is a format pass.** ``setDefaultStyleSheet`` only reaches ``setHtml``: Qt's Markdown
  import writes char and block formats directly, so after ``setMarkdown`` one walk over the document
  gives links, code and tables their theme colors. Text color and background are the QSS of
  ``#markdownView``; headings keep the importer's bold and size.
- **Nothing local or remote is followed.** The viewer opens files of synced cluster folders the user
  did not write: only a web address opens (in the browser) and an ``#anchor`` scrolls
  (``core/markdown_links``); other links say so in the footer, and an image loads only from a
  relative path (never a URL, never fetched).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QDesktopServices,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextFrame,
    QTextFrameFormat,
    QTextTable,
)
from PyQt6.QtWidgets import QTextBrowser, QWidget

from ...core.markdown_links import heading_slugs, link_action
from ..painting import mono_font
from ..theme.manager import ThemeManager

Feature = QTextDocument.MarkdownFeature
FEATURES = Feature.MarkdownDialectGitHub | Feature.MarkdownNoHTML
CELL_PADDING = 4
PAGE_MARGIN = 16
MESSAGE_MS = 5000


def open_url(url: QUrl) -> bool:
    """The one place a link leaves the app (what the tests replace)."""
    return QDesktopServices.openUrl(url)


class MarkdownView(QTextBrowser):
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("markdownView")
        self.setOpenLinks(False)  # anchorClicked decides: nothing navigates by itself
        self.setOpenExternalLinks(False)
        self._source = ""
        self._folder: Path | None = None
        self.anchorClicked.connect(self._on_link)
        theme.theme_changed.connect(self._on_theme)  # a bound method: dies with the view

    def text_document(self) -> QTextDocument:
        document = self.document()
        assert document is not None
        return document

    # -- content -----------------------------------------------------------------------------
    @property
    def source(self) -> str:
        return self._source

    def set_source(self, text: str, folder: Path) -> None:
        """Render ``text``; a relative image resolves in ``folder`` (the file's own)."""
        self._source, self._folder = text, folder
        document = self.text_document()
        document.setUndoRedoEnabled(False)  # read-only: the history would only grow
        document.setDocumentMargin(PAGE_MARGIN)
        self.setSearchPaths([str(folder)])
        document.setMarkdown(text, FEATURES)
        self._style(document)
        self.go_start()  # the import leaves the caret, and so the view, at the end

    def _on_theme(self, _name: str = "") -> None:
        if self._folder is None:
            return
        bar = self.verticalScrollBar()
        value = bar.value() if bar is not None else 0
        self.set_source(self._source, self._folder)
        if bar is not None:
            bar.setValue(value)

    def _style(self, document: QTextDocument) -> None:
        """Theme colors where the importer left Qt's defaults: links, inline code, code blocks and
        the borders of tables. One read walk collects the spans; the formats are merged after it,
        so no iterator lives across an edit."""
        theme = self.theme
        link = QBrush(theme.color("accent"))
        code_fg = QBrush(theme.color("text_secondary"))
        code_bg = QBrush(theme.color("card"))
        family = mono_font().family()
        fence = QTextFormat.Property.BlockCodeFence
        links: list[tuple[int, int]] = []
        inline: list[tuple[int, int]] = []
        blocks: list[tuple[int, int]] = []
        block = document.begin()
        while block.isValid():
            fenced = block.blockFormat().hasProperty(fence)
            if fenced:
                blocks.append((block.position(), block.length() - 1))
            fragments = block.begin()
            while not fragments.atEnd():
                fragment = fragments.fragment()
                fmt = fragment.charFormat()
                span = (fragment.position(), fragment.length())
                if fmt.isAnchor():
                    links.append(span)
                elif fmt.fontFixedPitch() and not fenced:
                    inline.append(span)
                fragments += 1
            block = block.next()

        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        for spans, fmt in (
            (links, _char(foreground=link)),
            (inline, _char(foreground=code_fg, background=code_bg, family=family)),
            (blocks, _char(foreground=code_fg, family=family)),
        ):
            for position, length in spans:
                cursor.setPosition(position)
                cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
        shade = QTextBlockFormat()
        shade.setBackground(code_bg)
        for position, _length in blocks:  # the whole width, not only under the text
            cursor.setPosition(position)
            cursor.mergeBlockFormat(shade)
        root = document.rootFrame()
        for table in _tables(root) if root is not None else []:
            fmt = table.format()
            fmt.setBorder(1)
            fmt.setBorderBrush(QBrush(theme.color("border")))
            fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            fmt.setCellPadding(CELL_PADDING)
            fmt.setCellSpacing(0)
            table.setFormat(fmt)
        cursor.endEditBlock()

    # -- links and images --------------------------------------------------------------------
    def _on_link(self, url: QUrl) -> None:
        action = link_action(url.toString())
        if action.kind == "open":
            open_url(QUrl(action.target))
        elif action.kind == "anchor":
            self.scroll_to_heading(action.target)
        else:
            self.message.emit(f"Link não aberto: {action.target}", "warning", MESSAGE_MS)

    def headings(self) -> list[tuple[str, QTextBlock]]:
        """(slug, block) of every heading, in document order."""
        found: list[QTextBlock] = []
        block = self.text_document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                found.append(block)
            block = block.next()
        return list(zip(heading_slugs(b.text() for b in found), found, strict=True))

    def scroll_to_heading(self, slug: str) -> bool:
        """Show the heading whose GitHub slug is ``slug``; False when there is none."""
        wanted = slug.lower()
        for name, block in self.headings():
            if name == wanted:
                cursor = QTextCursor(block)
                self.setTextCursor(cursor)
                bar = self.verticalScrollBar()
                if bar is not None:  # the heading at the top of the page
                    bar.setValue(bar.value() + self.cursorRect(cursor).top())
                return True
        return False

    def loadResource(self, type: int, name: QUrl) -> Any:
        """Only a relative path is read (from the file's folder): no URL, so nothing is fetched."""
        if name.scheme() or name.path().startswith("/"):
            return None
        return super().loadResource(type, name)

    # -- navigation --------------------------------------------------------------------------
    def go_start(self) -> None:
        self.moveCursor(QTextCursor.MoveOperation.Start)
        self._scroll_to(0)

    def go_end(self) -> None:
        self.moveCursor(QTextCursor.MoveOperation.End)
        bar = self.verticalScrollBar()
        self._scroll_to(bar.maximum() if bar is not None else 0)

    def _scroll_to(self, value: int) -> None:
        """The caret only has to be visible; Ctrl+Home / Ctrl+End mean the very top and bottom."""
        bar = self.verticalScrollBar()
        if bar is not None:
            bar.setValue(value)


def _char(
    foreground: QBrush | None = None, background: QBrush | None = None, family: str | None = None
) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if foreground is not None:
        fmt.setForeground(foreground)
    if background is not None:
        fmt.setBackground(background)
    if family is not None:
        fmt.setFontFamilies([family])
    return fmt


def _tables(frame: QTextFrame) -> list[QTextTable]:
    found: list[QTextTable] = []
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            found.append(child)
        found.extend(_tables(child))
    return found
