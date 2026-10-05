"""The input files of a type and their names (spec 28 R1.3, R4.2).

Every input has a stable key (what ``FormField.group`` and ``PlannedFile.key`` name) and a standard
name: ``<calculation>_<prefix>.in`` for the pw.x runs that follow the pattern (``scf_Al.in``,
``relax_Al.in``…), plain names for the rest (``bands.in``, ``bands_pp.in``, ``projwfc.in``). In the
``avancado`` mode each name is a field of its tab ("Nome do arquivo"); the output is the same name
with ``.out``, and the script runs the names chosen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..scf_info import ScfInfo
from .base import FormField, Work

__all__ = [
    "NAME_LABEL",
    "InputFile",
    "check_names",
    "name_field",
    "name_field_id",
    "output_name",
    "pw_input",
    "unit_stem",
]

NAME_LABEL = "Nome do arquivo"
INPUT_SUFFIX = ".in"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_NAME = re.compile(r"[A-Za-z0-9._-]+")


@dataclass(frozen=True)
class InputFile:
    key: str
    name: str  # the standard name
    label: str = ""  # the tab is "<label> (<name>)", or the name alone

    def tab_label(self, name: str) -> str:
        return f"{self.label} ({name})" if self.label else name


def unit_stem(prefix: str) -> str:
    """The SCF's ``prefix`` as part of a file name (characters outside ``[A-Za-z0-9._-]`` → ``_``)."""
    return _UNSAFE.sub("_", prefix.strip()) or "pwscf"


def pw_input(key: str, calculation: str, scf: ScfInfo, label: str) -> InputFile:
    """A pw.x input of the pattern: ``<calculation>_<prefix>.in``."""
    return InputFile(key, f"{calculation}_{unit_stem(scf.prefix)}{INPUT_SUFFIX}", label)


def name_field_id(key: str) -> str:
    return f"name:{key}"


def name_field(input_file: InputFile) -> FormField:
    return FormField(
        name_field_id(input_file.key),
        NAME_LABEL,
        "text",
        input_file.name,
        group=input_file.key,
        tooltip="Nome do input na pasta nova (termina em .in); a saída tem o mesmo nome com .out",
    )


def output_name(name: str) -> str:
    """``scf_Al.in`` → ``scf_Al.out``."""
    return name.removesuffix(INPUT_SUFFIX) + ".out"


def _problem(name: str) -> str | None:
    if not name.endswith(INPUT_SUFFIX) or name == INPUT_SUFFIX:
        return f"Nome de arquivo inválido: {name} (use <nome>.in)"
    if not _NAME.fullmatch(name):
        return (
            f"Nome de arquivo inválido: {name} "
            "(só letras sem acento, números, ponto, hífen e sublinhado)"
        )
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
        name = work.values.get(field_id) or input_file.name
        work.names[key] = name
        problem = _problem(name)
        if problem is None and name in owners:
            problem = f"Nome de arquivo repetido: {name}"
            if owners[name]:
                problems.setdefault(owners[name], problem)
        owners.setdefault(name, field_id)
        if problem is not None:
            problems[field_id] = problem
            work.errors.append(problem)
    return problems
