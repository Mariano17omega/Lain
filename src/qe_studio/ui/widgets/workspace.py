"""Central workspace: document tabs for text files, images and plots (PRD §2.1.3)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QRectF, QRunnable, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.sniff import sniff
from ..file_types import file_visual, human_size, is_job_log
from ..theme.manager import ThemeManager

LARGE_FILE = 4 * 1024 * 1024
HEAD_BYTES = 1024 * 1024
TAIL_BYTES = 2 * 1024 * 1024


def read_for_viewer(path: Path) -> tuple[str, str]:
    """(text, banner). Large files show their beginning and end (QE logs matter at both ends)."""
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if size <= LARGE_FILE:
            return handle.read().decode("utf-8", "replace"), ""
        head = handle.read(HEAD_BYTES).decode("utf-8", "replace")
        handle.seek(size - TAIL_BYTES)
        tail = handle.read().decode("utf-8", "replace")
    banner = (
        f"Arquivo grande ({human_size(size)}): exibindo o primeiro {human_size(HEAD_BYTES)} "
        f"e os últimos {human_size(TAIL_BYTES)}."
    )
    marker = "\n\n    [ … trecho omitido pelo visualizador … ]\n\n"
    return head + marker + tail, banner


def load_for_viewer(path: Path) -> tuple[str, str, str]:
    """(text, banner, banner level). Queue logs say whether the job wrote errors (spec 4 R4)."""
    text, banner = read_for_viewer(path)
    level = "warning"
    if is_job_log(path):
        qe = sniff(path)
        # A redirected QE output is judged by the run itself, as in the file label.
        if not (qe.is_output and qe.job_done is not None):
            if text:
                job, level = "O job registrou mensagens de erro.", "error"
            else:
                job, level = "Arquivo vazio: o job não registrou erros.", "success"
            banner = f"{job} {banner}".rstrip()
    return text, banner, level


class _LoadSignals(QObject):
    loaded = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)


class _LoadText(QRunnable):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.signals = _LoadSignals()

    def run(self) -> None:
        try:
            loaded = load_for_viewer(self.path)
        except OSError as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.loaded.emit(*loaded)


class TextViewer(QWidget):
    """Read-only preview of QE inputs and logs (PRD §2.1.3 text viewer tab)."""

    loaded = pyqtSignal()

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.banner = QLabel()
        self.banner.setObjectName("viewerBanner")
        self.banner.hide()
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("textViewer")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText("Carregando…")
        layout.addWidget(self.banner)
        layout.addWidget(self.editor, 1)
        self._task = _LoadText(path)
        self._task.signals.loaded.connect(self._on_loaded)
        self._task.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(self._task)

    def _on_loaded(self, text: str, banner: str, level: str) -> None:
        self.editor.setPlainText(text)
        self._set_banner(banner, level)
        self.loaded.emit()

    def _on_failed(self, error: str) -> None:
        self._set_banner(f"Não foi possível abrir o arquivo: {error}", "warning")
        self.loaded.emit()

    def _set_banner(self, text: str, level: str) -> None:
        self.banner.setText(text)
        self.banner.setProperty("level", level)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setVisible(bool(text))


class ImageViewer(QWidget):
    """PNG/JPG/SVG preview, centered with preserved aspect ratio."""

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.path = path
        self.svg = QSvgRenderer(str(path)) if path.suffix.lower() == ".svg" else None
        self.pixmap = None if self.svg else QPixmap(str(path))

    @property
    def natural_size(self) -> QSize:
        if self.svg is not None:
            return self.svg.defaultSize()
        return self.pixmap.size() if self.pixmap is not None else QSize()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        size = self.natural_size
        if size.isEmpty():
            return
        area = self.rect().adjusted(16, 16, -16, -16)
        scaled = size.scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.pixmap is not None and scaled.width() > size.width():
            scaled = size  # never upscale raster images
        target = QRectF(
            area.center().x() - scaled.width() / 2,
            area.center().y() - scaled.height() / 2,
            scaled.width(),
            scaled.height(),
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.svg is not None:
            self.svg.render(painter, target)
        else:
            painter.drawPixmap(target.toRect(), self.pixmap)
        painter.end()


class Workspace(QStackedWidget):
    """Tabs keyed by an identifier (file path or plot key); empty state when none is open."""

    current_changed = pyqtSignal(object)  # the current tab widget or None
    tab_closing = pyqtSignal(object)  # tab widget about to be removed

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.empty = QWidget()
        self.empty.setObjectName("emptyWorkspace")
        self.empty.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        empty_layout = QVBoxLayout(self.empty)
        hint = QLabel(
            "Selecione um arquivo para visualizar\nou use “Gerar Gráfico” em uma pasta de simulação."
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(14, 14))
        self.addWidget(self.empty)
        self.addWidget(self.tabs)
        self._keys: dict[str, QWidget] = {}
        self._icons: dict[QWidget, tuple[str, str]] = {}
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current)
        theme.theme_changed.connect(self._refresh_icons)

    def widget_for(self, key: str) -> QWidget | None:
        return self._keys.get(key)

    def keys(self) -> list[str]:
        return list(self._keys)

    def items(self) -> list[tuple[str, QWidget]]:
        return list(self._keys.items())

    def add(self, key: str, widget: QWidget, title: str, icon: tuple[str, str], tooltip: str = ""):
        existing = self._keys.get(key)
        if existing is not None:
            self.tabs.setCurrentWidget(existing)
            return existing
        self._keys[key] = widget
        self._icons[widget] = icon
        index = self.tabs.addTab(widget, self._icon(icon), title)
        self.tabs.setTabToolTip(index, tooltip or key)
        self.tabs.setCurrentIndex(index)
        self.setCurrentWidget(self.tabs)
        return widget

    def open_file(self, path: Path, kind: str) -> QWidget:
        key = str(path)
        if key in self._keys:
            self.tabs.setCurrentWidget(self._keys[key])
            return self._keys[key]
        widget = TextViewer(path) if kind == "text" else ImageViewer(path)
        return self.add(key, widget, path.name, file_visual(path), str(path))

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        self.tab_closing.emit(widget)
        self.tabs.removeTab(index)
        for key, value in list(self._keys.items()):
            if value is widget:
                del self._keys[key]
        self._icons.pop(widget, None)
        widget.deleteLater()
        if self.tabs.count() == 0:
            self.setCurrentWidget(self.empty)
            self.current_changed.emit(None)

    def close_key(self, key: str) -> None:
        widget = self._keys.get(key)
        if widget is not None:
            self.close_tab(self.tabs.indexOf(widget))

    def current(self) -> QWidget | None:
        return self.tabs.currentWidget() if self.tabs.count() else None

    def set_current(self, widget: QWidget) -> None:
        self.tabs.setCurrentWidget(widget)

    def _icon(self, icon: tuple[str, str]) -> QIcon:
        return self.theme.icon(icon[0], icon[1], size=14)

    def _refresh_icons(self, *_args) -> None:
        for widget, icon in self._icons.items():
            self.tabs.setTabIcon(self.tabs.indexOf(widget), self._icon(icon))

    def _on_current(self, _index: int) -> None:
        self.current_changed.emit(self.current())
