"""Central workspace: document tabs for text files, images, plots, input diffs and output
summaries (PRD §2.1.3)."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRectF, QSettings, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ....core.files.image_file import read_image
from ....core.sniff import looks_like_input
from ....core.tasks import TaskHandle, run_task
from ....i18n import _
from ...theme.manager import ThemeManager
from ..common import copy_text
from ..files.file_types import file_visual
from ..spinner import CircularProgress
from ..viewer.diff_view import DiffView, diff_key, diff_title
from ..viewer.summary_view import SummaryView, summary_key
from ..viewer.text_viewer import TextViewer
from .workspace_tabs import DocumentTabs, add_action

log = logging.getLogger(__name__)

INPUT_FILTER = _("Inputs do QE (*.in *.inp *.pw*);;Todos os arquivos (*)")


def _decode(path: Path) -> QImage | bytes:
    """The worker's half of opening an image: the file is read here, and a raster is decoded here
    (a ``QImage`` may be made off the GUI thread, a ``QPixmap`` may not). An SVG stays bytes: its
    renderer is a ``QObject`` that the GUI thread makes."""
    data = read_image(path)
    return data if path.suffix.lower() == ".svg" else QImage.fromData(data)


class ImageViewer(QWidget):
    """PNG/JPG/SVG preview, centered with preserved aspect ratio. The file is read and decoded in
    a worker (blank until then, and when it cannot be read); the picture is scaled when its size
    changes, not at every paint."""

    loaded = pyqtSignal()  # the picture is ready, or it could not be read

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.path = path
        self.svg: QSvgRenderer | None = None
        self.image: QImage | None = None
        self._scaled: tuple[QSize, QPixmap] | None = None  # the picture at the last size drawn
        self._task: TaskHandle | None = run_task(
            _decode, path, on_done=self._on_decoded, on_error=self._on_failed
        )

    def cancel_load(self) -> None:
        """Window close: the read in progress is not wanted any more."""
        if self._task is not None:
            self._task.cancel()

    def _on_decoded(self, result: QImage | bytes) -> None:
        self._task = None
        if isinstance(result, QImage):
            self.image = None if result.isNull() else result
        else:
            renderer = QSvgRenderer(result)
            self.svg = renderer if renderer.isValid() else None
        self.update()
        self.loaded.emit()

    def _on_failed(self, error: Exception) -> None:
        self._task = None
        log.warning("file: cannot show the image %s: %s", self.path, error)
        self.loaded.emit()

    @property
    def natural_size(self) -> QSize:
        if self.svg is not None:
            return self.svg.defaultSize()
        return self.image.size() if self.image is not None else QSize()

    def _pixmap_at(self, size: QSize) -> QPixmap | None:
        """The raster scaled to ``size`` (kept while the size stays the same)."""
        if self.image is None:
            return None
        if self._scaled is None or self._scaled[0] != size:
            image = self.image
            if size != image.size():
                image = image.scaled(
                    size,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            self._scaled = (size, QPixmap.fromImage(image))
        return self._scaled[1]

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        size = self.natural_size
        if size.isEmpty():
            return
        area = self.rect().adjusted(16, 16, -16, -16)
        scaled = size.scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.image is not None and scaled.width() > size.width():
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
        elif (pixmap := self._pixmap_at(scaled)) is not None:
            painter.drawPixmap(target.toRect().topLeft(), pixmap)  # already the drawn size
        painter.end()


class Workspace(QStackedWidget):
    """Tabs keyed by an identifier (file path or plot key); empty state when none is open."""

    current_changed = pyqtSignal(object)  # the current tab widget or None
    tab_closing = pyqtSignal(object)  # tab widget about to be removed
    external_open_requested = pyqtSignal(Path)  # a text viewer asks for the default program
    reveal_requested = pyqtSignal(Path)  # tab menu "Revelar no explorador"
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms): from the text viewers

    def __init__(
        self,
        theme: ThemeManager,
        parent: QWidget | None = None,
        settings: QSettings | None = None,
    ):
        super().__init__(parent)
        self.theme = theme
        self._settings = settings  # where a text viewer keeps "Texto / Renderizado"
        self.empty = QWidget()
        self.empty.setObjectName("emptyWorkspace")
        self.empty.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        empty_layout = QVBoxLayout(self.empty)
        hint = QLabel(
            _(
                "Selecione um arquivo para visualizar\n"
                "ou use “Gerar Gráfico” em uma pasta de simulação."
            )
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
        return [(_("Fechar a aba"), _("Botão do meio"), _("Abas"))]

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
        log.debug("tab: %s (%s)", path, kind)
        key = str(path)
        if key in self._keys:
            self.tabs.setCurrentWidget(self._keys[key])
            return self._keys[key]
        if kind == "text":
            widget = TextViewer(path, self.theme, settings=self._settings)
            widget.external_requested.connect(self.external_open_requested)
            widget.compare_requested.connect(self.compare_with)
            widget.render_mode_changed.connect(self._sync_render_mode)
            widget.message.connect(self.message)
        else:
            widget = ImageViewer(path)
        return self.add(key, widget, path.name, file_visual(path), str(path))

    def _sync_render_mode(self, rendered: bool) -> None:
        """A click on Texto / Renderizado is the choice of the program: the other open text tabs
        follow it (the clicked one has written the setting already)."""
        for _key, widget in self.items():
            if isinstance(widget, TextViewer) and widget is not self.sender():
                widget.set_rendered(rendered, remember=False)

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
        return self.add(
            key,
            view,
            _("Resumo · {name}").format(name=path.name),
            ("summarize", "accent"),
            str(path),
        )

    def open_output(self, path: Path, line: int = 0) -> None:
        """The output in the text viewer, at ``line`` when given."""
        viewer = self.open_file(path, "text")
        if line and isinstance(viewer, TextViewer):
            viewer.go_to_line(line)

    def compare_with(self, path: Path) -> None:
        """ "Comparar com…": ask for the other input, which must look like one too."""
        chosen, _filter = QFileDialog.getOpenFileName(
            self, _("Comparar com…"), str(path.parent), INPUT_FILTER
        )
        if not chosen:
            return
        other = Path(chosen)
        if not looks_like_input(other):
            QMessageBox.warning(
                self,
                _("Comparar inputs"),
                _("{name} não parece um input do Quantum ESPRESSO.").format(name=other.name),
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
        add_action(menu, _("Fechar") + "\tCtrl+W", lambda: self.close_tab(index))
        add_action(menu, _("Fechar outras"), lambda: self.close_others(index), enabled=last > 0)
        add_action(
            menu, _("Fechar à direita"), lambda: self.close_right(index), enabled=index < last
        )
        add_action(menu, _("Fechar todas"), self.close_all)
        menu.addSeparator()
        add_action(menu, _("Copiar caminho"), lambda: copy_text(path))
        add_action(menu, _("Revelar no explorador"), lambda: self.reveal_requested.emit(Path(path)))
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
        """The one place ``current_changed`` is emitted: removing the last tab also gets here (the
        bar's ``currentChanged(-1)``), so the empty state is shown first and the news comes once."""
        if self.tabs.count() == 0:
            self.setCurrentWidget(self.empty)
        self.current_changed.emit(self.current())
