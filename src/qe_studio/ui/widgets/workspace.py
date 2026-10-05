"""Central workspace: document tabs for text files, images, plots, input diffs and output
summaries (PRD §2.1.3)."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ...core.sniff import looks_like_input
from ..file_types import file_visual
from ..theme.manager import ThemeManager
from .diff_view import DiffView, diff_key, diff_title
from .spinner import CircularProgress
from .summary_view import SummaryView, summary_key
from .text_viewer import TextViewer
from .workspace_tabs import DocumentTabs, add_action

INPUT_FILTER = "Inputs do QE (*.in *.inp *.pw*);;Todos os arquivos (*)"


def copy_text(text: str) -> None:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


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
        elif self.pixmap is not None:
            painter.drawPixmap(target.toRect(), self.pixmap)
        painter.end()


class Workspace(QStackedWidget):
    """Tabs keyed by an identifier (file path or plot key); empty state when none is open."""

    current_changed = pyqtSignal(object)  # the current tab widget or None
    tab_closing = pyqtSignal(object)  # tab widget about to be removed
    external_open_requested = pyqtSignal(Path)  # a text viewer asks for the default program
    reveal_requested = pyqtSignal(Path)  # tab menu "Revelar no explorador"

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
        self.tabs = DocumentTabs()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(14, 14))
        self.addWidget(self.empty)
        self.addWidget(self.tabs)
        self._keys: dict[str, QWidget] = {}
        self._icons: dict[QWidget, tuple[str, str]] = {}
        self._busy: dict[QWidget, CircularProgress] = {}  # tabs showing a spinner for an icon
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.bar.middle_clicked.connect(self.close_tab)
        self.tabs.bar.menu_requested.connect(self._show_tab_menu)
        self.tabs.currentChanged.connect(self._on_current)
        theme.theme_changed.connect(self._refresh_icons)

    def widget_for(self, key: str) -> QWidget | None:
        return self._keys.get(key)

    def keys(self) -> list[str]:
        return list(self._keys)

    @staticmethod
    def shortcut_help() -> list[tuple[str, str, str]]:
        """(action, keys, where) of the tab bar's mouse gestures (Ctrl+W is a menu action)."""
        return [("Fechar a aba", "Botão do meio", "Abas")]

    def items(self) -> list[tuple[str, QWidget]]:
        return list(self._keys.items())

    def cancel_loads(self) -> None:
        """Window close: the tabs that are still reading a file stop (``cancel_load``)."""
        for _key, widget in self.items():
            cancel = getattr(widget, "cancel_load", None)
            if cancel is not None:
                cancel()

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
        if kind == "text":
            widget = TextViewer(path, self.theme)
            widget.external_requested.connect(self.external_open_requested)
            widget.compare_requested.connect(self.compare_with)
        else:
            widget = ImageViewer(path)
        return self.add(key, widget, path.name, file_visual(path), str(path))

    def open_diff(self, a: Path, b: Path) -> QWidget:
        """The tab that compares input ``a`` with ``b`` (spec 11 R6); an open one is shown again."""
        return self.add(
            diff_key(a, b),
            DiffView(a, b, self.theme),
            diff_title(a, b),
            ("difference", "accent"),
            str(a),
        )

    def open_summary(self, path: Path) -> QWidget:
        """The tab "Resumo · <arquivo>" of a QE output (spec 12); an open one is shown again, not
        re-read (its "Atualizar" does that)."""
        key = summary_key(path)
        existing = self._keys.get(key)
        if existing is not None:
            self.tabs.setCurrentWidget(existing)
            return existing
        view = SummaryView(path, self.theme)
        view.open_output_requested.connect(self.open_output)
        return self.add(key, view, f"Resumo · {path.name}", ("summarize", "accent"), str(path))

    def open_output(self, path: Path, line: int = 0) -> None:
        """The output in the text viewer, at ``line`` when given."""
        viewer = self.open_file(path, "text")
        if line and isinstance(viewer, TextViewer):
            viewer.go_to_line(line)

    def compare_with(self, path: Path) -> None:
        """ "Comparar com…": ask for the other input, which must look like one too."""
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Comparar com…", str(path.parent), INPUT_FILTER
        )
        if not chosen:
            return
        other = Path(chosen)
        if not looks_like_input(other):
            QMessageBox.warning(
                self, "Comparar inputs", f"{other.name} não parece um input do Quantum ESPRESSO."
            )
            return
        self.open_diff(path, other)

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        self.tab_closing.emit(widget)
        self._drop_spinner(widget)
        self.tabs.removeTab(index)
        for key, value in list(self._keys.items()):
            if value is widget:
                del self._keys[key]
        self._icons.pop(widget, None)
        widget.deleteLater()
        if self.tabs.count() == 0:
            self.setCurrentWidget(self.empty)
            self.current_changed.emit(None)

    # Every way of closing goes through close_tab: tab_closing flushes the plot settings.
    def close_current(self) -> None:
        if self.tabs.count():
            self.close_tab(self.tabs.currentIndex())

    def close_others(self, index: int) -> None:
        keep = self.tabs.widget(index)
        self._close_widgets([w for w in self._in_order() if w is not keep])

    def close_right(self, index: int) -> None:
        """The tabs after ``index`` in the order shown (tabs can be dragged around)."""
        self._close_widgets(self._in_order()[index + 1 :])

    def close_all(self) -> None:
        self._close_widgets(self._in_order())

    def _in_order(self) -> list[QWidget]:
        widgets = (self.tabs.widget(i) for i in range(self.tabs.count()))
        return [widget for widget in widgets if widget is not None]

    def _close_widgets(self, widgets: list[QWidget]) -> None:
        for widget in widgets:
            self.close_tab(self.tabs.indexOf(widget))

    def _show_tab_menu(self, index: int, pos: QPoint) -> None:
        path = self.tabs.tabToolTip(index)  # the file, or the folder of a plot
        last = self.tabs.count() - 1
        menu = QMenu(self)
        # The shortcut is only shown (after the tab): the real one is the main window's.
        add_action(menu, "Fechar\tCtrl+W", lambda: self.close_tab(index))
        add_action(menu, "Fechar outras", lambda: self.close_others(index), enabled=last > 0)
        add_action(menu, "Fechar à direita", lambda: self.close_right(index), enabled=index < last)
        add_action(menu, "Fechar todas", self.close_all)
        menu.addSeparator()
        add_action(menu, "Copiar caminho", lambda: copy_text(path))
        add_action(menu, "Revelar no explorador", lambda: self.reveal_requested.emit(Path(path)))
        menu.exec(pos)
        menu.deleteLater()

    def close_tabs_under(self, path: Path) -> None:
        """Close every tab that shows something inside ``path`` (renamed or moved away): its
        ``paths`` (a comparison) or its ``path`` (a file, or what a plot shows)."""
        for key, widget in self.items():
            shown = getattr(widget, "paths", None) or (getattr(widget, "path", None),)
            if any(item is not None and Path(item).is_relative_to(path) for item in shown):
                self.close_key(key)

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
            if widget not in self._busy:
                self.tabs.setTabIcon(self.tabs.indexOf(widget), self._icon(icon))

    def set_busy(self, key: str, busy: bool) -> None:
        """A spinner in place of the tab's icon while its plot is generated again (spec 15 R2)."""
        widget = self._keys.get(key)
        if widget is None or busy == (widget in self._busy):
            return
        index = self.tabs.indexOf(widget)
        if busy:
            spinner = CircularProgress(self.theme, 12)
            self._busy[widget] = spinner
            self.tabs.setTabIcon(index, QIcon())
            self.tabs.bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, spinner)
        else:
            self.tabs.bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
            self._drop_spinner(widget)
            self.tabs.setTabIcon(index, self._icon(self._icons[widget]))

    def is_busy(self, key: str) -> bool:
        widget = self._keys.get(key)
        return widget is not None and widget in self._busy

    def _drop_spinner(self, widget: QWidget) -> None:
        spinner = self._busy.pop(widget, None)
        if spinner is not None and not sip.isdeleted(spinner):
            spinner.deleteLater()

    def _on_current(self, _index: int) -> None:
        self.current_changed.emit(self.current())
