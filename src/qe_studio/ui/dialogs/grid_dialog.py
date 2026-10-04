"""The "Grids" window (spec 23 R3): define a grid of the open plots, save, reopen and generate it.

Not modal: plots can still be opened while it is up (their list is read again when the window gets
the focus). "Gerar" saves the grid and asks for its tab (``generate_requested``), then closes.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.grid_store import GridStore
from ...core.plotting.grid import MAX_SIZE, GridCell, GridSpec, PlotRef
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from ..widgets.grid_preview import GridPreview
from .grid_cells import CellsTable, PlotChoice


def default_name(taken: list[str]) -> str:
    """``1``, ``2``…: the first number no saved grid is called."""
    number = 1
    while str(number) in taken:
        number += 1
    return str(number)


class GridDialog(QDialog):
    generate_requested = pyqtSignal(object)  # GridSpec

    def __init__(
        self,
        theme: ThemeManager,
        store: GridStore,
        choices: Callable[[], list[PlotChoice]],
        describe: Callable[[PlotRef], PlotChoice],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Grids")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(760, 580)
        self.store, self._choices = store, choices
        self._saved_as: str | None = None  # the saved grid this one is (replaced without asking)

        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel("Grade de gráficos"), "dialogTitle"))
        note = QLabel(
            "Cada célula mostra um gráfico aberto, com os ajustes que ele tem agora. "
            "A grade é salva por nome e pode ser gerada de novo depois."
        )
        note.setWordWrap(True)
        layout.addWidget(set_variant(note, "dialogText"))
        layout.addLayout(self._top_row())

        self.table = CellsTable(describe)
        layout.addWidget(self.table, 1)
        cell_buttons = QHBoxLayout()
        self.add_button = QPushButton("Adicionar célula")
        self.remove_button = QPushButton("Remover")
        self.preview_button = QPushButton("Pré-visualizar")
        self.preview_button.setCheckable(True)
        for button in (self.add_button, self.remove_button):
            cell_buttons.addWidget(button)
        cell_buttons.addStretch(1)
        cell_buttons.addWidget(self.preview_button)
        layout.addLayout(cell_buttons)
        self.problem = set_variant(QLabel(), "warning")
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        self.info = set_variant(QLabel(), "dialogText")
        layout.addWidget(self.info)
        self.preview = GridPreview(theme)
        self.preview.hide()
        layout.addWidget(self.preview)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.close_button = QPushButton("Fechar")
        self.generate_button = set_variant(QPushButton("Gerar"), "primary")
        self.generate_button.setDefault(True)
        bottom.addWidget(self.close_button)
        bottom.addWidget(self.generate_button)
        layout.addLayout(bottom)

        self.rows.valueChanged.connect(self._on_size)
        self.cols.valueChanged.connect(self._on_size)
        self.name.textChanged.connect(self._validate)
        self.table.changed.connect(self._validate)
        self.add_button.clicked.connect(lambda: self.table.add_cell())
        self.remove_button.clicked.connect(self.table.remove_selected)
        self.preview_button.toggled.connect(self.preview.setVisible)
        self.save_button.clicked.connect(self.save)
        self.delete_button.clicked.connect(self.delete)
        self.close_button.clicked.connect(self.close)
        self.generate_button.clicked.connect(self.generate)
        self._start()

    def _top_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("nome da grade")
        self.rows, self.cols = QSpinBox(), QSpinBox()
        for spin in (self.rows, self.cols):
            spin.setRange(1, MAX_SIZE)
        self.open_button = QPushButton("Abrir…")
        self.open_menu = QMenu(self.open_button)
        self.open_menu.aboutToShow.connect(self._fill_open_menu)
        self.open_button.setMenu(self.open_menu)
        self.save_button = QPushButton("Salvar")
        self.delete_button = set_variant(QPushButton("Excluir"), "danger")
        for label, widget in (("Nome", self.name), ("Linhas", self.rows), ("Colunas", self.cols)):
            row.addWidget(set_variant(QLabel(label), "fieldLabel"))
            row.addWidget(widget, 1 if widget is self.name else 0)
        for button in (self.open_button, self.save_button, self.delete_button):
            row.addWidget(button)
        return row

    def _start(self) -> None:
        """A new grid: one row of the open plots (up to ``MAX_SIZE``), one cell each."""
        choices = self._choices()[:MAX_SIZE]
        self.name.setText(default_name(self.store.names()))
        self.cols.setValue(max(len(choices), 1))
        self.rows.setValue(1)
        self.table.set_choices(self._choices())
        self.table.set_limits(1, self.cols.value())
        self.table.set_cells([GridCell(0, i, c.ref) for i, c in enumerate(choices)])

    # -- the grid --------------------------------------------------------------------------------
    def spec(self) -> GridSpec:
        return GridSpec(
            self.name.text().strip(), self.rows.value(), self.cols.value(), self.table.cells()
        )

    def open_grid(self, name: str) -> bool:
        """Show the saved grid ``name``; False when it cannot be read."""
        spec = self.store.get(name)
        if spec is None:
            self.info.setText(f"Não foi possível abrir a grade “{name}”.")
            return False
        self.name.setText(spec.name)
        for spin, value in ((self.rows, spec.rows), (self.cols, spec.cols)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.table.set_limits(spec.rows, spec.cols)
        self.table.set_cells(spec.cells)
        self._saved_as = spec.name
        self.info.setText(f"Grade “{spec.name}” aberta.")
        return True

    def save(self) -> bool:
        """Save the grid under its name (asking before replacing another one); whether it was."""
        spec = self.spec()
        if spec.validate() or not self._may_replace(spec.name):
            return False
        self.store.save(spec)
        self._saved_as = spec.name
        self.info.setText(f"Grade “{spec.name}” salva.")
        return True

    def delete(self) -> None:
        name = self.name.text().strip()
        if name not in self.store.names():
            self.info.setText(f"Não há grade salva com o nome “{name}”.")
            return
        answer = QMessageBox.question(self, "Excluir grade", f"Excluir a grade salva “{name}”?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(name)
        self._saved_as = None
        self.info.setText(f"Grade “{name}” excluída.")

    def generate(self) -> None:
        """Save, ask for the grid's tab and close."""
        if not self.save():
            return
        self.generate_requested.emit(self.spec())
        self.close()

    def _may_replace(self, name: str) -> bool:
        if name == self._saved_as or name not in self.store.names():
            return True
        answer = QMessageBox.question(
            self, "Substituir grade", f"Já existe uma grade “{name}”. Substituir?"
        )
        return answer == QMessageBox.StandardButton.Yes

    # -- reactions -------------------------------------------------------------------------------
    def _on_size(self) -> None:
        self.table.set_limits(self.rows.value(), self.cols.value())
        self._validate()

    def _validate(self) -> None:
        spec = self.spec()
        errors = spec.validate()
        self.problem.setText("\n".join(errors))
        self.problem.setVisible(bool(errors))
        self.generate_button.setEnabled(not errors)
        self.save_button.setEnabled(not errors)
        labels = []
        for number, cell in enumerate(spec.cells, 1):
            combo = self.table.combo(number - 1)
            text = cell.title.strip() or combo.currentText() or f"Célula {number}"
            labels.append((cell.row, cell.col, text))
        self.preview.show_grid(spec.rows, spec.cols, labels)

    def _fill_open_menu(self) -> None:
        self.open_menu.clear()
        names = self.store.names()
        if not names:
            action = self.open_menu.addAction("Nenhuma grade salva")
            if action is not None:
                action.setEnabled(False)
        for name in names:
            action = self.open_menu.addAction(name)
            if action is not None:
                action.triggered.connect(lambda _c=False, n=name: self.open_grid(n))

    def event(self, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.WindowActivate:
            self.table.set_choices(self._choices())  # plots opened or closed meanwhile
        return super().event(event)
