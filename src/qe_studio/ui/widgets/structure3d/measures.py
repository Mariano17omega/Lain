"""The "Medidas" section of the structure panel (spec 44 R2): "Distância" (two atoms) and "Ângulos" (three,
the vertex is the second) measured from clicks on the view, one row per measure in its table.

The two mode buttons are exclusive and may both be off (then a click only shows the atom). The atoms of
the measure under way, of the one just made and of a selected row are numbered on the view
(``StructureCanvas.set_marks``); nothing here moves the camera. "Limpar" empties both tables, "Apagar"
removes the last measure made (spec 46 R4) and Delete the selected rows. The measures belong to the
window: nothing is saved.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from ....core.structure3d.measurements import (
    Measurement,
    MeasureMode,
    Measurer,
    row_text,
    to_tsv,
)
from ....core.structure3d.model import AtomRef, atom_name
from ....i18n import _
from ...theme.scale import scaled
from ..common import set_variant
from ..param_widgets import Section
from .canvas import StructureCanvas

MODES: tuple[MeasureMode, ...] = ("distancia", "angulo")
BUTTONS = {"distancia": _("Distância"), "angulo": _("Ângulos")}
TIPS = {
    "distancia": _("Medir a distância entre dois átomos"),
    "angulo": _("Medir o ângulo de três átomos (vértice no segundo)"),
}
CAPTIONS = {"distancia": _("Distâncias"), "angulo": _("Ângulos")}
VALUE_HEADERS = {"distancia": _("Distância"), "angulo": _("Ângulo")}
HINTS = {
    None: _("Escolha Distância ou Ângulos para medir."),
    "distancia": _("Clique em dois átomos."),
    "angulo": _("Clique em três átomos; o segundo é o vértice."),
}
COPIED = _("Medidas copiadas")
MAX_ROWS = 8  # rows shown before the table scrolls
ROW_PX = 22  # a row at scale 1


class MeasureTable(QTableWidget):
    """The measures of one kind: "Átomos" and the value; the newest row last."""

    delete_requested = pyqtSignal()

    def __init__(self, value_header: str, parent: QWidget | None = None):
        super().__init__(0, 2, parent)
        self.setObjectName("structureMeasures")
        self.setHorizontalHeaderLabels([_("Átomos"), value_header])
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.hide()
            vertical.setDefaultSectionSize(scaled(ROW_PX))
        horizontal = self.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            horizontal.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.items: list[Measurement] = []

    def texts(self) -> list[tuple[str, str]]:
        """The rows as shown (tests read the table through it)."""
        return [(self._text(row, 0), self._text(row, 1)) for row in range(self.rowCount())]

    def _text(self, row: int, column: int) -> str:
        item = self.item(row, column)
        return item.text() if item is not None else ""

    def add(self, measurement: Measurement, atoms: str, value: str) -> None:
        row = self.rowCount()
        self.insertRow(row)
        for column, text in enumerate((atoms, value)):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, column, item)
        self.items.append(measurement)
        self._fit_height()
        self.selectRow(row)
        self.scrollToBottom()

    def selected_rows(self) -> list[int]:
        model = self.selectionModel()
        rows = {index.row() for index in model.selectedRows()} if model is not None else set()
        return sorted(rows)

    def remove(self, rows: list[int]) -> None:
        for row in sorted(rows, reverse=True):
            self.removeRow(row)
            del self.items[row]
        self._fit_height()

    def clear_rows(self) -> None:
        self.setRowCount(0)
        self.items.clear()
        self._fit_height()

    def _fit_height(self) -> None:
        header = self.horizontalHeader()
        height = (header.sizeHint().height() if header is not None else 0) + 2 * self.frameWidth()
        height += sum(self.rowHeight(row) for row in range(min(self.rowCount(), MAX_ROWS)))
        self.setFixedHeight(height)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802 (Qt naming)
        if event is not None and event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MeasuresSection(QObject):
    """Fills ``section`` and measures what the user clicks on ``canvas``."""

    message = pyqtSignal(str)  # for the window's status bar

    def __init__(self, section: Section, canvas: StructureCanvas):
        super().__init__(section)
        self.canvas, self.structure = canvas, canvas.structure
        self.measurer = Measurer(canvas.structure)
        self.measurements: list[Measurement] = []  # every measure, in the order made

        modes = QWidget()
        row = QHBoxLayout(modes)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.buttons: dict[str, QToolButton] = {}
        for mode in MODES:
            button = set_variant(QToolButton(), "toggle")
            button.setText(BUTTONS[mode])
            button.setToolTip(TIPS[mode])
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, m=mode: self._button_clicked(m))
            self.buttons[mode] = button
            row.addWidget(button)
        row.addStretch(1)
        section.add_full(modes)
        self.hint = set_variant(QLabel(), "meta")
        self.hint.setWordWrap(True)
        section.add_full(self.hint)

        self.captions: dict[str, QLabel] = {}
        self.tables: dict[str, MeasureTable] = {}
        for mode in MODES:
            caption = set_variant(QLabel(CAPTIONS[mode]), "fieldLabel")
            table = MeasureTable(VALUE_HEADERS[mode])
            table.itemSelectionChanged.connect(lambda m=mode: self._selection_changed(m))
            table.delete_requested.connect(lambda m=mode: self.delete_selected(m))
            section.add_full(caption)
            section.add_full(table)
            self.captions[mode], self.tables[mode] = caption, table

        actions = QWidget()
        line = QHBoxLayout(actions)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.copy_button = QPushButton(_("Copiar"))
        self.copy_button.setToolTip(_("Copiar as medidas como texto (cola numa planilha)"))
        self.copy_button.clicked.connect(self.copy)
        self.clear_button = QPushButton(_("Limpar"))
        self.clear_button.setToolTip(_("Apagar todas as medidas"))
        self.clear_button.clicked.connect(self.clear)
        self.delete_button = QPushButton(_("Apagar"))
        self.delete_button.setToolTip(_("Apagar a última medida"))
        self.delete_button.clicked.connect(self.delete_last)
        line.addWidget(self.copy_button)
        line.addWidget(self.clear_button)
        line.addWidget(self.delete_button)
        line.addStretch(1)
        section.add_full(actions)

        canvas.atom_clicked.connect(self._atom_clicked)
        canvas.escape_pressed.connect(self.clear_pending)
        self._refresh()

    # -- mode ----------------------------------------------------------------------------------------
    @property
    def mode(self) -> MeasureMode | None:
        return self.measurer.mode

    def set_mode(self, mode: MeasureMode | None) -> None:
        """Measure ``mode`` (None: nothing); the atoms of a measure under way are dropped."""
        self.measurer.set_mode(mode)
        for value, button in self.buttons.items():
            button.setChecked(value == mode)
        self.canvas.set_marks(())
        self._refresh()

    def _button_clicked(self, mode: str) -> None:
        """Turning a button on turns the other off; clicking the one that is on turns it off."""
        self.set_mode(next((m for m in MODES if m == mode and self.buttons[m].isChecked()), None))

    # -- clicks ----------------------------------------------------------------------------------------
    def _atom_clicked(self, ref: AtomRef | None) -> None:
        if self.measurer.mode is None:
            return
        if ref is None:  # empty space
            self.clear_pending()
            return
        measurement = self.measurer.click(ref)
        if measurement is None:
            self.canvas.set_marks(self.measurer.pending)
        else:
            self.add(measurement)
        self._refresh()

    def clear_pending(self) -> None:
        """Drop the atoms of the measure under way (empty space, Esc); the tables stay."""
        self.measurer.clear_pending()
        self.canvas.set_marks(())
        self._refresh()

    # -- rows ----------------------------------------------------------------------------------------
    def add(self, measurement: Measurement) -> None:
        """A new row at the end of its table, selected: its atoms stay numbered until the next click."""
        self.measurements.append(measurement)
        atoms, value = row_text(self.structure, measurement)
        for mode, table in self.tables.items():
            if mode != measurement.kind:
                table.clearSelection()
        self.tables[measurement.kind].add(measurement, atoms, value)
        self.canvas.set_marks(measurement.refs)
        self._refresh()

    def _selection_changed(self, mode: str) -> None:
        table = self.tables[mode]
        rows = table.selected_rows()
        if not rows:
            return
        for other, other_table in self.tables.items():
            if other != mode:
                other_table.blockSignals(True)
                other_table.clearSelection()
                other_table.blockSignals(False)
        self.canvas.set_marks(table.items[rows[-1]].refs)

    def delete_selected(self, mode: str) -> None:
        table = self.tables[mode]
        rows = table.selected_rows()
        if not rows:
            return
        gone = {id(table.items[row]) for row in rows}
        self.measurements = [m for m in self.measurements if id(m) not in gone]
        table.blockSignals(True)
        table.remove(rows)
        table.clearSelection()
        table.blockSignals(False)
        self.canvas.set_marks(self.measurer.pending)
        self._refresh()

    def delete_last(self) -> None:
        """Remove the last measure made, of either kind (spec 46 R4). The atoms of a measure under way
        stay pending; a row selected in a table does not matter (it is the last *made*, not the
        selected one)."""
        if not self.measurements:
            return
        last = self.measurements.pop()
        table = self.tables[last.kind]
        table.blockSignals(True)
        table.remove([table.rowCount() - 1])  # the rows of a table follow the order made
        table.blockSignals(False)
        self.canvas.set_marks(self.measurer.pending)
        self._refresh()

    def clear(self) -> None:
        """Empty both tables and the measure under way."""
        self.measurements = []
        for table in self.tables.values():
            table.blockSignals(True)
            table.clear_rows()
            table.blockSignals(False)
        self.measurer.clear_pending()
        self.canvas.set_marks(())
        self._refresh()

    def copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None and self.measurements:
            clipboard.setText(to_tsv(self.structure, self.measurements))
            self.message.emit(COPIED)

    # -- state ---------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        pending = self.measurer.pending
        if pending:
            names = " → ".join(atom_name(self.structure, ref) for ref in pending)
            self.hint.setText(_("Selecionados: {names}").format(names=names))
        else:
            self.hint.setText(HINTS[self.measurer.mode])
        for mode, table in self.tables.items():
            has = table.rowCount() > 0
            table.setVisible(has)
            self.captions[mode].setVisible(has)
        for button in (self.copy_button, self.clear_button, self.delete_button):
            button.setEnabled(bool(self.measurements))
