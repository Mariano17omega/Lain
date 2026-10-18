"""The fields of one generated file (spec 26 R4.1, R4.2): a widget per ``FormField``, as
``ParamsBody`` does for ``ParamField``.

Each field opens with its default (from the SCF when it has the value); an emptied field goes back
to it, which the placeholder says ("vazio = 8"). The mode (spec 28) only shows or hides rows: a
hidden field keeps what was typed. The window knows no type: the kinds of field are the only cases
here.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ....core.calc_create.kpath import KMesh
from ....core.calc_create.preview import field_text
from ....core.calc_create.types import FormField
from ....core.qe.lattice import Crystal
from ....i18n import _
from ...theme.manager import ThemeManager
from ...widgets.atom_table import AtomRow, AtomTable
from ...widgets.common import set_variant
from ...widgets.kpath_editor import KPathEditor
from ...widgets.param_widgets import Section
from .kmesh import KMeshEditor
from .labels import repolish
from .scf_field import ScfFileField

TITLE = "Parâmetros"
UNIT_LABELS = {"angstrom": "Å"}  # the card's unit as a column head
ATOMS_MIN_HEIGHT = 320  # the atoms tab has the room: show a dozen rows


def placeholder(form_field: FormField) -> str:
    """What an empty field means: its ``hint`` when the type gives one ("vazio = o mais pesado")."""
    if form_field.hint:
        return form_field.hint
    default = field_text(form_field.default)
    if default:
        return f"vazio = {default}"
    return "obrigatório" if form_field.required else "vazio = não escrever"


def atom_rows(atoms: Any) -> list[AtomRow]:
    """The table's rows of an ``AtomRows`` (``fragments``), note included."""
    return [
        AtomRow(a.index, a.label, a.x, a.y, a.z, getattr(a, "note", ""))
        for a in getattr(atoms, "rows", ())
    ]


class FieldForm(QWidget):
    changed = pyqtSignal(bool)  # a value changed; True when the user did it

    def __init__(
        self,
        theme: ThemeManager,
        fields: Sequence[FormField],
        crystal: Crystal | None = None,
        parent: QWidget | None = None,
        start: Path | None = None,
    ):
        """``crystal``: the SCF's structure, for the band path checks (None: they are off);
        ``start``: where a field that picks a file opens its dialog (the SCF's folder)."""
        super().__init__(parent)
        self.theme = theme
        self.crystal = crystal
        self.start = start if start is not None else Path.home()
        self.fields = list(fields)
        self.widgets: dict[str, QWidget] = {}
        self.rows: dict[str, tuple[QWidget, ...]] = {}  # what shows a field: label and widget
        self._legends: dict[str, QLabel] = {}  # an ``atoms`` field's legend, or why it has no rows
        self.kpath_editor: KPathEditor | None = None
        self.section = Section(theme, TITLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.section)
        layout.addStretch(1)
        for form_field in self.fields:
            self._add(form_field)

    # -- building --------------------------------------------------------------------------------
    def _add(self, form_field: FormField) -> None:
        label = form_field.label + (" *" if form_field.required else "")
        kind = form_field.kind
        if kind == "kpath":
            editor = KPathEditor(self.theme, self.crystal.cell if self.crystal else None)
            editor.setAccessibleName(form_field.label)
            editor.setToolTip(form_field.tooltip)
            editor.changed.connect(self.changed)
            self.kpath_editor = editor
            title = set_variant(QLabel(label), "fieldLabel")
            title.setToolTip(form_field.tooltip)
            self.section.add_full(title)
            self.section.add_full(editor)
            self.widgets[form_field.id] = editor
            self.rows[form_field.id] = (title, editor)
            return
        if kind == "atoms":
            self._add_atoms(form_field, label)
            return
        widget = self._widget(form_field)
        self.section.add_row(label, widget, form_field.tooltip)
        item = self.section.grid.itemAtPosition(self.section.grid.rowCount() - 1, 0)
        text = item.widget() if item is not None else None
        if isinstance(text, QLabel):
            text.setWordWrap(True)  # long labels such as "forc_conv_thr" keep the 40/60 grid
        self.widgets[form_field.id] = widget
        self.rows[form_field.id] = (widget,) if text is None else (text, widget)

    def _add_atoms(self, form_field: FormField, label: str) -> None:
        """The table of atoms (``FormField.data``: ``AtomRows``) under the label and the legend."""
        atoms = form_field.data
        selected = form_field.default if isinstance(form_field.default, tuple) else ()
        unit = getattr(atoms, "unit", "") or "angstrom"
        table = AtomTable(atom_rows(atoms), selected, UNIT_LABELS.get(unit, unit))
        table.table.setMinimumHeight(ATOMS_MIN_HEIGHT)
        table.setAccessibleName(form_field.label)
        table.setToolTip(form_field.tooltip)
        table.changed.connect(self._edited)
        title = set_variant(QLabel(label), "fieldLabel")
        title.setToolTip(form_field.tooltip)
        legend = QLabel()
        legend.setWordWrap(True)
        self._legends[form_field.id] = legend
        self._show_legend(form_field, atoms)
        shown: tuple[QWidget, ...] = (title, legend, table)
        for widget in shown:
            self.section.add_full(widget)
        self.widgets[form_field.id] = table
        self.rows[form_field.id] = shown

    def _show_legend(self, form_field: FormField, atoms: Any) -> None:
        """The field's hint, or the reason it has no rows (a warning)."""
        legend = self._legends[form_field.id]
        error = getattr(atoms, "error", "")
        legend.setText(error or form_field.hint)
        variant = "warning" if error else "dialogText"
        if legend.property("variant") != variant:
            set_variant(legend, variant)
            repolish(legend)

    def set_data(self, field_id: str, data: Any) -> None:
        """New ``data`` for field ``field_id`` (spec 42 R2.4): an ``atoms`` table gets its rows again,
        keeping the marks of the atoms still listed. A change of marks is no user edit."""
        form_field = next(f for f in self.fields if f.id == field_id)
        table = self.widgets[field_id]
        if not isinstance(table, AtomTable):
            return
        self._show_legend(form_field, data)
        legend = self._legends[field_id]
        legend.setVisible(not table.isHidden() and bool(legend.text()))
        table.blockSignals(True)
        try:
            moved = table.set_rows(atom_rows(data))
        finally:
            table.blockSignals(False)
        if moved:
            self.changed.emit(False)

    def _widget(self, form_field: FormField) -> QWidget:
        kind, default = form_field.kind, form_field.default
        if kind == "choice":
            combo = QComboBox()
            # The data is the Portuguese token, the text its message.
            for choice in form_field.choices:
                combo.addItem(_(choice), choice)
            combo.setCurrentIndex(combo.findData(str(default)) if default is not None else -1)
            combo.activated.connect(self._edited)
            return combo
        if kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(default))
            check.clicked.connect(self._edited)
            return check
        if kind == "kmesh":
            mesh = default if isinstance(default, KMesh) else None
            editor = KMeshEditor(mesh, mesh, empty=form_field.hint)
            editor.changed.connect(self._edited)
            return editor
        if kind == "scf_file":
            field = ScfFileField(
                self.start, not form_field.required, form_field.label, form_field.hint
            )
            field.changed.connect(self._edited)
            return field
        edit = QLineEdit(field_text(default))
        edit.setPlaceholderText(placeholder(form_field))
        edit.textEdited.connect(self._edited)
        return edit

    def _edited(self, *_args) -> None:
        self.changed.emit(True)

    def set_visible(self, ids: Collection[str]) -> bool:
        """Show the rows of the fields ``ids`` and hide the rest; whether any row is shown. An empty
        legend stays hidden."""
        for field_id, row in self.rows.items():
            legend = self._legends.get(field_id)
            for widget in row:
                empty = legend is not None and widget is legend and not legend.text()
                widget.setVisible(field_id in ids and not empty)
        return any(field_id in ids for field_id in self.rows)

    def shown(self, field_id: str) -> bool:
        return not self.widgets[field_id].isHidden()

    # -- values ----------------------------------------------------------------------------------
    def values(self) -> dict[str, Any]:
        """What the fields hold, for ``CalcType.plan`` (an empty text is the default)."""
        out: dict[str, Any] = {}
        for field_id, widget in self.widgets.items():
            if isinstance(widget, QLineEdit):
                out[field_id] = widget.text()
            elif isinstance(widget, QComboBox):
                out[field_id] = widget.currentData() or None
            elif isinstance(widget, QCheckBox):
                out[field_id] = widget.isChecked()
            elif isinstance(widget, KMeshEditor | KPathEditor | AtomTable | ScfFileField):
                out[field_id] = widget.value()
        return out

    def shutdown(self) -> None:
        """The window is done: the fields that read files in a worker drop them."""
        for widget in self.widgets.values():
            if isinstance(widget, ScfFileField):
                widget.shutdown()

    def mark(self, problems: dict[str, str]) -> None:
        """Mark the fields with a problem (border and tooltip); the rest go back to normal."""
        for form_field in self.fields:
            widget = self.widgets[form_field.id]
            target = widget.table if isinstance(widget, KPathEditor | AtomTable) else widget
            if isinstance(widget, ScfFileField):
                target = widget.edit
            problem = problems.get(form_field.id)
            if bool(target.property("invalid")) != bool(problem):
                target.setProperty("invalid", bool(problem))
                repolish(target)
            target.setToolTip(problem or form_field.tooltip)
