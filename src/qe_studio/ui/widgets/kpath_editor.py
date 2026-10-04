"""The band path of "Criar cálculo" (spec 26 R4.3): a table of high-symmetry points the user edits.

Rows are the points of ``K_POINTS crystal_b``: label, the three fractional coordinates and the
points to the next one. "Marcar quebra de segmento" makes the path jump from a point to the next
(``X|U``: weight 1). The suggestion (pymatgen, seconds to import) runs in a worker; on the tab's
first visit it fills only an empty table, while "Sugerir" replaces what is there.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.calc_create.kpath import DEFAULT_NPTS, KPath, KPathUnavailable, KPoint
from ...core.tasks import run_task
from ..busy import BusyTracker
from .common import set_variant

log = logging.getLogger(__name__)

COLUMNS = ("Rótulo", "k1", "k2", "k3", "Pontos")
LABEL, K1, K2, K3, NPTS = range(5)
VALUE = Qt.ItemDataRole.UserRole  # the number a cell holds (its text is how it is shown)
SUGGESTING = "Calculando caminho de alta simetria…"
BREAK_TEXT = "quebra"
BREAK_TIP = "O caminho salta deste ponto para o próximo (peso 1)"
END_TEXT = "—"


@dataclass(frozen=True)
class _Row:
    label: str
    frac: tuple[float, float, float]
    npts: int
    jump: bool = False  # the path breaks after this point


def _number_text(value: float) -> str:
    return f"{value + 0.0:.8g}"  # + 0.0: no "-0"


class KPathEditor(QWidget):
    changed = pyqtSignal(bool)  # the path changed; True when the user did it (not a suggestion)

    def __init__(
        self,
        suggest: Callable[[], KPath] | None = None,
        busy: BusyTracker | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._suggest, self._busy = suggest, busy
        self._busy_key = f"kpath:{id(self)}"
        self._filling = False
        self._asked = False  # the first visit asked for a suggestion already
        self._running = False
        self._notes: tuple[str, ...] = ()
        if busy is not None:
            self.destroyed.connect(partial(busy.end, self._busy_key))

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("kpathTable")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        points = self.table.horizontalHeaderItem(NPTS)
        if points is not None:
            points.setToolTip("Pontos até o próximo ponto do caminho")
        self.table.setMinimumHeight(
            260
        )  # a whole fcc path (about 12 points) without scrolling much
        vertical = self.table.verticalHeader()
        assert vertical is not None
        vertical.setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(self._update_buttons)

        self.add_button = QPushButton("Adicionar")
        self.remove_button = QPushButton("Remover")
        self.up_button = QPushButton("Subir")
        self.down_button = QPushButton("Descer")
        self.break_button = QPushButton("Marcar quebra de segmento")
        self.break_button.setToolTip(BREAK_TIP)
        self.suggest_button = QPushButton("Sugerir (pymatgen)")
        self.suggest_button.setToolTip(
            "Caminho de alta simetria da estrutura do SCF (Setyawan–Curtarolo); substitui a tabela"
        )
        self.add_button.clicked.connect(self.add_point)
        self.remove_button.clicked.connect(self.remove_point)
        self.up_button.clicked.connect(partial(self.move_point, -1))
        self.down_button.clicked.connect(partial(self.move_point, 1))
        self.break_button.clicked.connect(self.toggle_break)
        self.suggest_button.clicked.connect(self.request_suggestion)
        self.suggest_button.setVisible(suggest is not None)
        self.message = set_variant(QLabel(), "dialogWarning")
        self.message.setWordWrap(True)
        self.message.hide()

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        more = QHBoxLayout()
        more.setContentsMargins(0, 0, 0, 0)
        for button in (self.break_button, self.suggest_button):
            button.setAutoDefault(False)
            more.addWidget(button)
        more.addStretch(1)
        layout.addLayout(more)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message)
        self._update_buttons()

    # -- value --------------------------------------------------------------------------------
    def value(self) -> KPath:
        """The path as typed (no points: an empty path, which the type reports as too short)."""
        rows = self._rows()
        points = tuple(KPoint(row.label, row.frac, row.npts) for row in rows)
        breaks = frozenset(i for i, row in enumerate(rows) if row.jump)
        return KPath(points, breaks)

    def set_path(self, path: KPath) -> None:
        """Show ``path`` (a suggestion): not a user edit."""
        rows = [
            _Row(point.label, point.frac, max(int(point.npts), 1), i in path.breaks)
            for i, point in enumerate(path.points)
        ]
        self._set_rows(rows, 0 if rows else -1)
        self.changed.emit(False)

    @property
    def notes(self) -> tuple[str, ...]:
        """Why there is no suggestion, or what the suggestion warns about (the "Arquivos" tab)."""
        return self._notes

    # -- rows -----------------------------------------------------------------------------------
    def _rows(self) -> list[_Row]:
        rows = []
        for row in range(self.table.rowCount()):
            label = self.table.item(row, LABEL)
            values = [self._number(row, column) for column in (K1, K2, K3)]
            npts = self._number(row, NPTS)
            rows.append(
                _Row(
                    label.text().strip() if label is not None else "",
                    (values[0], values[1], values[2]),
                    max(int(npts), 1),
                    bool(label is not None and label.data(Qt.ItemDataRole.UserRole + 1)),
                )
            )
        return rows

    def _number(self, row: int, column: int) -> float:
        item = self.table.item(row, column)
        value = item.data(VALUE) if item is not None else None
        return float(value) if value is not None else 0.0

    def _set_rows(self, rows: list[_Row], current: int) -> None:
        self._filling = True
        try:
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                label = QTableWidgetItem(row.label)
                label.setData(Qt.ItemDataRole.UserRole + 1, row.jump)
                self.table.setItem(index, LABEL, label)
                for column, value in zip((K1, K2, K3), row.frac, strict=True):
                    item = QTableWidgetItem(_number_text(value))
                    item.setData(VALUE, float(value))
                    self.table.setItem(index, column, item)
                npts = QTableWidgetItem()
                npts.setData(VALUE, row.npts)
                self.table.setItem(index, NPTS, npts)
            self._show_npts()
        finally:
            self._filling = False
        if 0 <= current < len(rows):
            self.table.setCurrentCell(current, LABEL)
        self._update_buttons()

    def _show_npts(self) -> None:
        """The points cell says "quebra" at a jump and "—" at the end, where it does not count."""
        last = self.table.rowCount() - 1
        for row in range(self.table.rowCount()):
            item = self.table.item(row, NPTS)
            label = self.table.item(row, LABEL)
            if item is None or label is None:
                continue
            jump = bool(label.data(Qt.ItemDataRole.UserRole + 1))
            flags = item.flags()
            if row == last or jump:
                item.setText(END_TEXT if row == last else BREAK_TEXT)
                item.setToolTip("" if row == last else BREAK_TIP)
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEditable)
            else:
                item.setText(str(int(item.data(VALUE))))
                item.setToolTip("")
                item.setFlags(flags | Qt.ItemFlag.ItemIsEditable)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling:
            return
        column = item.column()
        if column != LABEL:
            self._filling = True
            try:
                self._take_number(item, column)
            finally:
                self._filling = False
        self._edited()

    def _take_number(self, item: QTableWidgetItem, column: int) -> None:
        """Keep a valid number (comma or dot); put the previous one back otherwise."""
        text = item.text().strip().replace(",", ".")
        previous = item.data(VALUE)
        try:
            number: float = float(text) if column != NPTS else int(text)
            if column == NPTS and number < 1:
                raise ValueError
        except ValueError:
            self._show_message(f"Valor inválido: {item.text().strip() or 'vazio'}")
            number = previous
        else:
            self._show_message("")
        item.setData(VALUE, number)
        item.setText(_number_text(number) if column != NPTS else str(int(number)))

    def _edited(self) -> None:
        self._update_buttons()
        self.changed.emit(True)

    def _mutate(self, change: Callable[[list[_Row], int], int]) -> None:
        """Apply ``change(rows, current) -> new current`` and show the result: a user edit."""
        rows = self._rows()
        current = change(rows, self.table.currentRow())
        self._set_rows(rows, current)
        self._edited()

    # -- buttons --------------------------------------------------------------------------------
    def add_point(self) -> None:
        def add(rows: list[_Row], current: int) -> int:
            at = current + 1 if 0 <= current < len(rows) else len(rows)
            rows.insert(at, _Row("", (0.0, 0.0, 0.0), DEFAULT_NPTS))
            return at

        self._mutate(add)

    def remove_point(self) -> None:
        def remove(rows: list[_Row], current: int) -> int:
            if not 0 <= current < len(rows):
                return current
            del rows[current]
            return min(current, len(rows) - 1)

        self._mutate(remove)

    def move_point(self, delta: int) -> None:
        def move(rows: list[_Row], current: int) -> int:
            target = current + delta
            if not (0 <= current < len(rows) and 0 <= target < len(rows)):
                return current
            rows[current], rows[target] = rows[target], rows[current]
            return target

        self._mutate(move)

    def toggle_break(self) -> None:
        def toggle(rows: list[_Row], current: int) -> int:
            if 0 <= current < len(rows) - 1:  # the last point has nothing after it
                rows[current] = replace(rows[current], jump=not rows[current].jump)
            return current

        self._mutate(toggle)

    def _update_buttons(self, *_args) -> None:
        count, current = self.table.rowCount(), self.table.currentRow()
        selected = 0 <= current < count
        self.remove_button.setEnabled(selected)
        self.up_button.setEnabled(selected and current > 0)
        self.down_button.setEnabled(selected and current < count - 1)
        self.break_button.setEnabled(selected and current < count - 1)
        self.suggest_button.setEnabled(not self._running)

    # -- suggestion -------------------------------------------------------------------------------
    def ensure_suggested(self) -> None:
        """The tab's first visit: a suggestion for an empty table."""
        if self._asked or self._suggest is None:
            return
        self._asked = True
        if self.table.rowCount() == 0:
            self._start(replace=False)

    def request_suggestion(self) -> None:
        """ "Sugerir (pymatgen)": the suggestion replaces the table."""
        self._asked = True
        self._start(replace=True)

    def _start(self, replace: bool) -> None:
        if self._suggest is None or self._running:
            return
        self._running = True
        self._update_buttons()
        self._show_message(SUGGESTING, warning=False)
        if self._busy is not None:
            self._busy.begin(self._busy_key, SUGGESTING)
        on_done = self._on_replace if replace else self._on_suggested
        run_task(self._suggest, on_done=on_done, on_error=self._on_failed)

    def _finish(self) -> None:
        self._running = False
        if self._busy is not None:
            self._busy.end(self._busy_key)
        self._update_buttons()

    def _on_suggested(self, path: KPath) -> None:
        self._finish()
        if self.table.rowCount():  # typed while pymatgen worked: keep it
            self._show_message("Sugestão pronta: use “Sugerir (pymatgen)” para substituir a tabela")
            return
        self._show_suggestion(path)

    def _on_replace(self, path: KPath) -> None:
        self._finish()
        self._show_suggestion(path)
        self.changed.emit(True)  # asked for: the user's own edit

    def _show_suggestion(self, path: KPath) -> None:
        self._notes = path.warnings
        self._show_message("\n".join(path.warnings))
        self.set_path(path)

    def _on_failed(self, exc: BaseException) -> None:
        self._finish()
        if isinstance(exc, KPathUnavailable):
            reason = str(exc)
        else:
            log.error("suggesting the band path failed", exc_info=exc)
            reason = f"erro inesperado: {exc}"
        self._notes = (f"Sem sugestão de caminho: {reason}",)
        self._show_message(self._notes[0])
        self.changed.emit(False)

    def _show_message(self, text: str, warning: bool = True) -> None:
        set_variant(self.message, "dialogWarning" if warning else "dialogText")
        style = self.message.style()
        if style is not None:
            style.unpolish(self.message)
            style.polish(self.message)
        self.message.setText(text)
        self.message.setVisible(bool(text))
