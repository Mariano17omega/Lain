"""Tab that compares two QE inputs: by parameter, or side by side line by line (spec 11 R6).

All the comparing is ``core/qe/input_diff``, done in a worker; this widget lays the result out. Both
files are read whole (inputs over the viewer's lint limit are refused) and a write error in either
one is no obstacle.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollBar,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.qe.input_diff import Comparison, ParamDiff, TextRow, TooBigError, compare_files
from ...core.tasks import TaskHandle, run_task
from ..theme.manager import ThemeManager
from .code_view import CodeView
from .highlighters import InputHighlighter

log = logging.getLogger(__name__)
PARAMS, TEXT, MESSAGE = 0, 1, 2  # pages of the stack
STATUS = {"only_a": "só em A", "only_b": "só em B", "different": "diferente"}
STATUS_TOKEN = {"only_a": "diff_del_bg", "only_b": "diff_add_bg", "different": "diff_change_bg"}
# Row tag → background token, per side. Padding rows (the other side of an add or a delete) stay bare.
ROW_TOKENS_A = {"del": "diff_del_bg", "change": "diff_change_bg"}
ROW_TOKENS_B = {"add": "diff_add_bg", "change": "diff_change_bg"}
NO_DIFFERENCE = "Os inputs são equivalentes: nenhum parâmetro nem card difere."


def diff_key(a: Path, b: Path) -> str:
    """Key of the workspace tab that compares ``a`` with ``b``."""
    return f"diff:{a}|{b}"


def diff_title(a: Path, b: Path) -> str:
    """ "Diff · a ↔ b"; the folders too when the two files have the same name."""
    left, right = (
        (a.name, b.name)
        if a.name != b.name
        else (f"{a.parent.name}/{a.name}", f"{b.parent.name}/{b.name}")
    )
    return f"Diff · {left} ↔ {right}"


def _bars(pane: CodeView) -> tuple[QScrollBar, QScrollBar]:
    vertical, horizontal = pane.verticalScrollBar(), pane.horizontalScrollBar()
    assert vertical is not None and horizontal is not None
    return vertical, horizontal


def _tool(text: str, tip: str, checkable: bool = False) -> QToolButton:
    button = QToolButton()
    button.setProperty("variant", "viewerTool")
    button.setText(text)
    button.setToolTip(tip)
    button.setCheckable(checkable)
    return button


class DiffView(QWidget):
    """ "Diff · a ↔ b": the table of parameters that differ, or the two texts side by side."""

    loaded = pyqtSignal()  # the comparison finished (or failed)

    def __init__(self, a: Path, b: Path, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.a, self.b = a, b
        self.theme = theme
        self.comparison: Comparison | None = None
        self._mode = PARAMS
        self._task: TaskHandle | None = None  # cancelled if the tab closes first
        self.setObjectName("diffView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.bar = QWidget()
        self.bar.setObjectName("diffBar")
        self.bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self.bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        self.label_a = self._file_label("A", a)
        self.label_b = self._file_label("B", b)
        self.params_button = _tool("Parâmetros", "Só o que difere, parâmetro por parâmetro", True)
        self.text_button = _tool("Texto", "Os dois arquivos lado a lado", True)
        self.params_button.setChecked(True)
        modes = QButtonGroup(self)
        modes.setExclusive(True)
        modes.addButton(self.params_button)
        modes.addButton(self.text_button)
        self.ignore_box = QCheckBox("Ignorar espaços e comentários")
        self.ignore_box.hide()
        for widget in (self.label_a, self.label_b):
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self.ignore_box)
        row.addWidget(self.params_button)
        row.addWidget(self.text_button)
        layout.addWidget(self.bar)

        self.tree = QTreeWidget()
        self.tree.setObjectName("diffTree")
        self.tree.setHeaderLabels(["Namelist", "Parâmetro", "A", "B", "Estado"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.tree.header()
        if header is not None:
            header.setStretchLastSection(False)
            for column in range(5):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.pane_a, self.pane_b = CodeView(theme), CodeView(theme)
        self.panes = QSplitter(Qt.Orientation.Horizontal)
        for pane in (self.pane_a, self.pane_b):
            pane.setPlaceholderText("")
            self.panes.addWidget(pane)
        self._highlighters = [
            InputHighlighter(pane.text_document(), theme) for pane in (self.pane_a, self.pane_b)
        ]
        self.message = QLabel("Comparando…")
        self.message.setObjectName("diffMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.stack = QStackedWidget()
        for page in (self.tree, self.panes, self.message):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.params_button.clicked.connect(self.show_params)
        self.text_button.clicked.connect(self.show_text)
        self.ignore_box.toggled.connect(self._fill_text)
        self.tree.itemClicked.connect(self._toggle_item)
        (vertical_a, horizontal_a), (vertical_b, horizontal_b) = (
            _bars(self.pane_a),
            _bars(self.pane_b),
        )
        vertical_a.valueChanged.connect(self._follow_a_vertically)
        vertical_b.valueChanged.connect(self._follow_b_vertically)
        horizontal_a.valueChanged.connect(self._follow_a_horizontally)
        horizontal_b.valueChanged.connect(self._follow_b_horizontally)
        theme.theme_changed.connect(self._paint_tree)
        self._show_page()
        self._start()

    @property
    def paths(self) -> tuple[Path, Path]:
        """Both files: renaming either one closes the tab."""
        return self.a, self.b

    @property
    def mode(self) -> int:
        return self._mode

    @staticmethod
    def _file_label(side: str, path: Path) -> QLabel:
        label = QLabel(f"{side}  {path.name}")
        label.setObjectName("diffFile")
        label.setToolTip(str(path))
        return label

    # -- loading -----------------------------------------------------------------------------
    def _start(self) -> None:
        self._task = run_task(
            compare_files, self.a, self.b, on_done=self._on_done, on_error=self._on_failed
        )

    def cancel_load(self) -> None:
        """Window close: the read in progress is not wanted any more."""
        if self._task is not None:
            self._task.cancel()

    def _on_done(self, result: Comparison) -> None:
        self.comparison = result
        self._fill_tree(result.params)
        self._fill_text()
        self._show_page()
        self.loaded.emit()

    def _on_failed(self, error: Exception) -> None:
        if not isinstance(error, OSError | TooBigError):
            log.error("comparing %s with %s failed", self.a, self.b, exc_info=error)
        self.message.setText(f"Não foi possível comparar: {error}")
        self._show_page()
        self.loaded.emit()

    # -- modes -------------------------------------------------------------------------------
    def show_params(self) -> None:
        self._mode = PARAMS
        self.params_button.setChecked(True)
        self._show_page()

    def show_text(self) -> None:
        self._mode = TEXT
        self.text_button.setChecked(True)
        self._show_page()

    def _show_page(self) -> None:
        self.ignore_box.setVisible(self._mode == TEXT)
        result = self.comparison
        if result is None:
            self.stack.setCurrentIndex(MESSAGE)
        elif self._mode == TEXT:
            self.stack.setCurrentIndex(TEXT)
        elif result.params.identical:
            self.message.setText(NO_DIFFERENCE)
            self.stack.setCurrentIndex(MESSAGE)
        else:
            self.stack.setCurrentIndex(PARAMS)

    # -- parameters --------------------------------------------------------------------------
    def _fill_tree(self, diff: ParamDiff) -> None:
        self.tree.clear()
        for change in diff.params:
            item = QTreeWidgetItem(
                [
                    change.namelist,
                    change.key,
                    "—" if change.a is None else change.a,
                    "—" if change.b is None else change.b,
                    STATUS[change.status],
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, change.status)
            self.tree.addTopLevelItem(item)
        for card in diff.cards:
            item = QTreeWidgetItem(["card", card.summary, "", "", STATUS[card.status]])
            item.setData(0, Qt.ItemDataRole.UserRole, card.status)
            for left, right in card.detail:
                item.addChild(QTreeWidgetItem(["", "linha", left or "—", right or "—", ""]))
            self.tree.addTopLevelItem(item)
        self._paint_tree()

    def _paint_tree(self, _name: str = "") -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is None:
                continue
            brush = QBrush(self.theme.color(STATUS_TOKEN[item.data(0, Qt.ItemDataRole.UserRole)]))
            for column in range(self.tree.columnCount()):
                item.setBackground(column, brush)

    def _toggle_item(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    # -- text --------------------------------------------------------------------------------
    def _fill_text(self, *_args) -> None:
        if self.comparison is None:
            return
        rows = self.comparison.rows[self.ignore_box.isChecked()]
        self._fill_pane(self.pane_a, rows, 0, ROW_TOKENS_A)
        self._fill_pane(self.pane_b, rows, 1, ROW_TOKENS_B)

    @staticmethod
    def _fill_pane(pane: CodeView, rows: list[TextRow], side: int, tokens: dict[str, str]) -> None:
        cells = [row.a if side == 0 else row.b for row in rows]
        pane.setPlainText("\n".join(cell[1] if cell else "" for cell in cells))
        pane.set_numbers([cell[0] if cell else None for cell in cells])
        pane.set_row_backgrounds(
            {i: tokens[row.tag] for i, row in enumerate(rows) if row.tag in tokens}
        )

    # The panes have the same number of rows, so their scroll bars share a scale.
    def _follow_a_vertically(self, value: int) -> None:
        _bars(self.pane_b)[0].setValue(value)

    def _follow_b_vertically(self, value: int) -> None:
        _bars(self.pane_a)[0].setValue(value)

    def _follow_a_horizontally(self, value: int) -> None:
        _bars(self.pane_b)[1].setValue(value)

    def _follow_b_horizontally(self, value: int) -> None:
        _bars(self.pane_a)[1].setValue(value)
