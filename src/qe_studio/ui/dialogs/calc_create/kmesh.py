"""The ``K_POINTS automatic`` mesh of "Criar cálculo" (spec 26 R4.4): n1 n2 n3 and the shifts."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QSpinBox, QWidget

from ....core.calc_create.kpath import KMesh
from ....core.calc_create.preview import mesh_summary
from .labels import message_label, show_message

MAX_N = 999


class KMeshEditor(QWidget):
    """Three counts (0 shows "–": all three empty is an empty field) and three shifts. The summary
    under them is a rough size: pw.x keeps only the points symmetry leaves."""

    changed = pyqtSignal()  # the user edited it

    def __init__(self, value: KMesh | None, default: KMesh | None, parent: QWidget | None = None):
        super().__init__(parent)
        self._default = default
        self.counts = []
        self.shifts = []
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        for index in range(3):
            count = QSpinBox()
            count.setRange(0, MAX_N)
            count.setSpecialValueText("–")
            count.setAccessibleName(f"n{index + 1}")
            count.setToolTip(f"n{index + 1}: pontos na direção do vetor recíproco b{index + 1}")
            shift = QCheckBox(f"s{index + 1}")
            shift.setToolTip(f"s{index + 1}: desloca a rede meio passo na direção b{index + 1}")
            grid.addWidget(count, 0, index)
            grid.addWidget(shift, 1, index)
            self.counts.append(count)
            self.shifts.append(shift)
        self.summary = message_label()
        grid.addWidget(self.summary, 2, 0, 1, 3)
        self.set_value(value)
        for count in self.counts:
            count.valueChanged.connect(self._edited)
        for shift in self.shifts:
            shift.toggled.connect(self._edited)

    def value(self) -> KMesh | None:
        n = tuple(count.value() for count in self.counts)
        if not any(n):
            return None  # empty: the field's default
        shift = tuple(int(box.isChecked()) for box in self.shifts)
        return KMesh((n[0], n[1], n[2]), (shift[0], shift[1], shift[2]))

    def set_value(self, mesh: KMesh | None) -> None:
        for widget in (*self.counts, *self.shifts):
            widget.blockSignals(True)
        for index in range(3):
            self.counts[index].setValue(mesh.n[index] if mesh is not None else 0)
            self.shifts[index].setChecked(bool(mesh.shift[index]) if mesh is not None else False)
        for widget in (*self.counts, *self.shifts):
            widget.blockSignals(False)
        self._show_summary()

    def _edited(self, *_args) -> None:
        self._show_summary()
        self.changed.emit()

    def _show_summary(self) -> None:
        value = self.value()
        text = mesh_summary(value or self._default)
        if value is None and self._default is not None:
            text = f"Vazio = padrão: {text}"
        show_message(self.summary, text)
