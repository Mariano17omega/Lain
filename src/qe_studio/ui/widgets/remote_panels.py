"""The cluster mode's panels (spec 65 R4): the cluster's folders, in the left panel's place of the
explorer, and the files of one of them, in the file panel's place of the grid. Both on the red
``remote_panel`` background (``styles/remote/remote.qss``); their metadata in ``text_meta``.

They show what the controller (``ui/remote_controller.py``) hands them and say what the user does;
nothing here lists or reads anything. No badges nor file states: those need the content.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from PyQt6.QtCore import QEvent, QItemSelectionModel, QModelIndex, QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ...core.remote.listing import RemoteEntry
from ...i18n import _
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, selection_of, viewport_of
from .elided_label import ElidedLabel
from .remote_model import RemoteFileModel, RemotePath, RemoteTreeModel
from .spinner import CircularProgress

SPINNER_PX = 32


def _styled(widget: QWidget, name: str) -> None:
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


class RemoteTreePanel(QWidget):
    """The folders of the cluster below the top of the view, listed as they are opened."""

    folder_selected = pyqtSignal(str)  # a click (or the keys) on a folder
    refresh_requested = pyqtSignal()  # "Atualizar"
    menu_requested = pyqtSignal(list, QPoint)  # [RemotePath], global position

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        _styled(self, "remoteTreePanel")
        self._quiet = False  # the current row is moved by the controller, not by the user
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = PanelHeader(theme, _("Cluster"), "cloud_done")
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # the red band
        self.refresh_button = self.header.add_button(
            IconButton(theme, "refresh", _("Atualizar (F5)"))
        )
        layout.addWidget(self.header)
        self.model = RemoteTreeModel(theme, self)
        self.tree = QTreeView()
        self.tree.setObjectName("remoteTree")
        self.tree.setAccessibleName(_("Pastas do cluster"))
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.tree, 1)
        selection_of(self.tree).currentChanged.connect(self._on_current)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.refresh_button.clicked.connect(self.refresh_requested)
        theme.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        viewport_of(self.tree).update()  # the folder icons are the theme's

    def reset(self, top: str, account: str) -> None:
        """An empty tree under ``top``, ``usuario@host`` in the header."""
        self.header.count.setText(account)
        self._quiet = True
        try:
            self.model.reset(top)
        finally:
            self._quiet = False

    def set_subfolders(self, remote_dir: str, names: list[str]) -> None:
        """A listing of ``remote_dir``: its rows, without the selection telling anyone."""
        self._quiet = True
        try:
            self.model.set_subfolders(remote_dir, names)
        finally:
            self._quiet = False

    def reveal(self, remote_dir: str) -> None:
        """Select ``remote_dir`` when the tree has its row (its parents were listed), with them
        open; else nothing is selected. ``folder_selected`` is not emitted."""
        index = self.model.index_for(remote_dir)
        self._quiet = True
        try:
            if index.isValid():
                parent = index.parent()
                while parent.isValid():
                    self.tree.expand(parent)
                    parent = parent.parent()
                self.tree.setCurrentIndex(index)
                self.tree.scrollTo(index)
            else:
                self.tree.clearSelection()
                selection_of(self.tree).setCurrentIndex(
                    QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate
                )
        finally:
            self._quiet = False

    def current_dir(self) -> str | None:
        index = self.tree.currentIndex()
        return self.model.dir_of(index) if index.isValid() else None

    def _on_current(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not self._quiet and current.isValid():
            self.folder_selected.emit(self.model.dir_of(current))

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.tree.indexAt(pos)
        if index.isValid():
            item = RemotePath(self.model.dir_of(index), True)
            self.menu_requested.emit([item], viewport_of(self.tree).mapToGlobal(pos))


class RemoteFilePanel(QWidget):
    """The entries of one folder of the cluster as a list: name, size, date. A spinner over it while
    the folder has no answer yet; the reason and "Tentar de novo" when the listing failed."""

    folder_activated = pyqtSignal(str)  # Enter or a double click on a folder (or "..")
    up_requested = pyqtSignal()  # Backspace, Alt+↑
    retry_requested = pyqtSignal()  # "Tentar de novo"
    menu_requested = pyqtSignal(list, QPoint)  # [RemotePath] (the selection), global position

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        _styled(self, "remoteFilePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = PanelHeader(theme, _("Arquivos do cluster"), "cloud_done")
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(self.header)
        self.path = ElidedLabel()
        self.path.setObjectName("remotePath")
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        self.model = RemoteFileModel(theme, self)
        self.view = QTreeView()
        self.view.setObjectName("remoteFileList")
        self.view.setAccessibleName(_("Arquivos do cluster"))
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setUniformRowHeights(True)
        self.view.setAllColumnsShowFocus(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.view.header()
        assert header is not None
        header.setStretchLastSection(False)
        header.setSectionsClickable(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.pages.addWidget(self.view)

        self.failure = QWidget()
        _styled(self.failure, "remoteFailure")
        failure = QVBoxLayout(self.failure)
        self.message = QLabel()
        self.message.setObjectName("remoteMessage")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.retry_button = QPushButton(_("Tentar de novo"))
        failure.addStretch(1)
        failure.addWidget(self.message)
        failure.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignHCenter)
        failure.addStretch(1)
        self.pages.addWidget(self.failure)

        self.spinner = CircularProgress(theme, SPINNER_PX, viewport_of(self.view))
        self.spinner.hide()
        viewport_of(self.view).installEventFilter(self)

        self.view.activated.connect(self._on_activated)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        self.retry_button.clicked.connect(self.retry_requested)
        for keys in ("Backspace", "Alt+Up"):
            shortcut = QShortcut(QKeySequence(keys), self.view)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.up_requested)
        theme.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        viewport_of(self.view).update()

    # -- what the controller says ----------------------------------------------------------------
    def set_folder(self, remote_dir: str, up: str | None) -> None:
        """Show ``remote_dir``, empty until its entries come; ``up``: the folder ``..`` opens."""
        self.path.set_full_text(remote_dir)
        self.header.count.setText("")
        self.model.set_rows(remote_dir, [], up)
        self.pages.setCurrentWidget(self.view)

    @property
    def loading(self) -> bool:
        return not self.spinner.isHidden()

    def set_loading(self, loading: bool) -> None:
        """The spinner over the list: the folder shown has no answer yet."""
        self.spinner.setVisible(loading)
        if loading:
            self._place_spinner()
            self.spinner.raise_()

    def show_entries(self, entries: list[RemoteEntry]) -> None:
        """The entries of the folder shown; the items selected before stay selected."""
        model = self.model
        selected = [PurePosixPath(path.path).name for path in self.selected_paths()]
        current = model.path_of(self.view.currentIndex())
        model.set_rows(model.folder, entries, model.up)
        selection = selection_of(self.view)
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for name in selected:
            row = model.row_of(name)
            if row is not None:
                selection.select(model.index(row, 0), flags)
        if current is not None:
            row = model.row_of(PurePosixPath(current.path).name)
            if row is not None:
                selection.setCurrentIndex(
                    model.index(row, 0), QItemSelectionModel.SelectionFlag.NoUpdate
                )
        self.header.count.setText(f"({len(entries)})")
        self.pages.setCurrentWidget(self.view)
        self.set_loading(False)

    def show_failure(self, message: str) -> None:
        self.message.setText(message)
        self.header.count.setText("")
        self.pages.setCurrentWidget(self.failure)
        self.set_loading(False)

    @property
    def failed(self) -> bool:
        return self.pages.currentWidget() is self.failure

    def selected_paths(self) -> list[RemotePath]:
        """The selected items in view order; ``..`` never counts."""
        model = self.model
        rows = sorted({index.row() for index in selection_of(self.view).selectedIndexes()})
        indexes = [model.index(row, 0) for row in rows]
        paths = [model.path_of(index) for index in indexes if not model.is_up(index)]
        return [path for path in paths if path is not None]

    # -- what the user does ----------------------------------------------------------------------
    def _on_activated(self, index: QModelIndex) -> None:
        path = self.model.path_of(index)
        if path is not None and path.is_dir:  # a file: only read (spec 66 plots)
            self.folder_activated.emit(path.path)

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid() or self.model.is_up(index):
            return
        selection = selection_of(self.view)
        if not selection.isSelected(index):  # outside the selection: it becomes the selection
            selection.setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self.menu_requested.emit(self.selected_paths(), viewport_of(self.view).mapToGlobal(pos))

    # -- the spinner -----------------------------------------------------------------------------
    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Resize:
            self._place_spinner()
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.path.set_budget(self.width())

    def _place_spinner(self) -> None:
        area = viewport_of(self.view).rect()
        self.spinner.move(
            area.center().x() - SPINNER_PX // 2, max(0, area.height() // 3 - SPINNER_PX // 2)
        )
