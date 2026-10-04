"""The fields of one generated file (spec 26 R4.1, R4.2): a widget per ``FormField``, as
``ParamsBody`` does for ``ParamField``.

Each field opens with its default (from the SCF when it has the value); an emptied field goes back
to it, which the placeholder says ("vazio = 8"). The window knows no type: the kinds of field are
the only cases here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ....core.calc_create.kpath import KMesh, KPath
from ....core.calc_create.preview import field_text
from ....core.calc_create.types import FormField
from ...busy import BusyTracker
from ...theme.manager import ThemeManager
from ...widgets.common import set_variant
from ...widgets.kpath_editor import KPathEditor
from ...widgets.param_widgets import Section
from .kmesh import KMeshEditor
from .labels import repolish

TITLE = "Parâmetros"


def placeholder(form_field: FormField) -> str:
    default = field_text(form_field.default)
    if default:
        return f"vazio = {default}"
    return "obrigatório" if form_field.required else "vazio = não escrever"


class FieldForm(QWidget):
    changed = pyqtSignal(bool)  # a value changed; True when the user did it

    def __init__(
        self,
        theme: ThemeManager,
        fields: Sequence[FormField],
        suggest: Callable[[], KPath] | None = None,
        busy: BusyTracker | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.fields = list(fields)
        self.widgets: dict[str, QWidget] = {}
        self.kpath_editor: KPathEditor | None = None
        self.section = Section(theme, TITLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.section)
        layout.addStretch(1)
        for form_field in self.fields:
            self._add(form_field, suggest, busy)

    # -- building --------------------------------------------------------------------------------
    def _add(
        self, form_field: FormField, suggest: Callable[[], KPath] | None, busy: BusyTracker | None
    ) -> None:
        label = form_field.label + (" *" if form_field.required else "")
        kind = form_field.kind
        if kind == "kpath":
            editor = KPathEditor(suggest, busy)
            editor.setAccessibleName(form_field.label)
            editor.setToolTip(form_field.tooltip)
            editor.changed.connect(self.changed)
            self.kpath_editor = editor
            title = set_variant(QLabel(label), "fieldLabel")
            title.setToolTip(form_field.tooltip)
            self.section.add_full(title)
            self.section.add_full(editor)
            self.widgets[form_field.id] = editor
            return
        widget = self._widget(form_field)
        self.section.add_row(label, widget, form_field.tooltip)
        item = self.section.grid.itemAtPosition(self.section.grid.rowCount() - 1, 0)
        text = item.widget() if item is not None else None
        if isinstance(text, QLabel):
            text.setWordWrap(True)  # long labels such as "forc_conv_thr" keep the 40/60 grid
        self.widgets[form_field.id] = widget

    def _widget(self, form_field: FormField) -> QWidget:
        kind, default = form_field.kind, form_field.default
        if kind == "choice":
            combo = QComboBox()
            combo.addItems(list(form_field.choices))
            combo.setCurrentIndex(combo.findText(str(default)) if default is not None else -1)
            combo.activated.connect(self._edited)
            return combo
        if kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(default))
            check.clicked.connect(self._edited)
            return check
        if kind == "kmesh":
            mesh = default if isinstance(default, KMesh) else None
            editor = KMeshEditor(mesh, mesh)
            editor.changed.connect(self._edited)
            return editor
        edit = QLineEdit(field_text(default))
        edit.setPlaceholderText(placeholder(form_field))
        edit.textEdited.connect(self._edited)
        return edit

    def _edited(self, *_args) -> None:
        self.changed.emit(True)

    # -- values ----------------------------------------------------------------------------------
    def values(self) -> dict[str, Any]:
        """What the fields hold, for ``CalcType.plan`` (an empty text is the default)."""
        out: dict[str, Any] = {}
        for field_id, widget in self.widgets.items():
            if isinstance(widget, QLineEdit):
                out[field_id] = widget.text()
            elif isinstance(widget, QComboBox):
                out[field_id] = widget.currentText() or None
            elif isinstance(widget, QCheckBox):
                out[field_id] = widget.isChecked()
            elif isinstance(widget, KMeshEditor | KPathEditor):
                out[field_id] = widget.value()
        return out

    def mark(self, problems: dict[str, str]) -> None:
        """Mark the fields with a problem (border and tooltip); the rest go back to normal."""
        for form_field in self.fields:
            widget = self.widgets[form_field.id]
            target = widget.table if isinstance(widget, KPathEditor) else widget
            problem = problems.get(form_field.id)
            if bool(target.property("invalid")) != bool(problem):
                target.setProperty("invalid", bool(problem))
                repolish(target)
            target.setToolTip(problem or form_field.tooltip)
