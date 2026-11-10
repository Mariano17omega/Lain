"""The contract of a calculation type of "Criar cálculo" (spec 25 R3, spec 28 R3).

A type declares its input files (``input_files``: a stable key and the standard name of each) and the
form fields the window shows (``fields``), and builds the files of the new folder from the SCF and the
values typed (``plan``). The window knows no type: it lists ``REGISTRY``, draws the ``FormField``s that
``shown_fields`` keeps for its mode and values and shows the ``PlannedFile``s, one tab each, in order.

Modes (spec 28): in ``padrao`` only the fields marked ``standard`` (and a required one without a
default) are shown, and every other field takes its default whatever the window holds; ``avancado``
shows them all, plus the name of each input file. A field with ``shown_when`` (spec 87) also needs the
values of other fields, and takes its default just the same while they hide it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from ....i18n import _
from ...config import JobsConfig
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float, fortran_int
from ..kpath import KMesh, KPath
from ..scf_info import ScfInfo
from ..unit import apply_unit

if TYPE_CHECKING:
    from .files import InputFile

__all__ = [
    "DEFAULT_MODE",
    "MODES",
    "CalcPlan",
    "CalcType",
    "FieldKind",
    "FileKind",
    "FormField",
    "Mode",
    "PlannedFile",
    "Work",
    "field_problems",
    "is_empty",
    "is_visible",
    "resolve",
    "shown_fields",
    "visible_fields",
]

FieldKind = Literal[
    "int", "float", "text", "choice", "atom_choice", "bool", "kpath", "kmesh", "atoms", "scf_file"
]
FileKind = Literal["pw_input", "qe_input", "qsub", "notes", "report"]
Mode = Literal["padrao", "avancado"]
MODES: tuple[Mode, ...] = ("padrao", "avancado")
DEFAULT_MODE: Mode = "padrao"  # the window's on its first opening (spec 28 R5.2)


@dataclass(frozen=True)
class FormField:
    id: str
    label: str
    kind: FieldKind
    default: Any = None  # from the SCF when it has the value, else the type's; None: no default
    required: bool = False  # with no value and no default, "Criar" stays disabled
    group: str = ""  # the ``PlannedFile.key`` whose tab shows the field
    tooltip: str = ""
    choices: tuple[str, ...] = ()
    standard: bool = False  # shown in the ``padrao`` mode too (spec 28 R3.1)
    hint: str = ""  # a short legend the window shows with the field (``atoms``)
    # What a kind needs to be drawn (``atoms``: the ``AtomRows`` to pick from; ``atom_choice``: the
    # options, each with a ``text`` shown as it is and a ``value``).
    data: Any = None
    depends_on: tuple[
        str, ...
    ] = ()  # fields whose values change ``data`` (``CalcType.field_data``)
    # (field id, the values it may hold): shown only when all of them hold (spec 87 R3).
    shown_when: tuple[tuple[str, tuple[str, ...]], ...] = ()


def is_visible(form_field: FormField, mode: Mode) -> bool:
    """Whether the window shows the field in ``mode``: a required field without a default is
    always shown, as nothing else could fill it."""
    return (
        form_field.standard
        or mode == "avancado"
        or (form_field.required and form_field.default is None)
    )


def visible_fields(fields: Sequence[FormField], mode: Mode) -> list[FormField]:
    return [form_field for form_field in fields if is_visible(form_field, mode)]


def shown_fields(
    fields: Sequence[FormField], mode: Mode, values: Mapping[str, Any]
) -> list[FormField]:
    """The ``visible_fields`` of ``mode`` whose ``shown_when`` hold, read from the values resolved: a
    field the mode hides, or an empty one, counts as its default."""
    visible = visible_fields(fields, mode)
    asked = {key for form_field in visible for key, __ in form_field.shown_when}
    if not asked:
        return visible
    ids = {form_field.id for form_field in visible}
    typed = {key: value for key, value in values.items() if key in ids}
    resolved, __ = _resolve_all([f for f in fields if f.id in asked], typed)
    return [
        form_field
        for form_field in visible
        if all(resolved.get(key) in accepted for key, accepted in form_field.shown_when)
    ]


@dataclass(frozen=True)
class PlannedFile:
    name: str  # in the new folder
    kind: FileKind
    text: str
    tab_label: str
    key: str = ""  # stable within the type (the name can be edited): what ``FormField.group`` names
    source: str | None = None  # what the preview compares it with (None: step 1's SCF; spec 79)


@dataclass(frozen=True)
class CalcPlan:
    files: tuple[PlannedFile, ...]
    notes: tuple[str, ...] = ()  # warnings: shown, never block
    errors: tuple[str, ...] = ()  # what keeps "Criar" disabled, ``text_errors`` included
    problems: Mapping[str, str] = field(default_factory=dict)  # field id → its problem (marked)
    folder_tag: str = ""  # the end of the folder's name the plan offers (spec 77: the site)
    # The errors read from the texts of ``files`` (``CalcType.text_errors``): an edit by hand
    # changes them (``core/calc_create/overrides.py``), while the fields' errors stay.
    text_errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def file(self, name: str) -> PlannedFile | None:
        return next((planned for planned in self.files if planned.name == name), None)

    def by_key(self, key: str) -> PlannedFile | None:
        return next((planned for planned in self.files if planned.key == key), None)


def is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _point(text: str) -> str:
    """``text`` with a typed decimal comma read as a point (CLAUDE.md, Numbers)."""
    return text.strip().replace(",", ".")


def _coerce(form_field: FormField, value: Any) -> Any:
    """``value`` as the field's kind holds it; raises ValueError (texts from a line edit are fine)."""
    kind = form_field.kind
    if kind == "int":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            return value
        number = fortran_int(_point(str(value)))
        if number is None:
            raise ValueError
        return number
    if kind == "float":
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        number = fortran_float(_point(str(value)))
        if number is None:
            raise ValueError
        return number
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError
        return value
    if kind == "choice":
        text = str(value).strip()
        if form_field.choices and text not in form_field.choices:
            raise ValueError
        return text
    if kind == "kmesh":
        mesh = value if isinstance(value, KMesh) else KMesh.parse(str(value))
        if mesh is None:
            raise ValueError
        return mesh
    if kind == "kpath":
        if not isinstance(value, KPath):
            raise ValueError
        return value
    if kind == "atoms":
        # The picked atoms (1-based): empty is a value, whose problem the type says (``split_input``).
        if isinstance(value, str | bytes) or not isinstance(value, Iterable):
            raise ValueError
        if any(isinstance(n, bool) or not isinstance(n, int) for n in value):
            raise ValueError
        return tuple(sorted(set(value)))
    if kind == "scf_file":
        # Another SCF, read by the window in a worker (spec 40 R1.1): the ``ScfInfo`` itself.
        if not isinstance(value, ScfInfo):
            raise ValueError
        return value
    return str(value).strip()


def _resolve_one(form_field: FormField, value: Any) -> tuple[Any, str | None]:
    """The field's value (an empty one → its default) and its problem, if any."""
    if is_empty(value):
        value = form_field.default
    problem = None
    if not is_empty(value):
        try:
            value = _coerce(form_field, value)
        except (TypeError, ValueError):
            problem = _("Valor inválido em {label}: {value}").format(
                label=form_field.label, value=value
            )
            value = None
    if is_empty(value):
        value = None
        if form_field.required and problem is None:
            problem = _("Preencha {label}").format(label=form_field.label)
    return value, problem


def _resolve_all(
    fields: Sequence[FormField], values: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    resolved: dict[str, Any] = {}
    problems: dict[str, str] = {}
    for form_field in fields:
        resolved[form_field.id], problem = _resolve_one(form_field, values.get(form_field.id))
        if problem is not None:
            problems[form_field.id] = problem
    return resolved, problems


def resolve(
    fields: Sequence[FormField], values: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Each field's value (an empty one → its default) and the errors: invalid values and
    required fields with neither."""
    resolved, problems = _resolve_all(fields, values)
    return resolved, list(problems.values())


def field_problems(fields: Sequence[FormField], values: Mapping[str, Any]) -> dict[str, str]:
    """The problem of each field that has one, by field id (the window marks those fields)."""
    return _resolve_all(fields, values)[1]


@dataclass
class Work:
    """What ``plan`` builds up: the SCF, the resolved values, the file names, notes and errors."""

    scf: ScfInfo
    values: dict[str, Any]
    jobs: JobsConfig
    inputs: dict[str, InputFile] = field(default_factory=dict)  # by key
    names: dict[str, str] = field(default_factory=dict)  # key → the name in the folder
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)  # field id → its problem (marked)
    folder_tag: str = ""  # ``CalcPlan.folder_tag``
    scfs: tuple[ScfInfo, ...] = ()  # step 1's list, for a ``multi_scf`` type (spec 79)
    # What the script declares, in the order ``run`` was called: (variable, input's name), spec 86.
    script_inputs: list[tuple[str, str]] = field(default_factory=list)

    def problem(self, field_id: str, text: str) -> None:
        """An error the window marks on the field ``field_id`` (it blocks "Criar" like any error)."""
        self.problems.setdefault(field_id, text)
        self.errors.append(text)

    def editor(self, scf: ScfInfo | None = None) -> InputEditor:
        """A fresh editor on the text of ``scf`` (default: the SCF), already a unit's (``outdir``,
        ``pseudo_dir``)."""
        editor = InputEditor.from_text((scf or self.scf).text)
        apply_unit(editor, self.jobs)
        return editor

    def finish(self, editor: InputEditor, name: str) -> str:
        """The edited text; the editor's failures become errors of ``name``."""
        self.errors.extend(f"{name}: {issue}" for issue in editor.issues)
        return editor.text()

    def name(self, key: str) -> str:
        return self.names[key]

    def run(self, key: str) -> tuple[str, str]:
        """The script's references to the input of ``key`` and to its output (``.in`` → ``.out``).
        The name goes into a variable of the script (``script_inputs``), as in the cluster's model:
        ``QE_INPUTFILE`` for the first run, ``QE_INPUTFILE_<KEY>`` for the others (spec 86 R3)."""
        variable = "QE_INPUTFILE"
        if self.script_inputs:
            variable += "_" + key.upper().replace("-", "_")
        self.script_inputs.append((variable, self.names[key]))
        return f"${{{variable}}}", f"${{{variable}%.in}}.out"

    def planned(self, key: str, kind: FileKind, text: str) -> PlannedFile:
        name = self.names[key]
        return PlannedFile(name, kind, text, self.inputs[key].tab_label(name), key)

    def pw_file(self, key: str, editor: InputEditor, source: str | None = None) -> PlannedFile:
        """A pw.x input made by ``editor``; ``source``: the text it derives from, when not the SCF."""
        planned = self.planned(key, "pw_input", self.finish(editor, self.names[key]))
        return planned if source is None else dataclasses.replace(planned, source=source)


class CalcType:
    """One kind of calculation the window creates. Subclasses fill the ClassVars and
    ``input_files`` / ``input_fields`` / ``inputs``; the script (always the first file) is common."""

    id: ClassVar[str]
    label: ClassVar[str]  # in the type dropdown
    folder_prefix: ClassVar[str]  # the new folder is <folder_prefix>_<suffix>, or <folder_prefix>
    script_stem: ClassVar[str]  # the script is <script_stem>.qsub
    script_template: ClassVar[str]  # under templates/
    input_templates: ClassVar[tuple[str, ...]] = ()  # the other templates it renders
    uses_name: ClassVar[bool] = False  # a standard file name takes the folder's name (spec 29)
    scf_label: ClassVar[str] = _("Input de SCF")  # what step 1 calls the SCF (spec 40 R1.4)
    writes_report: ClassVar[bool] = False  # ``geracao.md`` after the inputs (spec 40 R1.5)
    site_tag: ClassVar[bool] = (
        False  # the plan's ``folder_tag`` can end the folder's name (spec 77)
    )
    multi_scf: ClassVar[bool] = False  # step 1 picks a list of SCFs, two or more (spec 79)

    @property
    def script_name(self) -> str:
        return f"{self.script_stem}.qsub"

    def fields(
        self, scf: ScfInfo, jobs: JobsConfig, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[FormField]:
        """The script's fields, the name of each input (first in its tab) and the type's own."""
        from .files import name_field
        from .script import script_fields

        names = [name_field(input_file) for input_file in self.input_files(scf, name, scfs)]
        return [*script_fields(self, scf, jobs), *names, *self.input_fields(scf)]

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        """The inputs after the script, in tab order, with their standard names (spec 28 R1.3).
        ``name`` is the folder's name, which only a type with ``uses_name`` reads; ``scfs`` the
        list of step 1, which only a ``multi_scf`` type reads (spec 79)."""
        raise NotImplementedError

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        raise NotImplementedError

    def inputs(self, work: Work) -> list[PlannedFile]:
        """The files after the script, in tab order (``work.names`` holds their names)."""
        raise NotImplementedError

    def check_scf(self, scf: ScfInfo) -> str | None:
        """Why step 1 refuses ``scf`` for this type (None: it does not), e.g. a bulk's SCF for a type
        that puts a molecule on a surface (spec 42 R1)."""
        return None

    def field_data(self, field_id: str, scf: ScfInfo, values: Mapping[str, Any]) -> Any:
        """The ``data`` of field ``field_id`` for the window's ``values`` (those of the fields shown):
        asked again when a field of its ``depends_on`` changes (spec 42 R2.4)."""
        return next((f.data for f in self.input_fields(scf) if f.id == field_id), None)

    def script_values(self, work: Work) -> dict[str, Any]:
        """Template variables of the script besides the common ones: the runs, by name."""
        return {}

    def text_errors(self, files: Sequence[PlannedFile]) -> list[str]:
        """What keeps "Criar" disabled in the texts of ``files`` as they will be written, an edit by
        hand included (none for most types; spec 79: two SCFs that would share their data)."""
        return []

    def default_notes(
        self,
        scfs: tuple[ScfInfo, ...],
        root: Path | None = None,
        real: Mapping[Path, Path] | None = None,
    ) -> str:
        """What the "Descrição" tab starts with ("" for most types; spec 79: where the SCFs came
        from, a path inside ``root`` relative to it). ``real``: paths with their links followed
        (``fingerprint.real_paths``, in a worker: this reads no disk); the others stay as given."""
        return ""

    def plan(
        self,
        scf: ScfInfo,
        values: Mapping[str, Any],
        jobs: JobsConfig,
        mode: Mode = DEFAULT_MODE,
        name: str = "",
        scfs: tuple[ScfInfo, ...] = (),
    ) -> CalcPlan:
        """The files of the new folder for ``values`` (the window's fields; empty → default). A field
        the mode or a ``shown_when`` hides takes its default, whatever ``values`` holds. ``name`` is
        the folder's name typed in step 1 (may be empty); ``scfs`` its list of SCFs, for a
        ``multi_scf`` type (``scf`` is the first). Never raises and reads no file: the window calls
        it on every edit."""
        from ..render import TemplateFailure
        from ..unit import unit_notes
        from .files import check_names
        from .script import gamma_pool_notes, script_file

        fields = self.fields(scf, jobs, name, scfs)
        shown = {form_field.id for form_field in shown_fields(fields, mode, values)}
        resolved, problems = _resolve_all(
            fields, {key: value for key, value in values.items() if key in shown}
        )
        inputs = {input_file.key: input_file for input_file in self.input_files(scf, name, scfs)}
        work = Work(scf, resolved, jobs, inputs, notes=unit_notes(scf, jobs), scfs=scfs)
        work.errors.extend(problems.values())
        problems.update(check_names(work, self.script_name))
        files: list[PlannedFile] = []
        try:
            files.append(script_file(self, work, jobs))
            files.extend(self.inputs(work))
            nk = work.values.get("nk")
            work.notes.extend(gamma_pool_notes(files, jobs.nk if nk is None else nk))
        except TemplateFailure as exc:
            work.errors.append(str(exc))
        for field_id, text in work.problems.items():
            problems.setdefault(field_id, text)
        notes = list(dict.fromkeys(work.notes))
        text_errors = tuple(dict.fromkeys(self.text_errors(files)))
        return CalcPlan(
            tuple(files),
            tuple(notes),
            tuple(dict.fromkeys([*work.errors, *text_errors])),
            problems,
            work.folder_tag,
            text_errors,
        )
