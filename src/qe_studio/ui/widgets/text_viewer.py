"""Text viewer tab: QE inputs and logs, with search, highlighting and line numbers (spec 10).
QE inputs also get write-error marks and navigation (spec 11); ``.qsub`` scripts the write-error
marks (spec 38 R2) and Markdown files a rendered view next to the text (spec 38 R1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core import textfile
from ...core.file_kinds import is_markdown
from ...core.qe.input_lexer import LintIssue
from ...core.tasks import TaskHandle, run_task
from ...core.text_preview import TextPreview, read_preview
from ...i18n import _
from ..theme.manager import ThemeManager
from .code_view import CodeView
from .highlighters import InputHighlighter, OutputHighlighter, ShellHighlighter, ThemedHighlighter
from .input_view import InputView
from .markdown_view import MarkdownView
from .search_bar import SearchBar

log = logging.getLogger(__name__)
TOO_BIG = _("Arquivo grande demais para o visualizador: use o editor externo")
RENDER_TOO_BIG = _("Arquivo grande demais para renderizar (mais de 1 MB): mostrado como texto")
MARKDOWN_KEY = (
    "viewer/markdown_rendered"  # QSettings: the choice of the whole program (default: on)
)
# (name, keys, what it does): the one table the QShortcuts and "Ajuda ▸ Atalhos de teclado" read.
SHORTCUTS = (
    ("find", "Ctrl+F", _("Buscar no texto")),
    ("next", "F3", _("Próxima ocorrência")),
    ("previous", "Shift+F3", _("Ocorrência anterior")),
    ("line", "Ctrl+L", _("Ir à linha")),
    ("start", "Ctrl+Home", _("Ir ao início")),
    ("end", "Ctrl+End", _("Ir ao fim")),
    ("next_issue", "F8", _("Próximo problema de escrita")),
    ("previous_issue", "Shift+F8", _("Problema anterior de escrita")),
    ("escape", "Esc", _("Fechar a busca")),
)


def _tool(text: str, tip: str) -> QToolButton:
    button = QToolButton()
    button.setProperty("variant", "viewerTool")
    button.setText(text)
    button.setToolTip(tip)
    return button


class TextViewer(QWidget):
    """Read-only view of QE inputs and logs (PRD §2.1.3 text viewer tab)."""

    loaded = pyqtSignal()
    external_requested = pyqtSignal(Path)  # "Abrir no editor externo"
    compare_requested = pyqtSignal(Path)  # "Comparar com…" of an input: this file
    render_mode_changed = pyqtSignal(bool)  # the user clicked Texto / Renderizado (True: rendered)
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms): a link not followed

    def __init__(
        self,
        path: Path,
        theme: ThemeManager,
        parent: QWidget | None = None,
        settings: QSettings | None = None,
    ):
        super().__init__(parent)
        self.path = path
        self.theme = theme
        self._settings = settings
        self._loading = False
        # Markdown: what the program chose (``_rendered``), what is on show (``_viewing_rendered``:
        # Ctrl+F shows the text of this tab without changing the choice), whether the file can be
        # rendered, and whether the view lags behind the text (a reload).
        self._rendered = settings.value(MARKDOWN_KEY, True, type=bool) if settings else True
        self._viewing_rendered = False
        self._renderable = False
        self._markdown_dirty = False
        self._markdown_text = ""
        self._pending_line: int | None = None  # a go_to_line that came while loading
        self._highlighter: ThemedHighlighter | None = None
        self._task: TaskHandle | None = None  # the read in progress (cancelled when we die)
        self._size: int | None = None  # of the last read: "Carregar tudo" needs no stat()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.banner_bar = QWidget()
        self.banner_bar.setObjectName("viewerBannerBar")
        self.banner_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        banner_layout = QHBoxLayout(self.banner_bar)
        banner_layout.setContentsMargins(8, 3, 8, 3)
        banner_layout.setSpacing(6)
        self.banner = QLabel()
        self.banner.setObjectName("viewerBanner")
        self.external_button = QPushButton(_("Abrir no editor externo"))
        self.load_all_button = QPushButton(_("Carregar tudo"))
        banner_layout.addWidget(self.banner, 1)
        banner_layout.addWidget(self.external_button)
        banner_layout.addWidget(self.load_all_button)
        self.banner_bar.hide()

        self.tools = QWidget()
        self.tools.setObjectName("viewerBar")
        self.tools.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tools_layout = QHBoxLayout(self.tools)
        tools_layout.setContentsMargins(8, 2, 8, 2)
        tools_layout.setSpacing(4)
        self.text_button = _tool(_("Texto"), _("Mostrar o texto do arquivo"))
        self.rendered_button = _tool(_("Renderizado"), _("Mostrar o Markdown renderizado"))
        modes = QButtonGroup(self)  # two positions: one is always on
        for button in (self.text_button, self.rendered_button):
            button.setCheckable(True)
            button.setVisible(is_markdown(path))
            modes.addButton(button)
            tools_layout.addWidget(button)
        tools_layout.addStretch(1)
        self.start_button = _tool(_("Ir ao início"), _("Ir ao início (Ctrl+Home)"))
        self.end_button = _tool(_("Ir ao fim"), _("Ir ao fim (Ctrl+End)"))
        self.line_button = _tool(_("Ir à linha…"), _("Ir à linha (Ctrl+L)"))
        for button in (self.start_button, self.end_button, self.line_button):
            tools_layout.addWidget(button)

        self.editor = CodeView(theme)
        self.markdown = MarkdownView(theme)
        self.stack = QStackedWidget()  # the text, or the rendered Markdown
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.markdown)
        self.search = SearchBar(self.editor)
        self.input_view = InputView(self.editor)
        for widget in (self.banner_bar, self.input_view, self.tools, self.search):
            layout.addWidget(widget)
        layout.addWidget(self.stack, 1)

        self.text_button.clicked.connect(self._pick_text)
        self.rendered_button.clicked.connect(self._pick_rendered)
        self.markdown.message.connect(self.message)
        self.external_button.clicked.connect(self._open_external)
        self.input_view.compare_requested.connect(self._request_compare)
        self.load_all_button.clicked.connect(self.load_all)
        self.start_button.clicked.connect(self.editor.go_start)
        self.end_button.clicked.connect(self.editor.go_end)
        self.line_button.clicked.connect(self.ask_line)
        self.search.closed.connect(self._on_search_closed)
        self._shortcuts: dict[str, QShortcut] = {}
        slots = {
            "find": self.open_search,
            "next": self.next_match,
            "previous": self.previous_match,
            "line": self.ask_line,
            "start": self.go_start,
            "end": self.go_end,
            "next_issue": self.input_view.goto_next,
            "previous_issue": self.input_view.goto_previous,
            "escape": self.search.dismiss,
        }
        for name, keys, _what in SHORTCUTS:
            self._shortcuts[name] = self._shortcut(keys, slots[name])
        # Esc only means something while the bar is open: otherwise the key goes on its way.
        self._shortcuts["escape"].setEnabled(False)
        self._start_load(full=False)

    @staticmethod
    def shortcut_help() -> list[tuple[str, str, str]]:
        """(action, keys, where) for "Ajuda ▸ Atalhos de teclado"; needs no open tab."""
        return [(what, keys, _("Visualizador de texto")) for _name, keys, what in SHORTCUTS]

    def _shortcut(self, keys: str, slot) -> QShortcut:
        """Active only while the focus is inside this viewer: Ctrl+F in the explorer or the grid
        is another feature (spec 10 R1.4)."""
        shortcut = QShortcut(QKeySequence(keys), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(slot)
        return shortcut

    # -- loading -----------------------------------------------------------------------------
    @property
    def loading(self) -> bool:
        return self._loading

    def _start_load(self, full: bool) -> None:
        self._loading = True
        self.search.set_busy(True)
        self._shortcuts["escape"].setEnabled(False)
        self.load_all_button.setEnabled(False)
        self.external_button.setEnabled(False)
        self.rendered_button.setEnabled(False)  # until the read says whether it can be rendered
        self._show(False)  # the editor's placeholder says "Carregando…"
        self.editor.setPlainText("")
        if self._task is not None:
            self._task.cancel()
        self._task = run_task(
            read_preview, self.path, full, on_done=self._on_loaded, on_error=self._on_failed
        )

    def cancel_load(self) -> None:
        """Window close: the read in progress is not wanted any more."""
        if self._task is not None:
            self._task.cancel()

    def load_all(self) -> None:
        """Read the whole file ("Carregar tudo"): up to ``LOAD_ALL_LIMIT``."""
        size = self._size
        if not self._loading and size is not None and size <= textfile.LOAD_ALL_LIMIT:
            self._start_load(full=True)

    def _on_loaded(self, loaded: TextPreview) -> None:
        self._loading = False
        self._size = loaded.size
        self.editor.setPlainText(loaded.text)
        self.editor.set_line_map(loaded.line_map)
        issues = loaded.issues
        self._highlight(loaded, self.editor.issues_by_block(issues))
        self.editor.set_diagnostics(issues)
        if loaded.is_script:
            self.input_view.bind_issues(issues, "script")
        else:
            self.input_view.bind(loaded.input_doc, loaded.chips)
        self._renderable = loaded.renderable
        self._markdown_text, self._markdown_dirty = loaded.text, loaded.renderable
        self.rendered_button.setEnabled(loaded.renderable)
        self.rendered_button.setToolTip(
            _("Mostrar o Markdown renderizado") if loaded.renderable else RENDER_TOO_BIG
        )
        self._show(self._rendered)
        self._set_banner(loaded.banner, loaded.level)
        large = loaded.size > textfile.LARGE_FILE
        self.external_button.setVisible(large)
        self.external_button.setEnabled(True)
        self.load_all_button.setVisible(loaded.truncated)
        fits = loaded.size <= textfile.LOAD_ALL_LIMIT
        self.load_all_button.setEnabled(fits)
        self.load_all_button.setToolTip("" if fits else TOO_BIG)
        self.search.set_busy(False)
        self.search.refresh()
        self._shortcuts["escape"].setEnabled(not self.search.isHidden())
        if self._pending_line is not None:
            self.editor.go_to_line(self._pending_line)
            self._pending_line = None
        self.loaded.emit()

    def _highlight(self, loaded: TextPreview, by_block: dict[int, list[LintIssue]]) -> None:
        """The highlighter of what was read: made once, and its issues set at every load."""
        if self._highlighter is None:
            kind = (
                InputHighlighter
                if loaded.is_input
                else ShellHighlighter
                if loaded.is_script
                else OutputHighlighter
                if loaded.highlight
                else None
            )
            if kind is not None:
                self._highlighter = kind(self.editor.text_document(), self.theme, by_block)
        elif isinstance(self._highlighter, InputHighlighter | ShellHighlighter):
            self._highlighter.set_issues(by_block)

    # -- Markdown: text or rendered ----------------------------------------------------------
    @property
    def viewing_rendered(self) -> bool:
        return self._viewing_rendered

    def set_rendered(self, rendered: bool, remember: bool = True) -> None:
        """Choose the rendered view (or the text) for the program: ``remember`` writes it to the
        settings. A file that cannot be rendered stays on the text."""
        self._rendered = rendered
        if remember and self._settings is not None:
            self._settings.setValue(MARKDOWN_KEY, rendered)
        self._show(rendered)

    def _pick_text(self) -> None:
        self.set_rendered(False)
        self.render_mode_changed.emit(False)

    def _pick_rendered(self) -> None:
        self.set_rendered(True)
        self.render_mode_changed.emit(True)

    def _show(self, rendered: bool) -> None:
        """Put the rendered view (when the file allows it and is read) or the text on show."""
        rendered = rendered and self._renderable and not self._loading
        if rendered:
            if not self.search.isHidden():  # the search is the text's
                self.search.dismiss()
            if self._markdown_dirty:
                self.markdown.set_source(self._markdown_text, self.path.parent)
                self._markdown_dirty = False
        self._viewing_rendered = rendered
        self.stack.setCurrentWidget(self.markdown if rendered else self.editor)
        for button in (self.start_button, self.end_button, self.line_button):
            button.setVisible(not rendered)  # line numbers are the text's
        self.text_button.setChecked(not rendered)
        self.rendered_button.setChecked(rendered)

    def _on_failed(self, error: Exception) -> None:
        self._loading = False
        self._pending_line = None
        self.search.set_busy(False)
        self._shortcuts["escape"].setEnabled(not self.search.isHidden())
        if not isinstance(error, OSError):  # a parser bug: the banner says it, the log has it
            log.error("cannot show %s", self.path, exc_info=error)
        self._set_banner(
            _("Não foi possível abrir o arquivo: {error}").format(error=error), "warning"
        )
        self.loaded.emit()

    def _set_banner(self, text: str, level: str) -> None:
        self.banner.setText(text)
        self.banner.setProperty("level", level)
        style = self.banner.style()
        if style is not None:
            style.unpolish(self.banner)
            style.polish(self.banner)
        self.banner.setVisible(bool(text))
        self.banner_bar.setVisible(bool(text))

    def _open_external(self) -> None:
        self.external_requested.emit(self.path)

    def _request_compare(self) -> None:
        self.compare_requested.emit(self.path)

    # -- search and navigation ---------------------------------------------------------------
    def open_search(self) -> None:
        if self._loading:
            return
        if self._viewing_rendered:  # the search is the text's: this tab shows it, the choice stays
            self._show(False)
        selected = self.editor.textCursor().selectedText()
        if selected and " " not in selected:
            self.search.field.setText(selected)
        self.search.open()
        self._shortcuts["escape"].setEnabled(True)

    def next_match(self) -> None:
        if self._viewing_rendered:
            self.open_search()
        else:
            self.search.next_match()

    def previous_match(self) -> None:
        if self._viewing_rendered:
            self.open_search()
        else:
            self.search.previous_match()

    def go_start(self) -> None:
        (self.markdown if self._viewing_rendered else self.editor).go_start()

    def go_end(self) -> None:
        (self.markdown if self._viewing_rendered else self.editor).go_end()

    def _on_search_closed(self) -> None:
        self._shortcuts["escape"].setEnabled(False)

    def go_to_line(self, number: int) -> None:
        """Show real line ``number`` (a double click in the output summary); once the file arrives
        if it is still loading."""
        if self._loading:
            self._pending_line = number
        else:
            self.editor.go_to_line(number)

    def ask_line(self) -> None:
        if self._loading or self._viewing_rendered:
            return
        last = self.editor.last_number()
        current = self.editor.number_at(self.editor.textCursor().blockNumber()) or 1
        number, ok = QInputDialog.getInt(self, _("Ir à linha"), _("Linha:"), current, 1, last)
        if ok:
            self.editor.go_to_line(number)
