"""Step 2 of "Criar cálculo" (spec 26 R4): a tab per generated file, then "Arquivos" and
"Descrição".

Each file tab is its fields on the left and the file as it will be written on the right. Every
edit plans again (``CalcType.plan``: templates and input edits, no file read), debounced, and the
previews, the marks on the fields and the "Arquivos" tab follow. The tabs come from the type's plan
in order; the page knows no type.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....core.calc_create.preview import changed_lines
from ....core.calc_create.scf_info import ScfInfo
from ....core.calc_create.types import CalcPlan, CalcType, FormField, PlannedFile, field_problems
from ....core.calc_create.writer import files_to_write, folder_name, preview_name
from ....core.config import JobsConfig
from ...theme.manager import ThemeManager
from .form import FieldForm
from .labels import message_label, show_message
from .preview import FilePreview, FilesView

DEBOUNCE_MS = 250
NO_FIELDS = "Sem campos: o arquivo é gerado como mostrado ao lado."
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
        debounce_ms: int = DEBOUNCE_MS,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.calc_type, self.scf, self.jobs = calc_type, scf, jobs
        self.debounce_ms = debounce_ms
        self.fields = calc_type.fields(scf, jobs)
        self.plan: CalcPlan = calc_type.plan(scf, {}, jobs)
        self._edited = False
        self._parent_folder = Path()
        self._suffix = ""
        self._extra_warnings: tuple[str, ...] = ()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("calcTabs")
        self.tabs.setDocumentMode(True)
        self.forms: list[FieldForm] = []
        self.previews: dict[str, FilePreview] = {}
        for planned, fields in self._groups():
            self.tabs.addTab(
                self._file_tab(theme, planned.name, planned.kind, fields), planned.tab_label
            )
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
        self.flush()

    # -- building --------------------------------------------------------------------------------
    def _groups(self) -> list[tuple[PlannedFile, list[FormField]]]:
        """Each planned file and its fields; a field of no file goes to the first tab."""
        names = [planned.name for planned in self.plan.files]
        by_group: dict[str, list[FormField]] = defaultdict(list)
        for form_field in self.fields:
            group = form_field.group if form_field.group in names else names[0] if names else ""
            by_group[group].append(form_field)
        return [(planned, by_group.get(planned.name, [])) for planned in self.plan.files]

    def _file_tab(
        self,
        theme: ThemeManager,
        name: str,
        kind: str,
        fields: list[FormField],
    ) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        if fields:
            form = FieldForm(theme, fields, self.scf.crystal)
            form.changed.connect(self._on_changed)
            self.forms.append(form)
            left: QWidget = form
        else:
            left = QWidget()
            note = message_label()
            show_message(note, NO_FIELDS)
            box = QVBoxLayout(left)
            box.addWidget(note)
            box.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        preview = FilePreview(theme, kind)
        self.previews[name] = preview
        splitter.addWidget(scroll)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([400, 560])  # the window's 960 px: the band path table needs room
        return splitter

    # -- edits -----------------------------------------------------------------------------------
    def _on_changed(self, user: bool) -> None:
        if user:
            self._edited = True
        if self.debounce_ms <= 0:
            self.flush()
        else:
            self._timer.start(self.debounce_ms)

    def values(self) -> dict:
        out: dict = {}
        for form in self.forms:
            out.update(form.values())
        return out

    def flush(self) -> None:
        """Plan now with what the fields hold, and show it."""
        self._timer.stop()
        values = self.values()
        self.plan = self.calc_type.plan(self.scf, values, self.jobs)
        problems = field_problems(self.fields, values)
        for form in self.forms:
            form.mark(problems)
        original = self.scf.text
        for name, preview in self.previews.items():
            planned = self.plan.file(name)
            text = planned.text if planned is not None else ""
            derived = planned is not None and planned.kind == "pw_input" and text != original
            preview.set_text(text, changed_lines(original, text) if derived else ())
        self._show_files()
        self.planned.emit()

    # -- state -----------------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        """Something the user would lose on closing: an edited field or notes."""
        return self._edited or bool(self.notes.toPlainText().strip())

    def notes_text(self) -> str:
        return self.notes.toPlainText()

    def blocking(self) -> str:
        """Why "Criar" is disabled ("" = it is not)."""
        return self.plan.errors[0] if self.plan.errors else ""

    def warnings(self) -> list[str]:
        return list(dict.fromkeys([*self.plan.notes, *self._extra_warnings]))

    def set_target(self, parent: Path, suffix: str, warnings: tuple[str, ...] = ()) -> None:
        """Where the folder goes (step 1): the "Arquivos" tab shows it."""
        self._parent_folder, self._suffix, self._extra_warnings = parent, suffix, warnings
        self._show_files()

    def _show_files(self) -> None:
        if not self._suffix:
            return
        name = preview_name(self._parent_folder, self.calc_type, self._suffix)
        self.files_view.show_files(
            self._parent_folder / name,
            folder_name(self.calc_type, self._suffix),
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
