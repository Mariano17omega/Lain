"""Step 2 of "Criar cálculo" (spec 26 R4, spec 28 R5): a tab per generated file, then "Arquivos"
and "Descrição".

Each file tab is its fields on the left and the file as it will be written on the right. A field whose
group is no file's key (spec 30: the atoms of a charge difference) has a tab of its own, named by the
group, before the file tabs: its form and no preview. Every
edit plans again (``CalcType.plan``: templates and input edits, no file read), debounced, and the
previews, the marks on the fields, the tab labels (a file name can be edited) and the "Arquivos" tab
follow. The mode only shows or hides rows (``shown_fields``, from the core) and plans again; a tab
with no field shown is its preview alone. The tabs come from the type's plan in order, keyed by
``PlannedFile.key``; the page knows no type.

In the ``avancado`` mode the previews can be edited (spec 39 R2): the typed text *wins*
(``core/calc_create/overrides``), so a field no longer changes that file, which says "editado" and
gets a bar with "Restaurar do formulário"; edits are kept by key across modes and checked as typed
(what is checked only warns; the errors the type reads in the texts do block "Criar").
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QPlainTextEdit, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from ....core.calc_create.fingerprint import Source, fingerprint_text, real_paths, sources
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
    resolve,
    shown_fields,
    visible_fields,
)
from ....core.calc_create.writer import files_to_write, preview_names
from ....core.config import JobsConfig
from ....core.tasks import TaskGroup
from ....i18n import _
from ...theme.manager import ThemeManager
from .edit_bar import EditBar
from .form import FieldForm
from .preview import FilePreview, FilesView

DEBOUNCE_MS = 250
NOTES_PLACEHOLDER = _("Anotações sobre este cálculo (opcional)")
FILES_TAB = _("Arquivos")
NOTES_TAB = _("Descrição")
NO_SITE = _("Sem sítio: o nome fica sem a marca")  # spec 77 R2.2


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
        scfs: tuple[ScfInfo, ...] = (),
        root: Path | None = None,
    ):
        """``name``: the folder's name typed in step 1, for a type whose file names take it;
        ``scfs``: step 1's list, for a ``multi_scf`` type (spec 79); ``root``: the project's root,
        what the paths of the notes it starts with are relative to."""
        super().__init__(parent)
        self.calc_type, self.scf, self.jobs, self._root = calc_type, scf, jobs, root
        self.mode: Mode = mode
        self.debounce_ms = debounce_ms
        self.name, self.scfs = name, scfs
        self.fields = calc_type.fields(scf, jobs, name, scfs)
        # Fields whose data follow others (spec 42 R2.4): field id → (fields it depends on, last values)
        self._depends = {f.id: f.depends_on for f in self.fields if f.depends_on}
        followed = {key for depends in self._depends.values() for key in depends}
        self._depended_fields = [f for f in self.fields if f.id in followed]
        self._depended: dict[str, tuple] = {}
        self._base: CalcPlan = calc_type.plan(scf, {}, jobs, mode, name, scfs)  # the fields' alone
        self.plan: CalcPlan = self._base  # with the edits: what "Criar" writes
        self._edits: dict[str, str] = {}  # file key → the text typed in its preview
        self._edited = False
        # step 1's place, the name asked for and the one the folder would get now (``set_target``)
        self._target: tuple[Path, str, str] | None = None
        # step 1's ask (place, name, "Numerar", inherited suffix, "Sítio no nome") and the tag the
        # name was made with: the site changes with the fields (spec 77)
        self._naming: tuple[Path, str, bool, str, bool] | None = None
        self._named_tag = ""
        self._extra_warnings: tuple[str, ...] = ()
        self._fingerprint_root: Path | None = None  # step 1's "Gerar fingerprint.md" (spec 80)
        self._real: dict[Path, Path] = {}  # its paths with the links followed, as the writer's
        self._asked: set[Path] = set()  # what the running "real" worker resolves
        self._tasks = TaskGroup()
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
        for group, fields in groups:  # the group is a token marked with N_ by its type
            self.tabs.addTab(self._group_tab(theme, group, fields), _(group))
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
        self._first_notes = self._notes_now()  # where the SCFs came from
        self.notes.setPlainText(self._first_notes)
        if self._first_notes and root is not None:  # their paths, with links followed
            self._ask_real([root, *(each.path for each in scfs if each.path is not None)])
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
        self._show_fields()
        self.flush()

    def _show_fields(self) -> None:
        """Show the rows the mode and the values leave (spec 87 R3); a tab with none is its preview."""
        shown = {f.id for f in shown_fields(self.fields, self.mode, self.values())}
        for key, pane in self._panes.items():
            form = self._form_of.get(key)
            visible = form is not None and form.set_visible(shown)
            if key in self._group_tabs:  # the whole tab, not a side of it
                self.tabs.setTabVisible(self.tabs.indexOf(pane), visible)
            else:
                pane.setVisible(visible)

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
        self._show_fields()  # at once: a choice shows or hides the rows under it
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
        self._base = self.calc_type.plan(
            self.scf, self.values(), self.jobs, self.mode, self.name, self.scfs
        )
        self._edits = edits_in_force(self._base, self._edits)
        self.plan = apply_overrides(self._base, self._edits, self.calc_type)
        if self._naming is not None and self._tag() != self._named_tag:
            self._name_target()
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
        defaults in ``padrao``. A change is one of the values resolved (a hidden field is its
        default): a mode that only shows the defaults remakes nothing, such as the marks of the fixed
        atoms (spec 76)."""
        if not self._depends:
            return
        shown = {form_field.id for form_field in visible_fields(self.fields, self.mode)}
        values = {key: value for key, value in self.values().items() if key in shown}
        resolved, __ = resolve(self._depended_fields, values)
        for field_id, depends in self._depends.items():
            now = tuple(resolved.get(key) for key in depends)
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
        preview.show_derived(planned.text if planned is not None else "", self._source(key))

    def _source(self, key: str) -> str:
        """The text the file of ``key`` derives from: its own SCF (spec 79), or the SCF."""
        planned = self._base.by_key(key)
        source = planned.source if planned is not None else None
        return self.scf.text if source is None else source

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
        self.plan = apply_overrides(self._base, self._edits, self.calc_type)
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
            preview.paint_changes(self._source(key))

    def restore(self, key: str) -> None:
        """Drop the edit of ``key``: its preview shows what the fields give again."""
        if self._edits.pop(key, None) is None:
            return
        self.plan = apply_overrides(self._base, self._edits, self.calc_type)
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
        hand or notes other than those the page started with."""
        notes = self.notes.toPlainText().strip()
        return self._edited or self.has_edits or notes not in ("", self._first_notes.strip())

    def notes_text(self) -> str:
        return self.notes.toPlainText()

    def blocking(self) -> str:
        """Why "Criar" is disabled ("" = it is not)."""
        return self.plan.errors[0] if self.plan.errors else ""

    def warnings(self) -> list[str]:
        no_site = (
            [NO_SITE] if self._naming is not None and self._naming[4] and not self._tag() else []
        )
        return list(dict.fromkeys([*self.plan.notes, *self._extra_warnings, *no_site]))

    def set_target(
        self,
        parent: Path,
        suffix: str,
        warnings: tuple[str, ...] = (),
        numbered: bool = False,
        inherited: str = "",
        use_tag: bool = False,
        fingerprint_root: Path | None = None,
    ) -> None:
        """Where the folder goes (step 1; the name may be empty, the place's next number in front
        of it when ``numbered``, the SCF folder's ``inherited`` suffix and, with ``use_tag``, the
        plan's site at its end: spec 77): the "Arquivos" tab shows it. ``fingerprint_root``: the
        project's root when "Gerar fingerprint.md" is on, None when it is not (spec 80)."""
        self._naming, self._extra_warnings = (
            (parent, suffix, numbered, inherited, use_tag),
            warnings,
        )
        self._fingerprint_root = fingerprint_root
        self._restart_notes(self._notes_now())
        self._name_target()
        self._show_files()

    def _notes_now(self) -> str:
        """What the notes start with; the table of fingerprint.md lists the SCFs, so not them too."""
        if self._fingerprint_root is not None:
            return ""
        return self.calc_type.default_notes(self.scfs, self._root, self._real)

    def _restart_notes(self, first: str) -> None:
        """The notes start with ``first`` when they still hold what they started with: what the
        user typed stays."""
        if first != self._first_notes and self.notes.toPlainText() == self._first_notes:
            self._first_notes = first
            self.notes.setPlainText(first)

    def _tag(self) -> str:
        """The site the name ends with now (the plan's, when step 1 asked for it)."""
        return self.plan.folder_tag if self._naming is not None and self._naming[4] else ""

    def _name_target(self) -> None:
        """Name the folder again (it lists the place when "Numerar" is on): at ``set_target`` and
        when the site changed."""
        assert self._naming is not None
        parent, suffix, numbered, inherited, _use_tag = self._naming
        tag = self._tag()
        asked, name = preview_names(parent, self.calc_type, suffix, numbered, inherited, tag)
        self._target, self._named_tag = (parent, asked, name), tag

    def fingerprint_sources(self) -> tuple[Source, ...] | None:
        """The SCFs ``fingerprint.md`` lists now; None when step 1 did not ask for the file."""
        if self._fingerprint_root is None:
            return None
        found = sources(self.calc_type, self.scf, self.fields, self.values(), self.scfs)
        return tuple(found)

    def _fingerprint_preview(self, name: str) -> str | None:
        """The file's text as the "Arquivos" tab shows it (now, the name as it would be): its paths
        resolved in a worker, as the writer resolves them; as given until then."""
        found, root = self.fingerprint_sources(), self._fingerprint_root
        if found is None or root is None:
            return None
        self._ask_real([root, *(s.path for s in found)])
        real = self._real
        shown = [Source(source.label, real.get(source.path, source.path)) for source in found]
        return fingerprint_text(
            self.calc_type, name, shown, real.get(root, root), datetime.now(), resolve=False
        )

    def _ask_real(self, paths: list[Path]) -> None:
        missing = {path for path in paths if path not in self._real}
        if missing and not (missing <= self._asked and self._tasks.active("real")):
            self._asked = missing
            self._tasks.submit("real", real_paths, sorted(missing), on_done=self._on_real)

    def _on_real(self, _key: str, found: dict[Path, Path]) -> None:
        self._real.update(found)
        self._restart_notes(self._notes_now())
        self._show_files()

    def _show_files(self) -> None:
        if self._target is None:
            return
        parent, asked, name = self._target
        self.files_view.show_files(
            parent / name,
            asked,
            files_to_write(self.plan, self.notes_text(), self._fingerprint_preview(name)),
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
        self._tasks.shutdown(0)
        for form in self.forms:
            form.shutdown()

    def form_of(self, field_id: str) -> FieldForm:
        return next(form for form in self.forms if field_id in form.widgets)

    def widget_of(self, field_id: str) -> QWidget:
        return self.form_of(field_id).widgets[field_id]
