"""Step 2 of "Criar cálculo" (spec 26 R4, spec 28 R5): a tab per generated file, then "Arquivos"
and "Descrição".

Each file tab is its fields on the left and the file as it will be written on the right. A field whose
group is no file's key (spec 30: the atoms of a charge difference) has a tab of its own, named by the
group, before the file tabs: its form and no preview. Every
edit plans again (``CalcType.plan``: templates and input edits, no file read), debounced, and the
previews, the marks on the fields, the tab labels (a file name can be edited) and the "Arquivos" tab
follow. The mode only shows or hides rows (``visible_fields``, from the core) and plans again; a tab
with no field shown is its preview alone. The tabs come from the type's plan in order, keyed by
``PlannedFile.key``; the page knows no type.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QPlainTextEdit, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from ....core.calc_create.preview import changed_lines
from ....core.calc_create.scf_info import ScfInfo
from ....core.calc_create.types import (
    DEFAULT_MODE,
    CalcPlan,
    CalcType,
    FormField,
    Mode,
    PlannedFile,
    visible_fields,
)
from ....core.calc_create.writer import files_to_write, folder_name, preview_name
from ....core.config import JobsConfig
from ...theme.manager import ThemeManager
from .form import FieldForm
from .preview import FilePreview, FilesView

DEBOUNCE_MS = 250
NOTES_PLACEHOLDER = "Anotações sobre este cálculo (opcional)"
FILES_TAB = "Arquivos"
NOTES_TAB = "Descrição"


class TabsPage(QWidget):
    planned = pyqtSignal()  # a new plan: the window updates "Criar"

    def __init__(
        self,
        theme: ThemeManager,
        calc_type: CalcType,
        scf: ScfInfo,
        jobs: JobsConfig,
        mode: Mode = DEFAULT_MODE,
        debounce_ms: int = DEBOUNCE_MS,
        name: str = "",
        parent: QWidget | None = None,
    ):
        """``name``: the folder's name typed in step 1, for a type whose file names take it."""
        super().__init__(parent)
        self.calc_type, self.scf, self.jobs = calc_type, scf, jobs
        self.mode: Mode = mode
        self.debounce_ms = debounce_ms
        self.name = name
        self.fields = calc_type.fields(scf, jobs, name)
        self.plan: CalcPlan = calc_type.plan(scf, {}, jobs, mode, name)
        self._edited = False
        self._target: tuple[Path, str] | None = None  # where the folder goes (step 1)
        self._extra_warnings: tuple[str, ...] = ()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("calcTabs")
        self.tabs.setDocumentMode(True)
        self.forms: list[FieldForm] = []
        self._form_of: dict[str, FieldForm] = {}  # file key (or group) → its fields
        self._panes: dict[
            str, QWidget
        ] = {}  # file key → the form's side of the splitter; group → its tab
        self._group_tabs: set[str] = set()  # the groups that are tabs of their own
        self.previews: dict[str, FilePreview] = {}  # by file key
        self._keys: list[str] = []  # the file tabs, in order
        self._tab_of: dict[str, QWidget] = {}  # file key → its tab
        files, groups = self._groups()
        for group, fields in groups:
            self.tabs.addTab(self._group_tab(theme, group, fields), group)
        for planned, fields in files:
            tab = self._file_tab(theme, planned, fields)
            self.tabs.addTab(tab, planned.tab_label)
            self._tab_of[planned.key] = tab
            self._keys.append(planned.key)
        self.files_view = FilesView()
        self.tabs.addTab(self.files_view, FILES_TAB)
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("calcNotes")
        self.notes.setPlaceholderText(NOTES_PLACEHOLDER)
        self.notes.textChanged.connect(self._show_files)
        self.tabs.addTab(self.notes, NOTES_TAB)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.set_mode(mode)

    # -- building --------------------------------------------------------------------------------
    def _groups(
        self,
    ) -> tuple[list[tuple[PlannedFile, list[FormField]]], list[tuple[str, list[FormField]]]]:
        """Each planned file and its fields, and the tabs of their own (group → fields, in the order
        the type declares them). A field with no group goes to the first file's tab."""
        keys = [planned.key for planned in self.plan.files]
        by_group: dict[str, list[FormField]] = defaultdict(list)
        own: dict[str, list[FormField]] = {}
        for form_field in self.fields:
            if form_field.group and form_field.group not in keys:
                own.setdefault(form_field.group, []).append(form_field)
            else:
                group = form_field.group or (keys[0] if keys else "")
                by_group[group].append(form_field)
        files = [(planned, by_group.get(planned.key, [])) for planned in self.plan.files]
        return files, list(own.items())

    def _group_tab(self, theme: ThemeManager, group: str, fields: list[FormField]) -> QWidget:
        form = FieldForm(theme, fields, self.scf.crystal)
        form.changed.connect(self._on_changed)
        self.forms.append(form)
        self._form_of[group] = form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)
        self._panes[group] = scroll
        self._group_tabs.add(group)
        return scroll

    def _file_tab(
        self, theme: ThemeManager, planned: PlannedFile, fields: list[FormField]
    ) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        if fields:
            form = FieldForm(theme, fields, self.scf.crystal)
            form.changed.connect(self._on_changed)
            self.forms.append(form)
            self._form_of[planned.key] = form
            scroll.setWidget(form)
        preview = FilePreview(theme, planned.kind)
        self.previews[planned.key] = preview
        self._panes[planned.key] = scroll
        splitter.addWidget(scroll)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([400, 560])  # the window's 960 px: the band path table needs room
        return splitter

    # -- mode ------------------------------------------------------------------------------------
    def set_mode(self, mode: Mode) -> None:
        """Show the fields of ``mode`` (what was typed in a hidden field stays) and plan again."""
        self.mode = mode
        shown = {form_field.id for form_field in visible_fields(self.fields, mode)}
        for key, pane in self._panes.items():
            form = self._form_of.get(key)
            visible = form is not None and form.set_visible(shown)
            if key in self._group_tabs:  # the whole tab, not a side of it
                self.tabs.setTabVisible(self.tabs.indexOf(pane), visible)
            else:
                pane.setVisible(visible)
        self.flush()

    def form_shown(self, key: str) -> bool:
        """Whether the tab of file ``key`` shows its fields (not only the preview); for a group
        tab, whether the tab shows."""
        pane = self._panes[key]
        if key in self._group_tabs:
            return self.tabs.isTabVisible(self.tabs.indexOf(pane))
        return not pane.isHidden()

    # -- edits -----------------------------------------------------------------------------------
    def _on_changed(self, user: bool) -> None:
        if user:
            self._edited = True
        if self.debounce_ms <= 0:
            self.flush()
        else:
            self._timer.start(self.debounce_ms)

    def values(self) -> dict:
        """What every field holds, shown or not (``plan`` drops what the mode hides)."""
        out: dict = {}
        for form in self.forms:
            out.update(form.values())
        return out

    def flush(self) -> None:
        """Plan now with what the fields hold, and show it."""
        self._timer.stop()
        self.plan = self.calc_type.plan(self.scf, self.values(), self.jobs, self.mode, self.name)
        for form in self.forms:
            form.mark(dict(self.plan.problems))
        original = self.scf.text
        for key in self._keys:
            index = self.tabs.indexOf(self._tab_of[key])
            planned = self.plan.by_key(key)
            text = planned.text if planned is not None else ""
            derived = planned is not None and planned.kind == "pw_input" and text != original
            self.previews[key].set_text(text, changed_lines(original, text) if derived else ())
            if planned is not None:
                self.tabs.setTabText(index, planned.tab_label)
        self._show_files()
        self.planned.emit()

    # -- state -----------------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        """Something the user would lose on closing: an edited field (in any mode) or notes."""
        return self._edited or bool(self.notes.toPlainText().strip())

    def notes_text(self) -> str:
        return self.notes.toPlainText()

    def blocking(self) -> str:
        """Why "Criar" is disabled ("" = it is not)."""
        return self.plan.errors[0] if self.plan.errors else ""

    def warnings(self) -> list[str]:
        return list(dict.fromkeys([*self.plan.notes, *self._extra_warnings]))

    def set_target(self, parent: Path, suffix: str, warnings: tuple[str, ...] = ()) -> None:
        """Where the folder goes (step 1; the name may be empty): the "Arquivos" tab shows it."""
        self._target, self._extra_warnings = (parent, suffix), warnings
        self._show_files()

    def _show_files(self) -> None:
        if self._target is None:
            return
        parent, suffix = self._target
        name = preview_name(parent, self.calc_type, suffix)
        self.files_view.show_files(
            parent / name,
            folder_name(self.calc_type, suffix),
            files_to_write(self.plan, self.notes_text()),
            self.warnings(),
            self.plan.errors,
        )

    def tab_labels(self) -> list[str]:
        return [self.tabs.tabText(index) for index in range(self.tabs.count())]

    def form_of(self, field_id: str) -> FieldForm:
        return next(form for form in self.forms if field_id in form.widgets)

    def widget_of(self, field_id: str) -> QWidget:
        return self.form_of(field_id).widgets[field_id]
