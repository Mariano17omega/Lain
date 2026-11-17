"""The fields of one generated file (spec 26 R4.1, R4.2): a widget per ``FormField``, as
``ParamsBody`` does for ``ParamField``.

Each field opens with its default (from the SCF when it has the value); an emptied field goes back
to it, which the placeholder says ("vazio = 8"). An ``auto`` field (the pools, spec 102) has no default:
the plan computes its value and the window shows it, until the user types one. What the plan warns about
a field (``CalcPlan.advice``, spec 105) is a line under it, which never blocks. The mode (spec 28) only
shows or hides rows: a hidden field keeps what was typed. The window knows no type: the kinds of field are the only cases
here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ....core.calc_create.kpath import KMesh
from ....core.calc_create.preview import field_text
from ....core.calc_create.types import CalcPlan, FormField
from ....core.qe.lattice import Crystal
from ....i18n import _
from ...theme.manager import ThemeManager
from ...theme.scale import scaled
from ...widgets.common import set_variant
from ...widgets.no_wheel import NoWheelComboBox
from ...widgets.plot.atom_table import NOTE_HEADER, AtomRow, AtomTable
from ...widgets.plot.param_widgets import Section
from .kmesh import KMeshEditor
from .kpath_editor import KPathEditor
from .labels import repolish
from .scf_field import ScfFileField

TITLE = _("Parâmetros")
UNIT_LABELS = {"angstrom": "Å"}  # the card's unit as a column head
ATOMS_MIN_HEIGHT = 320  # the atoms tab has the room: show a dozen rows


def placeholder(form_field: FormField) -> str:
    """What an empty field means: its ``hint`` when the type gives one ("vazio = o mais pesado"); a
    text without a default whose ``data`` is a text goes back to it (a name that follows a choice,
    spec 95 R2.5)."""
    if form_field.hint:
        return form_field.hint
    default = field_text(form_field.default)
    if not default and form_field.kind == "text" and isinstance(form_field.data, str):
        default = form_field.data
    if default:
        return _("vazio = {default}").format(default=default)
    return _("obrigatório") if form_field.required else _("vazio = não escrever")


def atom_rows(atoms: Any) -> list[AtomRow]:
    """The table's rows of an ``AtomRows`` (``fragments``), note included."""
    return [
        AtomRow(a.index, a.label, a.x, a.y, a.z, getattr(a, "note", ""))
        for a in getattr(atoms, "rows", ())
    ]


def fill_choices(combo: QComboBox, choices: Any) -> None:
    """The options of an ``atom_choice`` field (``text`` shown as it is, ``value``); the first alone
    leaves nothing to choose, so the combo is off."""
    combo.clear()
    for choice in choices or ():
        combo.addItem(choice.text, choice.value)
    combo.setEnabled(combo.count() > 1)


class FieldForm(QWidget):
    changed = pyqtSignal(bool)  # a value changed; True when the user did it
    # A field began reading its file. The plan is not made again (it keeps the old file's data,
    # which is how the anchor stays when the same file is picked, spec 87 R1.5): the window only
    # asks again whether "Criar" may go on.
    reading_started = pyqtSignal()

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
        self._advice: dict[str, QLabel] = {}  # what the plan warns about a field, under its row
        self.kpath_editor: KPathEditor | None = None
        # The ``auto`` fields, and those the user typed in (the rest show what the plan computed).
        self._auto = {f.id for f in self.fields if f.auto}
        self._typed: set[str] = set()
        self._filling = False  # ``show_plan`` is writing a text: not the user
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
        advice = set_variant(QLabel(), "warning")
        advice.setWordWrap(True)
        advice.hide()  # until a plan says something
        self.section.add_full(advice)
        self._advice[form_field.id] = advice

    def _add_atoms(self, form_field: FormField, label: str) -> None:
        """The table of atoms (``FormField.data``: ``AtomRows``) under the label and the legend. The
        marks start from the field's default, else from those the rows suggest (spec 76)."""
        atoms = form_field.data
        default = form_field.default
        selected = default if isinstance(default, tuple) else getattr(atoms, "marked", None) or ()
        unit = getattr(atoms, "unit", "") or "angstrom"
        table = AtomTable(
            atom_rows(atoms),
            selected,
            UNIT_LABELS.get(unit, unit),
            check_header=getattr(atoms, "check_header", ""),
            note_header=getattr(atoms, "note_header", "") or NOTE_HEADER,
            species_filter=getattr(atoms, "species_filter", False),
        )
        table.table.setMinimumHeight(scaled(ATOMS_MIN_HEIGHT))
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
        keeping the marks of the atoms still listed, or taking those the data suggest (``marked``,
        spec 76), an ``atom_choice`` its options and a line edit its placeholder only (what the user
        typed stays, spec 95 R2.5). A change of marks or of the choice is no user edit."""
        form_field = next(f for f in self.fields if f.id == field_id)
        table = self.widgets[field_id]
        if isinstance(table, QComboBox):
            self._set_choices(table, data)
            return
        if isinstance(table, QLineEdit):
            table.setPlaceholderText(placeholder(dataclasses.replace(form_field, data=data)))
            return
        if not isinstance(table, AtomTable):
            return
        self._show_legend(form_field, data)
        legend = self._legends[field_id]
        legend.setVisible(not table.isHidden() and bool(legend.text()))
        table.blockSignals(True)
        try:
            moved = table.set_rows(atom_rows(data), getattr(data, "marked", None))
        finally:
            table.blockSignals(False)
        if moved:
            self.changed.emit(False)

    def _set_choices(self, combo: QComboBox, choices: Any) -> None:
        """New options: the same option (text and value) stays chosen, else the first (spec 87 R1.4)."""
        text, value = combo.currentText(), combo.currentData()
        fill_choices(combo, choices)
        same = (
            index
            for index in range(combo.count())
            if (combo.itemText(index), combo.itemData(index)) == (text, value)
        )
        combo.setCurrentIndex(next(same, 0))
        if combo.currentData() != value:
            self.changed.emit(False)

    def _widget(self, form_field: FormField) -> QWidget:
        kind, default = form_field.kind, form_field.default
        if kind == "choice":
            combo = NoWheelComboBox()
            # The data is the Portuguese token, the text its message.
            for choice in form_field.choices:
                combo.addItem(_(choice), choice)
            combo.setCurrentIndex(combo.findData(str(default)) if default is not None else -1)
            combo.activated.connect(self._edited)
            return combo
        if kind == "atom_choice":
            combo = NoWheelComboBox()
            fill_choices(combo, form_field.data)
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
            field.started.connect(self.reading_started)
            return field
        edit = QLineEdit(field_text(default))
        edit.setPlaceholderText(placeholder(form_field))
        edit.textEdited.connect(self._edited)
        if form_field.auto:
            edit.textChanged.connect(self._auto_changed)
        return edit

    def _auto_changed(self, _text: str) -> None:
        """A text of an ``auto`` field changed: typed (or set by a caller) when it holds something, back
        to the plan's when emptied. The window's own filling is neither."""
        if self._filling:
            return
        for field_id in self._auto:
            widget = self.widgets.get(field_id)
            if isinstance(widget, QLineEdit):
                (self._typed.add if widget.text().strip() else self._typed.discard)(field_id)

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
            advice = self._advice.get(field_id)
            if advice is not None:
                advice.setVisible(field_id in ids and bool(advice.text()))
        return any(field_id in ids for field_id in self.rows)

    def shown(self, field_id: str) -> bool:
        return not self.widgets[field_id].isHidden()

    # -- values ----------------------------------------------------------------------------------
    def values(self) -> dict[str, Any]:
        """What the fields hold, for ``CalcType.plan`` (an empty text is the default)."""
        out: dict[str, Any] = {}
        for field_id, widget in self.widgets.items():
            if isinstance(widget, QLineEdit):
                shown = field_id in self._auto and field_id not in self._typed
                out[field_id] = "" if shown else widget.text()  # what the plan shows is not a value
            elif isinstance(widget, QComboBox):
                out[field_id] = widget.currentData() or None
            elif isinstance(widget, QCheckBox):
                out[field_id] = widget.isChecked()
            elif isinstance(widget, KMeshEditor | KPathEditor | AtomTable | ScfFileField):
                out[field_id] = widget.value()
        return out

    @property
    def reading(self) -> bool:
        """A field is still reading its file in a worker: the plan does not have it yet."""
        return any(isinstance(w, ScfFileField) and w.reading for w in self.widgets.values())

    def shutdown(self) -> None:
        """The window is done: the fields that read files in a worker drop them."""
        for widget in self.widgets.values():
            if isinstance(widget, ScfFileField):
                widget.shutdown()

    def show_plan(self, plan: CalcPlan) -> None:
        """What a plan says to the fields: mark those with a problem, show what it warns about each
        (``advice``) and fill the ``auto`` ones the user did not type in with the value it computed."""
        self.mark(dict(plan.problems))
        self._advise(plan.advice)
        auto = plan.auto
        for form_field in self.fields:
            widget = self.widgets[form_field.id]
            if not form_field.auto or not isinstance(widget, QLineEdit):
                continue
            value = auto.get(form_field.id)
            shown = field_text(value)
            if value is not None:
                widget.setPlaceholderText(_("vazio = {default} (automático)").format(default=shown))
            else:
                widget.setPlaceholderText(placeholder(form_field))
            if form_field.id in self._typed or widget.text() == shown:
                continue
            self._filling = True
            try:
                widget.setText(shown)
            finally:
                self._filling = False

    def _advise(self, advice: Mapping[str, str]) -> None:
        """The plan's warning under each field shown (none: the line goes)."""
        for field_id, label in self._advice.items():
            text = advice.get(field_id, "")
            if label.text() != text:
                label.setText(text)
            label.setVisible(bool(text) and self.shown(field_id))

    def advice(self, field_id: str) -> str:
        """The warning shown under field ``field_id`` ("": none, or the field is hidden)."""
        label = self._advice.get(field_id)
        return label.text() if label is not None and not label.isHidden() else ""

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
