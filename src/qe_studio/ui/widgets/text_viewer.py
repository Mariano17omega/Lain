"""Text viewer tab: QE inputs and logs, with search, highlighting and line numbers (spec 10).
QE inputs also get write-error marks and navigation (spec 11)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core import textfile
from ...core.qe.input_extract import Chip, extract
from ...core.qe.input_lint import InputDoc, lint
from ...core.sniff import INPUT_READ_LIMIT, FileSniff, looks_like_input, sniff
from ...core.textfile import LineMap
from ..file_types import human_size, is_job_log
from ..theme.manager import ThemeManager
from .code_view import CodeView
from .highlighters import InputHighlighter, OutputHighlighter, ThemedHighlighter
from .input_view import InputView
from .search_bar import SearchBar

TOO_BIG = "Arquivo grande demais para o visualizador: use o editor externo"


@dataclass(frozen=True)
class Loaded:
    """What the worker hands to the viewer."""

    text: str
    banner: str
    level: str  # warning / success / error: the banner's color
    line_map: LineMap
    size: int
    highlight: bool  # QE output or job log: color it
    is_input: bool = False  # a QE input: color it as one
    input_doc: InputDoc | None = None  # its lint; None when too big to check (R4.2)
    chips: tuple[Chip, ...] = ()  # its extract

    @property
    def truncated(self) -> bool:
        return self.line_map.truncated


def _sniff(path: Path) -> FileSniff | None:
    try:
        return sniff(path)
    except OSError:
        return None


def load_for_viewer(path: Path, full: bool = False) -> Loaded:
    """Text, banner and line numbers of ``path``. Queue logs say whether the job wrote errors
    (spec 4 R4); a large file is cut to its ends unless ``full`` (spec 10 R4)."""
    piece = textfile.read_slice(path, full=full)
    banner, level = "", "warning"
    if piece.truncated:
        banner = (
            f"Arquivo grande ({human_size(piece.size)}): exibindo o primeiro "
            f"{human_size(textfile.HEAD_BYTES)} e os últimos {human_size(textfile.TAIL_BYTES)}."
        )
    elif full and piece.size > textfile.LARGE_FILE:
        banner = f"Arquivo completo ({human_size(piece.size)})."
    job_log = is_job_log(path)
    info = _sniff(path)
    output = info is not None and info.is_output
    # A redirected QE output is judged by the run itself, as in the file label.
    judged_by_run = output and info is not None and info.job_done is not None
    if job_log and not judged_by_run:
        if piece.text:
            job, level = "O job registrou mensagens de erro.", "error"
        else:
            job, level = "Arquivo vazio: o job não registrou erros.", "success"
        banner = f"{job} {banner}".rstrip()
    is_input = not (job_log or output) and looks_like_input(path)
    doc = None
    if is_input:
        if piece.size <= INPUT_READ_LIMIT:  # below the viewer's own limit: the text is whole
            doc = lint(piece.text)
        else:
            note = f"Input grande ({human_size(piece.size)}): a escrita não foi verificada, só o realce."
            banner = f"{note} {banner}".rstrip()
    chips = extract(doc) if doc is not None else ()
    return Loaded(
        piece.text,
        banner,
        level,
        piece.line_map,
        piece.size,
        job_log or output,
        is_input,
        doc,
        chips,
    )


class _LoadSignals(QObject):
    loaded = pyqtSignal(object)  # Loaded
    failed = pyqtSignal(str)


class _LoadText(QRunnable):
    def __init__(self, path: Path, full: bool = False):
        super().__init__()
        self.path, self.full = path, full
        self.signals = _LoadSignals()

    def run(self) -> None:
        try:
            loaded = load_for_viewer(self.path, self.full)
        except OSError as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.loaded.emit(loaded)


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

    def __init__(self, path: Path, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.theme = theme
        self._loading = False
        self._highlighter: ThemedHighlighter | None = None
        self._task: _LoadText | None = None
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
        self.external_button = QPushButton("Abrir no editor externo")
        self.load_all_button = QPushButton("Carregar tudo")
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
        tools_layout.addStretch(1)
        self.start_button = _tool("Ir ao início", "Ir ao início (Ctrl+Home)")
        self.end_button = _tool("Ir ao fim", "Ir ao fim (Ctrl+End)")
        self.line_button = _tool("Ir à linha…", "Ir à linha (Ctrl+L)")
        for button in (self.start_button, self.end_button, self.line_button):
            tools_layout.addWidget(button)

        self.editor = CodeView(theme)
        self.search = SearchBar(self.editor)
        self.input_view = InputView(self.editor)
        for widget in (self.banner_bar, self.input_view, self.tools, self.search):
            layout.addWidget(widget)
        layout.addWidget(self.editor, 1)

        self.external_button.clicked.connect(self._open_external)
        self.input_view.compare_requested.connect(self._request_compare)
        self.load_all_button.clicked.connect(self.load_all)
        self.start_button.clicked.connect(self.editor.go_start)
        self.end_button.clicked.connect(self.editor.go_end)
        self.line_button.clicked.connect(self.ask_line)
        self.search.closed.connect(self._on_search_closed)
        self._shortcuts: dict[str, QShortcut] = {}
        for name, keys, slot in (
            ("find", "Ctrl+F", self.open_search),
            ("next", "F3", self.search.next_match),
            ("previous", "Shift+F3", self.search.previous_match),
            ("line", "Ctrl+L", self.ask_line),
            ("start", "Ctrl+Home", self.editor.go_start),
            ("end", "Ctrl+End", self.editor.go_end),
            ("next_issue", "F8", self.input_view.goto_next),
            ("previous_issue", "Shift+F8", self.input_view.goto_previous),
            ("escape", "Esc", self.search.dismiss),
        ):
            self._shortcuts[name] = self._shortcut(keys, slot)
        # Esc only means something while the bar is open: otherwise the key goes on its way.
        self._shortcuts["escape"].setEnabled(False)
        self._start_load(full=False)

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
        self.editor.setPlainText("")  # the placeholder says "Carregando…"
        previous = self._task
        task = _LoadText(self.path, full)
        task.signals.loaded.connect(self._on_loaded)
        task.signals.failed.connect(self._on_failed)
        self._task = task
        if previous is not None:
            # The finished task's signal object may still be running this slot.
            QTimer.singleShot(0, lambda: previous)
        pool = QThreadPool.globalInstance()
        assert pool is not None
        pool.start(task)

    def load_all(self) -> None:
        """Read the whole file ("Carregar tudo"): up to ``LOAD_ALL_LIMIT``."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if not self._loading and size <= textfile.LOAD_ALL_LIMIT:
            self._start_load(full=True)

    def _on_loaded(self, loaded: Loaded) -> None:
        self._loading = False
        self.editor.setPlainText(loaded.text)
        self.editor.set_line_map(loaded.line_map)
        issues = loaded.input_doc.issues if loaded.input_doc is not None else []
        if loaded.is_input:
            by_block = self.editor.issues_by_block(issues)
            if isinstance(self._highlighter, InputHighlighter):
                self._highlighter.set_issues(by_block)
            elif self._highlighter is None:
                self._highlighter = InputHighlighter(
                    self.editor.text_document(), self.theme, by_block
                )
        elif loaded.highlight and self._highlighter is None:
            self._highlighter = OutputHighlighter(self.editor.text_document(), self.theme)
        self.editor.set_diagnostics(issues)
        self.input_view.bind(loaded.input_doc, loaded.chips)
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
        self.loaded.emit()

    def _on_failed(self, error: str) -> None:
        self._loading = False
        self.search.set_busy(False)
        self._shortcuts["escape"].setEnabled(not self.search.isHidden())
        self._set_banner(f"Não foi possível abrir o arquivo: {error}", "warning")
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
        selected = self.editor.textCursor().selectedText()
        if selected and " " not in selected:
            self.search.field.setText(selected)
        self.search.open()
        self._shortcuts["escape"].setEnabled(True)

    def _on_search_closed(self) -> None:
        self._shortcuts["escape"].setEnabled(False)

    def ask_line(self) -> None:
        if self._loading:
            return
        last = self.editor.last_number()
        current = self.editor.number_at(self.editor.textCursor().blockNumber()) or 1
        number, ok = QInputDialog.getInt(self, "Ir à linha", "Linha:", current, 1, last)
        if ok:
            self.editor.go_to_line(number)
