"""The contract of a calculation type of "Criar cálculo" (spec 25 R3).

A type declares the form fields the window shows (``fields``) and builds the files of the new folder
from the SCF and the values typed (``plan``). The window knows no type: it lists ``REGISTRY``, draws
the ``FormField``s and shows the ``PlannedFile``s, one tab each, in order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ...config import JobsConfig
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..kpath import KMesh, KPath
from ..scf_info import ScfInfo

__all__ = [
    "CalcPlan",
    "CalcType",
    "FieldKind",
    "FileKind",
    "FormField",
    "PlannedFile",
    "Work",
    "field_problems",
    "is_empty",
    "resolve",
]

FieldKind = Literal["int", "float", "text", "choice", "bool", "kpath", "kmesh"]
FileKind = Literal["pw_input", "qe_input", "qsub", "notes"]


@dataclass(frozen=True)
class FormField:
    id: str
    label: str
    kind: FieldKind
    default: Any = None  # from the SCF when it has the value, else the type's; None: no default
    required: bool = False  # with no value and no default, "Criar" stays disabled
    group: str = ""  # the ``PlannedFile.name`` whose tab shows the field
    tooltip: str = ""
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedFile:
    name: str  # in the new folder
    kind: FileKind
    text: str
    tab_label: str


@dataclass(frozen=True)
class CalcPlan:
    files: tuple[PlannedFile, ...]
    notes: tuple[str, ...] = ()  # warnings: shown, never block
    errors: tuple[str, ...] = ()  # what keeps "Criar" disabled

    @property
    def ok(self) -> bool:
        return not self.errors

    def file(self, name: str) -> PlannedFile | None:
        return next((planned for planned in self.files if planned.name == name), None)


def is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce(form_field: FormField, value: Any) -> Any:
    """``value`` as the field's kind holds it; raises ValueError (texts from a line edit are fine)."""
    kind = form_field.kind
    if kind == "int":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            return value
        number = fortran_float(str(value))
        if number is None or number != int(number):
            raise ValueError
        return int(number)
    if kind == "float":
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        number = fortran_float(str(value))
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
            problem = f"Valor inválido em {form_field.label}: {value}"
            value = None
    if is_empty(value):
        value = None
        if form_field.required and problem is None:
            problem = f"Preencha {form_field.label}"
    return value, problem


def resolve(
    fields: Sequence[FormField], values: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Each field's value (an empty one → its default) and the errors: invalid values and
    required fields with neither."""
    resolved: dict[str, Any] = {}
    errors: list[str] = []
    for form_field in fields:
        resolved[form_field.id], problem = _resolve_one(form_field, values.get(form_field.id))
        if problem is not None:
            errors.append(problem)
    return resolved, errors


def field_problems(fields: Sequence[FormField], values: Mapping[str, Any]) -> dict[str, str]:
    """The problem of each field that has one, by field id (the window marks those fields)."""
    problems = {}
    for form_field in fields:
        _value, problem = _resolve_one(form_field, values.get(form_field.id))
        if problem is not None:
            problems[form_field.id] = problem
    return problems


@dataclass
class Work:
    """What ``plan`` builds up: the SCF, the resolved values, notes and errors."""

    scf: ScfInfo
    values: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def editor(self) -> InputEditor:
        """A fresh editor on the SCF's text."""
        return InputEditor.from_text(self.scf.text)

    def finish(self, editor: InputEditor, name: str) -> str:
        """The edited text; the editor's failures become errors of ``name``."""
        self.errors.extend(f"{name}: {issue}" for issue in editor.issues)
        return editor.text()


class CalcType:
    """One kind of calculation the window creates. Subclasses fill the ClassVars and
    ``input_fields`` / ``inputs``; the script (always the first file) is common."""

    id: ClassVar[str]
    label: ClassVar[str]  # in the type dropdown
    folder_prefix: ClassVar[str]  # the new folder is <folder_prefix>_<suffix>
    script_template: ClassVar[str]  # under templates/
    input_templates: ClassVar[tuple[str, ...]] = ()  # the other templates it renders
    default_nk: ClassVar[int] = 8

    @property
    def script_name(self) -> str:
        return f"{self.folder_prefix}.qsub"

    def fields(self, scf: ScfInfo, jobs: JobsConfig) -> list[FormField]:
        from .script import script_fields

        return [*script_fields(self, scf, jobs), *self.input_fields(scf)]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        raise NotImplementedError

    def inputs(self, work: Work) -> list[PlannedFile]:
        """The files after the script, in tab order."""
        raise NotImplementedError

    def script_values(self, work: Work) -> dict[str, Any]:
        """Template variables of the script besides the common ones."""
        return {}

    def plan(self, scf: ScfInfo, values: Mapping[str, Any], jobs: JobsConfig) -> CalcPlan:
        """The files of the new folder for ``values`` (the window's fields; empty → default).
        Never raises and reads no file: the window calls it on every edit."""
        from ..render import TemplateFailure
        from .script import script_file

        resolved, errors = resolve(self.fields(scf, jobs), values)
        work = Work(scf, resolved, list(scf.warnings), errors)
        files: list[PlannedFile] = []
        try:
            files.append(script_file(self, work, jobs))
            files.extend(self.inputs(work))
        except TemplateFailure as exc:
            work.errors.append(str(exc))
        notes = list(dict.fromkeys(work.notes))
        return CalcPlan(tuple(files), tuple(notes), tuple(dict.fromkeys(work.errors)))
