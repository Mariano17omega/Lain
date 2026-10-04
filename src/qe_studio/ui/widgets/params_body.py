"""Tuning widgets of one plot: built from the module's parameter schema for one session."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QLocale, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.calculations.base import Dataset
from ...core.calculations.params import CommonParams, ParamField, ordered_sections
from ...core.compounds import atoms_summary
from ...core.plotting.session import PlotSession
from ..dialogs.atoms import ask_atoms
from ..theme.manager import ThemeManager
from .common import set_variant
from .param_widgets import ColorButton, Section, SeriesList

SECTIONS_KEY = "params/sections"  # QSettings: <kind>/<section title> → open (bool)
CLOSED_BY_DEFAULT = ("Arquivos",)


class ParamsBody(QWidget):
    """Summary, files and one accordion section per group of fields, bound to one session.

    Built once per session and kept while its plot tab is open; ``refresh_values`` pushes the
    current parameter values into the widgets.
    """

    changed = pyqtSignal(str)  # parameter name
    export_requested = pyqtSignal()
    remap_requested = pyqtSignal()
    restore_requested = pyqtSignal()

    def __init__(
        self,
        theme: ThemeManager,
        session: PlotSession[Dataset, CommonParams],
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("paramsBody")
        self.theme, self.session, self.settings = theme, session, settings
        self.schema = session.module.param_schema(session.dataset)  # what this body was built from
        self._fields = {f.name: f for f in self.schema}
        self._setters: dict[str, Callable[[Any], object]] = {}
        self._series: SeriesList | None = None
        self._series_field: ParamField | None = None
        self._updating = False

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._summary())
        column.addWidget(self._files_section())
        for definition in ordered_sections(session.module):
            fields = [f for f in self.schema if f.section == definition.name]
            if not fields:
                continue
            section = self._section(definition.name)
            for field in fields:
                self._add_field(section, field)
            if definition.export:
                button = set_variant(QPushButton("Salvar em plots/"), "primary")
                button.clicked.connect(self.export_requested)
                section.add_full(button)
            column.addWidget(section)
        restore = QPushButton("Restaurar padrões")
        restore.setToolTip(f"Voltar todos os ajustes ao padrão e apagar {session.kind}.plot")
        restore.clicked.connect(self.restore_requested)
        footer = QHBoxLayout()
        footer.setContentsMargins(10, 10, 8, 10)
        footer.addWidget(restore)
        column.addLayout(footer)
        column.addStretch(1)

    # -- values ---------------------------------------------------------------------------------
    def refresh_values(self) -> None:
        """Push current parameter values into the widgets (after pan/zoom, reference change)."""
        self._updating = True
        try:
            for name, setter in self._setters.items():
                setter(getattr(self.session.params, name))
            self._refresh_series()
            self.update_readout()
        finally:
            self._updating = False

    def set_param(self, name: str, value: Any) -> None:
        """Edit ``name`` as if the user had changed its widget."""
        self._set(name, value)

    def update_readout(self) -> None:
        info = self.session.info
        self.readout.setText(info.summary if info else "")
        notes = info.notes if info else ()
        self.notes.setText("\n".join(f"⚠ {note}" for note in notes))
        self.notes.setVisible(bool(notes))

    # -- construction ---------------------------------------------------------------------------
    def _summary(self) -> QWidget:
        """E_F / gap readout and detection or loading warnings, always visible on top."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(4)
        self.readout = set_variant(QLabel(), "readout")
        self.readout.setWordWrap(True)
        self.readout.setMinimumWidth(0)
        self.readout.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.readout)
        # What the last render noticed (e.g. two runs of a bands + DOS figure that disagree).
        self.notes = set_variant(QLabel(), "warning")
        self.notes.setWordWrap(True)
        self.notes.setMinimumWidth(0)
        self.notes.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.notes.hide()
        layout.addWidget(self.notes)
        for warning in self.session.dataset.warnings[:6]:
            label = set_variant(QLabel(f"⚠ {warning}"), "warning")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            layout.addWidget(label)
        return box

    def _files_section(self) -> QWidget:
        section = self._section("Arquivos")
        result = self.session.result
        for role in self.session.module.roles:
            paths = result.files.get(role.id)
            if not paths:
                continue
            text = paths[0].name if len(paths) == 1 else f"{len(paths)} arquivos"
            method = result.methods.get(role.id)
            name = set_variant(QLabel(role.label), "fieldLabel")
            value = set_variant(QLabel(text), "readout")
            value.setMinimumWidth(0)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            tip = "\n".join(str(p) for p in paths[:20])
            value.setToolTip(f"{tip}\n(detectado por {method.value})" if method else tip)
            section.add_full(name)
            section.add_full(value)
        if self.session.module.selectable:  # a figure of several folders has no mapping of its own
            remap = QPushButton("Remapear arquivos…")
            remap.clicked.connect(self.remap_requested)
            section.add_full(remap)
        return section

    def _section(self, title: str) -> Section:
        """An accordion section that remembers whether it is open, per kind of plot."""
        key = f"{SECTIONS_KEY}/{self.session.kind}/{title}"
        opened = title not in CLOSED_BY_DEFAULT
        if self.settings is not None:
            opened = self.settings.value(key, opened, type=bool)
        section = Section(self.theme, title, opened)
        section.opened_changed.connect(lambda on, k=key: self._remember_open(k, on))
        return section

    def _remember_open(self, key: str, opened: bool) -> None:
        if self.settings is not None:
            self.settings.setValue(key, opened)

    def _add_field(self, section: Section, field: ParamField) -> None:
        value = getattr(self.session.params, field.name)
        name = field.name
        if field.kind == "float":
            widget = self._float_widget(field, value)
        elif field.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(field.minimum or 0), int(field.maximum or 10**6))
            spin.setValue(int(value))
            spin.valueChanged.connect(lambda v: self._set(name, int(v)))
            self._setters[name] = lambda v, w=spin: w.setValue(int(v))
            widget = spin
        elif field.kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(value))
            check.toggled.connect(lambda v: self._set(name, bool(v)))
            self._setters[name] = lambda v, w=check: w.setChecked(bool(v))
            widget = check
        elif field.kind == "color":
            widget = self._color_widget(name, value)
        elif field.kind == "choice":
            combo = QComboBox()
            choices = list(field.choices)
            if value not in [c[0] for c in choices]:
                choices.append((value, str(value)))
            for data, label in choices:
                combo.addItem(label, data)
            combo.setCurrentIndex(combo.findData(value))
            combo.currentIndexChanged.connect(lambda _i, c=combo: self._set(name, c.currentData()))
            self._setters[name] = lambda v, c=combo: c.setCurrentIndex(max(c.findData(v), 0))
            widget = combo
        elif field.kind == "series":
            self._series = SeriesList()
            self._series_field = field
            self._series.changed.connect(lambda: self._emit(name))
            section.add_full(self._series)
            self._refresh_series()
            return
        elif field.kind == "atoms":
            section.add_full(self._atoms_widget(field))
            return
        else:  # text / labels
            edit = QLineEdit(str(value))
            if field.kind == "labels":
                edit.setProperty("variant", "mono")
                detected = ", ".join(self.session.module.default_labels(self.session.dataset))
                edit.setPlaceholderText(detected or "ex.: G, X, W, L, G")
            edit.editingFinished.connect(lambda e=edit: self._set(name, e.text()))
            self._setters[name] = lambda v, e=edit: e.setText(str(v))
            widget = edit
        section.add_row(field.label, widget, field.tooltip)

    def _atoms_widget(self, field: ParamField) -> QWidget:
        """The "Átomos…" button and how many atoms are shown; the window and the choices are the
        module's (``atoms_of``), disabled when the atoms could not be read."""
        name, session = field.name, self.session
        choices = session.module.atoms_of(session.dataset)
        total = len(choices.sites) if choices else 0
        button = QPushButton("Átomos…")
        button.setAccessibleName(field.label)
        summary = set_variant(QLabel(), "readout")

        def show(value: list[int] | None) -> None:
            summary.setText(atoms_summary(value, total) if total else "")

        def pick() -> None:
            if choices is None:
                return
            answer = ask_atoms(self, choices, getattr(session.params, name))
            if answer is not None:
                self._set(name, answer.atoms)
                show(answer.atoms)

        if choices is None or not choices.available:
            button.setEnabled(False)
            button.setToolTip("Não foi possível ler os átomos da saída do SCF")
        else:
            button.setToolTip("Escolher os átomos cujos orbitais são plotados")
            button.clicked.connect(pick)
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button)
        row.addWidget(summary, 1)

        show(getattr(session.params, name))
        self._setters[name] = show
        return widget

    def _color_widget(self, name: str, value: str) -> QWidget:
        swatch = ColorButton(value)
        edit = set_variant(QLineEdit(value), "mono")
        edit.setMaximumWidth(84)

        def picked(color: str) -> None:
            edit.setText(color)
            self._set(name, color)

        def show(color: str) -> None:
            swatch.set_color(color)
            edit.setText(color)

        swatch.color_changed.connect(picked)
        edit.editingFinished.connect(lambda: self._color_typed(name, edit, swatch))
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(swatch)
        row.addWidget(edit, 1)
        self._setters[name] = show
        return widget

    def _float_widget(self, field: ParamField, value: float | None) -> QWidget:
        name = field.name
        spin = QDoubleSpinBox()
        spin.setLocale(QLocale.c())
        spin.setDecimals(field.decimals)
        spin.setRange(
            field.minimum if field.minimum is not None else -1e9,
            field.maximum if field.maximum is not None else 1e9,
        )
        spin.setSingleStep(field.step)
        spin.setKeyboardTracking(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        if field.suffix:
            spin.setSuffix(f" {field.suffix}")
        if not field.optional:
            spin.setValue(float(value or 0.0))
            spin.valueChanged.connect(lambda v: self._set(name, float(v)))
            self._setters[name] = lambda v, w=spin: w.setValue(float(v))
            return spin
        auto = QCheckBox("auto")
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(spin, 1)
        row.addWidget(auto)

        def show(v: float | None) -> None:
            auto.setChecked(v is None)
            spin.setEnabled(v is not None)
            if v is not None:
                spin.setValue(float(v))

        show(value)
        spin.valueChanged.connect(lambda v: self._set(name, float(v)))
        auto.toggled.connect(
            lambda on: (spin.setEnabled(not on), self._set(name, None if on else spin.value()))
        )
        self._setters[name] = show
        return widget

    def _refresh_series(self) -> None:
        field = self._series_field
        if self._series is None or field is None:
            return
        session = self.session
        colors = session.module.series_colors(session.dataset, session.params, session.style)
        self._series.set_series(
            colors, getattr(session.params, field.name), getattr(session.params, field.colors)
        )

    # -- edits ----------------------------------------------------------------------------------
    def _set(self, name: str, value: Any) -> None:
        if self._updating:
            return
        params = self.session.params
        old = getattr(params, name)
        if old == value:
            return
        setattr(params, name, value)
        self.session.module.param_changed(self.session.dataset, params, name, old)
        if self._fields[name].refreshes:
            self.refresh_values()
        self._emit(name)

    def _emit(self, name: str) -> None:
        if not self._updating:
            self.changed.emit(name)

    def _color_typed(self, name: str, edit: QLineEdit, swatch: ColorButton) -> None:
        color = QColor(edit.text().strip())
        if color.isValid():
            swatch.set_color(color.name())
            self._set(name, color.name())
        else:
            edit.setText(swatch.color)
