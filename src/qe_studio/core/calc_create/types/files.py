"""The input files of a type and their names (spec 28 R1.3, R4.2).

Every input has a stable key (what ``FormField.group`` and ``PlannedFile.key`` name) and a standard
name: ``<calculation>_<prefix>.in`` for the pw.x runs that follow the pattern (``scf_Al.in``,
``relax_Al.in``…), plain names for the rest (``bands.in``, ``bands_pp.in``, ``projwfc.in``). In the
``avancado`` mode each name is a field of its tab ("Nome do arquivo"); the output is the same name
with ``.out``, and the script runs the names chosen.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ....i18n import _
from ..scf_info import ScfInfo
from .base import FormField, Work

__all__ = [
    "NAME_LABEL",
    "InputFile",
    "check_names",
    "name_field",
    "name_field_id",
    "named_input",
    "pw_input",
    "unit_stem",
]

NAME_LABEL = _("Nome do arquivo")
INPUT_SUFFIX = ".in"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_NAME = re.compile(r"[A-Za-z0-9._-]+")


@dataclass(frozen=True)
class InputFile:
    key: str
    name: str  # the standard name (with ``named_by``: the one of the choice's default)
    label: str = ""  # the tab is "<label> (<name>)", or the name alone
    # The id of the choice field whose value is the ``<calculation>`` of the name (spec 95 R2), and
    # the rest of it: the name is then ``<value>_<stem>.in``.
    named_by: str = ""
    stem: str = ""

    def tab_label(self, name: str) -> str:
        return f"{self.label} ({name})" if self.label else name

    def standard(self, values: Mapping[str, Any]) -> str:
        """The standard name for the values resolved: ``<value of named_by>_<stem>.in``, else ``name``."""
        value = values.get(self.named_by) if self.named_by else None
        return f"{value}_{self.stem}{INPUT_SUFFIX}" if value else self.name


def unit_stem(prefix: str) -> str:
    """The SCF's ``prefix`` as part of a file name (characters outside ``[A-Za-z0-9._-]`` → ``_``)."""
    return _UNSAFE.sub("_", prefix.strip()) or "pwscf"


def pw_input(key: str, calculation: str, scf: ScfInfo, label: str, named_by: str = "") -> InputFile:
    """A pw.x input of the pattern: ``<calculation>_<prefix>.in``; with ``named_by``, the
    ``<calculation>`` is the value of that choice field (``calculation`` is its default)."""
    stem = unit_stem(scf.prefix)
    return InputFile(key, f"{calculation}_{stem}{INPUT_SUFFIX}", label, named_by, stem)


def name_field_id(key: str) -> str:
    return f"name:{key}"


def name_field(input_file: InputFile, defaults: Mapping[str, Any] | None = None) -> FormField:
    """The "Nome do arquivo" of an input. One named by a choice starts empty: its standard name
    (the ``data``, which the placeholder shows) follows the choice (spec 95 R2.2)."""
    tooltip = _("Nome do input na pasta nova (termina em .in); a saída tem o mesmo nome com .out")
    field_id = name_field_id(input_file.key)
    if input_file.named_by:
        return FormField(
            field_id,
            NAME_LABEL,
            "text",
            None,
            group=input_file.key,
            tooltip=tooltip,
            data=input_file.standard(defaults or {}),
            depends_on=(input_file.named_by,),
        )
    return FormField(
        field_id, NAME_LABEL, "text", input_file.name, group=input_file.key, tooltip=tooltip
    )


def named_input(inputs: list[InputFile], field_id: str) -> InputFile | None:
    """The input named by a choice whose "Nome do arquivo" is ``field_id``, or None."""
    return next(
        (f for f in inputs if f.named_by and name_field_id(f.key) == field_id),
        None,
    )


def _problem(name: str) -> str | None:
    if not name.endswith(INPUT_SUFFIX) or name == INPUT_SUFFIX:
        return _("Nome de arquivo inválido: {name} (use <nome>.in)").format(name=name)
    if not _NAME.fullmatch(name):
        return _(
            "Nome de arquivo inválido: {name} (só letras sem acento, números, ponto, hífen e sublinhado)"
        ).format(name=name)
    return None


def check_names(work: Work, script_name: str) -> dict[str, str]:
    """Fill ``work.names`` (the name typed, or the standard one) and return the problems by field
    id: a name must end in ``.in``, use ``[A-Za-z0-9._-]`` only and be unique in the folder (both
    fields of a repeated name are marked). A bad name is still used (the preview shows it); the
    problem blocks "Criar"."""
    problems: dict[str, str] = {}
    owners: dict[str, str] = {script_name: ""}  # name → the field that took it first
    for key, input_file in work.inputs.items():
        field_id = name_field_id(key)
        name = work.values.get(field_id) or input_file.standard(work.values)
        work.names[key] = name
        problem = _problem(name)
        if problem is None and name in owners:
            problem = _("Nome de arquivo repetido: {name}").format(name=name)
            if owners[name]:
                problems.setdefault(owners[name], problem)
        owners.setdefault(name, field_id)
        if problem is not None:
            problems[field_id] = problem
            work.errors.append(problem)
    return problems
