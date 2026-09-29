"""Plot parameters panel (PRD §2.1.2 plot mode), built from the module's parameter schema."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QLocale, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.calculations.params import SECTIONS, ParamField
from ..plot_session import PlotSession
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, set_variant


class ColorButton(QToolButton):
    color_changed = pyqtSignal(str)

    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        set_variant(self, "swatch")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: str) -> None:
        self.color = color
        self.setStyleSheet(f"background: {color};")
        self.setToolTip(color)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color), self, "Escolher cor")
        if chosen.isValid():
            self.set_color(chosen.name())
            self.color_changed.emit(chosen.name())


class Section(QWidget):
    """Collapsible accordion section with a 40/60 label/field grid."""

    def __init__(self, theme: ThemeManager, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = set_variant(QToolButton(), "sectionHeader")
        self.header.setText(title.upper())
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setIconSize(QSize(12, 12))
        self.body = set_variant(QWidget(), "sectionBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(10, 6, 8, 8)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(4)
        self.grid.setColumnStretch(0, 2)
        self.grid.setColumnStretch(1, 3)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        theme.theme_changed.connect(self._refresh_icon)
        self._refresh_icon()

    def add_row(self, label: str, widget: QWidget, tooltip: str = "") -> None:
        row = self.grid.rowCount()
        text = set_variant(QLabel(label), "fieldLabel")
        text.setToolTip(tooltip)
        text.setMinimumWidth(0)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, widget.sizePolicy().verticalPolicy())
        widget.setToolTip(tooltip or widget.toolTip())
        self.grid.addWidget(text, row, 0)
        self.grid.addWidget(widget, row, 1)

    def add_full(self, widget: QWidget) -> None:
        self.grid.addWidget(widget, self.grid.rowCount(), 0, 1, 2)

    def _toggle(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self._refresh_icon()

    def _refresh_icon(self, *_args) -> None:
        icon = "expand_more" if self.header.isChecked() else "chevron_right"
        self.header.setIcon(self.theme.icon(icon, "text_muted", size=12))


class SeriesList(QWidget):
    """PDOS series: visibility checkbox + color swatch per group."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(2)

    def rebuild(self, colors: dict[str, str], hidden: list[str], overrides: dict[str, str]):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._hidden, self._overrides = hidden, overrides
        for label, color in colors.items():
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            check = QCheckBox(label)
            check.setChecked(label not in hidden)
            swatch = ColorButton(color)
            check.toggled.connect(lambda on, name=label: self._set_visible(name, on))
            swatch.color_changed.connect(lambda c, name=label: self._set_color(name, c))
            row_layout.addWidget(swatch)
            row_layout.addWidget(check, 1)
            self.layout_.addWidget(row)

    def _set_visible(self, name: str, visible: bool) -> None:
        if visible and name in self._hidden:
            self._hidden.remove(name)
        elif not visible and name not in self._hidden:
            self._hidden.append(name)
        self.changed.emit()

    def _set_color(self, name: str, color: str) -> None:
        self._overrides[name] = color
        self.changed.emit()


class ParamsPanel(QWidget):
    changed = pyqtSignal(str)  # parameter name
    back_requested = pyqtSignal()
    remap_requested = pyqtSignal()
    export_requested = pyqtSignal()
    labels_edited = pyqtSignal(list)

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("paramsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme = theme
        self.session: PlotSession | None = None
        self._setters: dict[str, Callable[[Any], None]] = {}
        self._series: SeriesList | None = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = PanelHeader(theme, "Ajuste do gráfico", "tune")
        self.back_button = header.add_button(IconButton(theme, "account_tree", "Voltar à árvore"))
        self.back_button.clicked.connect(self.back_requested)
        layout.addWidget(header)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("paramsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll, 1)
        self.body: QWidget | None = None
        self._placeholder()

    # -- binding --------------------------------------------------------------------------------
    def bind(self, session: PlotSession | None) -> None:
        self.session = session
        self._setters.clear()
        self._series = None
        if session is None:
            self._placeholder()
            return
        body = QWidget()
        body.setObjectName("paramsBody")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._summary(session))
        column.addWidget(self._files_section(session))
        schema = session.module.param_schema(session.dataset)
        for title in SECTIONS:
            fields = [f for f in schema if f.section == title]
            if not fields:
                continue
            section = Section(self.theme, title)
            for field in fields:
                self._add_field(section, field)
            if title == "Exportar":
                button = set_variant(QPushButton("Salvar em plots/"), "primary")
                button.clicked.connect(self.export_requested)
                section.add_full(button)
            column.addWidget(section)
        column.addStretch(1)
        self._set_body(body)

    def refresh_values(self) -> None:
        """Push current parameter values into the widgets (after pan/zoom, reference change)."""
        if self.session is None:
            return
        self._updating = True
        try:
            for name, setter in self._setters.items():
                setter(getattr(self.session.params, name))
            self._rebuild_series()
            self.readout.setText(self.session.info.summary if self.session.info else "")
        finally:
            self._updating = False

    # -- construction ---------------------------------------------------------------------------
    def _placeholder(self) -> None:
        body = QWidget()
        body.setObjectName("paramsBody")
        layout = QVBoxLayout(body)
        hint = set_variant(
            QLabel("Gere um gráfico para ajustar\nos parâmetros de plotagem."), "fieldLabel"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint, 1)
        self._set_body(body)

    def _set_body(self, body: QWidget) -> None:
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.body = body
        self.scroll.setWidget(body)

    def _summary(self, session: PlotSession) -> QWidget:
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
        for warning in session.dataset.warnings[:6]:
            label = set_variant(QLabel(f"⚠ {warning}"), "warning")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            layout.addWidget(label)
        return box

    def _files_section(self, session: PlotSession) -> QWidget:
        section = Section(self.theme, "Arquivos")
        result = session.result
        for role in session.module.roles:
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
        remap = QPushButton("Remapear arquivos…")
        remap.clicked.connect(self.remap_requested)
        section.add_full(remap)
        section.header.setChecked(False)
        return section

    def _add_field(self, section: Section, field: ParamField) -> None:
        params = self.session.params
        value = getattr(params, field.name)
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
            swatch = ColorButton(value)
            edit = set_variant(QLineEdit(value), "mono")
            edit.setMaximumWidth(84)
            swatch.color_changed.connect(lambda c, e=edit: (e.setText(c), self._set(name, c)))
            edit.editingFinished.connect(lambda e=edit, s=swatch: self._color_typed(name, e, s))
            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(swatch)
            row.addWidget(edit, 1)
            self._setters[name] = lambda v, s=swatch, e=edit: (s.set_color(v), e.setText(v))
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
            self._series.changed.connect(lambda: self._emit("series_colors"))
            section.add_full(self._series)
            self._rebuild_series()
            return
        else:  # text / labels
            edit = QLineEdit(str(value))
            if field.kind == "labels":
                edit.setProperty("variant", "mono")
                detected = ", ".join(getattr(self.session.dataset, "labels", []) or [])
                edit.setPlaceholderText(detected or "ex.: G, X, W, L, G")
                edit.editingFinished.connect(lambda e=edit: self._labels_typed(e.text()))
            edit.editingFinished.connect(lambda e=edit: self._set(name, e.text()))
            self._setters[name] = lambda v, e=edit: e.setText(str(v))
            widget = edit
        section.add_row(field.label, widget, field.tooltip)

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
            spin.setValue(float(value))
            spin.valueChanged.connect(lambda v: self._set(name, float(v)))
            self._setters[name] = lambda v, w=spin: w.setValue(float(v))
            return spin
        auto = QCheckBox("auto")
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(spin, 1)
        row.addWidget(auto)

        def show(v, w=spin, a=auto) -> None:
            a.setChecked(v is None)
            w.setEnabled(v is not None)
            if v is not None:
                w.setValue(float(v))

        show(value)
        spin.valueChanged.connect(lambda v: self._set(name, float(v)))
        auto.toggled.connect(
            lambda on, w=spin: (w.setEnabled(not on), self._set(name, None if on else w.value()))
        )
        self._setters[name] = show
        return widget

    def _rebuild_series(self) -> None:
        if self._series is None or self.session is None:
            return
        session = self.session
        colors = session.module.series_colors(
            session.dataset, session.params, self.theme.plot_style
        )
        self._series.rebuild(colors, session.params.hidden_series, session.params.series_colors)

    # -- edits ----------------------------------------------------------------------------------
    def _set(self, name: str, value: Any) -> None:
        if self._updating or self.session is None:
            return
        params = self.session.params
        old = getattr(params, name)
        if old == value:
            return
        setattr(params, name, value)
        self.session.module.param_changed(self.session.dataset, params, name, old)
        if name in ("reference", "shift_to_fermi", "fermi_source", "grouping"):
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

    def _labels_typed(self, text: str) -> None:
        labels = [part.strip() for part in text.split(",")] if text.strip() else []
        self.labels_edited.emit(labels)
