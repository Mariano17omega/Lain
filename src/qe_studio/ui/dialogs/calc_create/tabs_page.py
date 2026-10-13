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

In the ``avancado`` mode the previews can be edited (spec 39 R2): the typed text *wins*
(``core/calc_create/overrides``), so a field no longer changes that file, which says "editado" and
gets a bar with "Restaurar do formulário"; edits are kept by key across modes and checked as typed
(never blocking "Criar").
"""

from __future__ import annotations

from collections import defaultdict
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QPlainTextEdit, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from ....core.calc_create.overrides import apply_overrides, edit_issues, edits_in_force, is_edit
from ....core.calc_create.preview import EDITED_MARK
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
from .edit_bar import EditBar
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
        # Fields whose data follow others (spec 42 R2.4): field id → (fields it depends on, last values)
        self._depends = {f.id: f.depends_on for f in self.fields if f.depends_on}
        self._depended: dict[str, tuple] = {}
        self._base: CalcPlan = calc_type.plan(scf, {}, jobs, mode, name)  # the fields' alone
        self.plan: CalcPlan = self._base  # with the edits: what "Criar" writes
        self._edits: dict[str, str] = {}  # file key → the text typed in its preview
        self._edited = False
        self._target: tuple[Path, str] | None = None  # where the folder goes (step 1)
        self._extra_warnings: tuple[str, ...] = ()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._check)

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
        self.edit_bars: dict[str, EditBar] = {}  # by file key
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

    def _start(self) -> Path:
        """Where a field that picks a file opens its dialog: the SCF's folder."""
        return self.scf.path.parent if self.scf.path is not None else Path.home()

    def _group_tab(self, theme: ThemeManager, group: str, fields: list[FormField]) -> QWidget:
        form = FieldForm(theme, fields, self.scf.crystal, start=self._start())
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
            form = FieldForm(theme, fields, self.scf.crystal, start=self._start())
            form.changed.connect(self._on_changed)
            self.forms.append(form)
            self._form_of[planned.key] = form
            scroll.setWidget(form)
        preview = FilePreview(theme, planned.kind)
        preview.edited.connect(partial(self._on_text_edited, planned.key))
        self.previews[planned.key] = preview
        bar = EditBar()
        bar.restore_requested.connect(partial(self.restore, planned.key))
        self.edit_bars[planned.key] = bar
        self._panes[planned.key] = scroll
        side = QWidget()
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(bar)
        column.addWidget(preview, 1)
        splitter.addWidget(scroll)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([400, 560])  # the window's 960 px: the band path table needs room
        return splitter

    # -- mode ------------------------------------------------------------------------------------
    def set_mode(self, mode: Mode) -> None:
        """Show the fields of ``mode`` (what was typed in a hidden field stays) and plan again; the
        previews are editable in ``avancado`` only (the edits stay in either mode)."""
        self.mode = mode
        for preview in self.previews.values():
            preview.set_editable(mode == "avancado")
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
        """Plan now with what the fields hold, and show it; an edited file keeps its text."""
        self._timer.stop()
        self._base = self.calc_type.plan(self.scf, self.values(), self.jobs, self.mode, self.name)
        self._edits = edits_in_force(self._base, self._edits)
        self.plan = apply_overrides(self._base, self._edits)
        for form in self.forms:
            form.mark(dict(self.plan.problems))
        for key in self._keys:
            if key not in self._edits:
                self._show_generated(key)
            self._mark(key)
        self._show_files()
        self.planned.emit()
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Ask the type for the data of a field again when a field it depends on changed, with the
        values ``plan`` sees (the fields of the mode): the candidates follow the window, and the
        defaults in ``padrao``."""
        if not self._depends:
            return
        shown = {form_field.id for form_field in visible_fields(self.fields, self.mode)}
        values = {key: value for key, value in self.values().items() if key in shown}
        for field_id, depends in self._depends.items():
            now = tuple(values.get(key) for key in depends)
            last = self._depended.setdefault(field_id, now)
            if last == now:
                continue
            self._depended[field_id] = now
            data = self.calc_type.field_data(field_id, self.scf, values)
            self.form_of(field_id).set_data(field_id, data)

    def _show_generated(self, key: str) -> None:
        planned, preview = self._base.by_key(key), self.previews[key]
        if preview.diagnostics:  # of an edit that is gone
            preview.show_issues([])
        preview.show_derived(planned.text if planned is not None else "", self.scf.text)

    def _mark(self, key: str) -> None:
        """The tab label (the file's name can be edited) and the bar of an edited file."""
        planned = self.plan.by_key(key)
        edited = key in self._edits
        if planned is not None:
            label = planned.tab_label + (EDITED_MARK if edited else "")
            self.tabs.setTabText(self.tabs.indexOf(self._tab_of[key]), label)
        self.edit_bars[key].set_edited(edited)

    # -- files edited by hand (spec 39 R2) -------------------------------------------------------
    def _on_text_edited(self, key: str, text: str) -> None:
        generated = self._base.by_key(key)
        if generated is not None and is_edit(text, generated.text):
            self._edits[key] = text
        else:
            self._edits.pop(key, None)  # typed back to what the fields give: no edit
        self.plan = apply_overrides(self._base, self._edits)
        self._mark(key)
        self._show_files()
        self.planned.emit()
        if self.debounce_ms <= 0:
            self._check()
        else:
            self._check_timer.start(self.debounce_ms)

    def _check(self) -> None:
        """The write problems of every edited file (they only warn) and, for a pw.x input, the rows
        that differ from the SCF, now of the typed text."""
        self._check_timer.stop()
        for key in self._keys:
            preview = self.previews[key]
            text = self._edits.get(key)
            if text is None:
                if preview.diagnostics:
                    preview.show_issues([])
                continue
            preview.show_issues(edit_issues(preview.kind, text))
            preview.paint_changes(self.scf.text)

    def restore(self, key: str) -> None:
        """Drop the edit of ``key``: its preview shows what the fields give again."""
        if self._edits.pop(key, None) is None:
            return
        self.plan = apply_overrides(self._base, self._edits)
        self._show_generated(key)
        self._mark(key)
        self._show_files()
        self.planned.emit()

    @property
    def has_edits(self) -> bool:
        return bool(self._edits)

    def edited_keys(self) -> list[str]:
        """The files edited by hand, in tab order."""
        return [key for key in self._keys if key in self._edits]

    # -- state -----------------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        """Something the user would lose on closing: an edited field (in any mode), a file edited by
        hand or notes."""
        return self._edited or self.has_edits or bool(self.notes.toPlainText().strip())

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
            self._edits.keys(),
        )

    def tab_labels(self) -> list[str]:
        return [self.tabs.tabText(index) for index in range(self.tabs.count())]

    def shutdown(self) -> None:
        """The window is done (or builds another step 2): pending plans and file reads are dropped."""
        self._timer.stop()
        self._check_timer.stop()
        for form in self.forms:
            form.shutdown()

    def form_of(self, field_id: str) -> FieldForm:
        return next(form for form in self.forms if field_id in form.widgets)

    def widget_of(self, field_id: str) -> QWidget:
        return self.form_of(field_id).widgets[field_id]
