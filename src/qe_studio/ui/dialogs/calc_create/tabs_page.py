"""Step 2 of "Criar cálculo" (spec 26 R4, spec 28 R5): a tab per generated file, then "Arquivos"
and "Descrição".

Each file tab is its fields on the left and the file as it will be written on the right. Every
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
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.calc_type, self.scf, self.jobs = calc_type, scf, jobs
        self.mode: Mode = mode
        self.debounce_ms = debounce_ms
        self.fields = calc_type.fields(scf, jobs)
        self.plan: CalcPlan = calc_type.plan(scf, {}, jobs, mode)
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
        self._form_of: dict[str, FieldForm] = {}  # file key → its fields
        self._panes: dict[str, QWidget] = {}  # file key → the form's side of the splitter
        self.previews: dict[str, FilePreview] = {}  # by file key
        self._keys: list[str] = []  # the file tabs, in order
        for planned, fields in self._groups():
            self.tabs.addTab(self._file_tab(theme, planned, fields), planned.tab_label)
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
    def _groups(self) -> list[tuple[PlannedFile, list[FormField]]]:
        """Each planned file and its fields; a field of no file goes to the first tab."""
        keys = [planned.key for planned in self.plan.files]
        by_group: dict[str, list[FormField]] = defaultdict(list)
        for form_field in self.fields:
            group = form_field.group if form_field.group in keys else keys[0] if keys else ""
            by_group[group].append(form_field)
        return [(planned, by_group.get(planned.key, [])) for planned in self.plan.files]

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
            pane.setVisible(form is not None and form.set_visible(shown))
        self.flush()

    def form_shown(self, key: str) -> bool:
        """Whether the tab of file ``key`` shows its fields (not only the preview)."""
        return not self._panes[key].isHidden()

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
        self.plan = self.calc_type.plan(self.scf, self.values(), self.jobs, self.mode)
        for form in self.forms:
            form.mark(dict(self.plan.problems))
        original = self.scf.text
        for index, key in enumerate(self._keys):
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
