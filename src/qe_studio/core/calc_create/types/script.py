"""The ``.qsub`` script every type writes first (spec 25 R6, spec 86): its three fields and its checks.

The cluster side (QE and MPI paths, parallel environment, environment lines, the job's e-mails) is
the cluster's model, fixed in ``qsub/_base.qsub.j2`` and each type's template; the defaults of NP and
the pools and the ``MYEMAIL`` come from the ``jobs:`` section of ``config.yaml``. The form
(``avancado`` mode only) asks for the job name, NP and the pools. The runs read the inputs' names,
chosen or not, from variables at the top of the script (``Work.run``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ....i18n import _
from ...config import JobsConfig
from ...qe.input_edit import InputEditor
from ..render import render
from ..scf_info import ScfInfo
from .base import FormField, PlannedFile, Work

if TYPE_CHECKING:
    from .base import CalcType

__all__ = [
    "JOB_NAME_MAX",
    "MYEMAIL_NOTE",
    "SCRIPT_KEY",
    "gamma_pool_notes",
    "job_name",
    "pool_notes",
    "script_fields",
    "script_file",
]

SCRIPT_KEY = "script"
JOB_NAME_MAX = 15
JOB_DIGIT_PREFIX = "j"
MYEMAIL_NOTE = _("Defina jobs.myemail no config.yaml para receber os e-mails do job")
_JOB_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def job_name(name: str) -> str:
    """What ``#$ -N`` gets: letters, digits, ``.``, ``_``, ``-``, at most 15 characters, and no digit
    first (qsub refuses it: "is not a valid object name")."""
    safe = _JOB_UNSAFE.sub("_", name.strip())
    if safe[:1].isdigit():
        safe = JOB_DIGIT_PREFIX + safe
    return safe[:JOB_NAME_MAX] or "lain"


def script_fields(type_: CalcType, scf: ScfInfo, jobs: JobsConfig) -> list[FormField]:
    group = SCRIPT_KEY
    return [
        FormField(
            "job_name",
            _("Nome do job"),
            "text",
            job_name(scf.prefix),
            group=group,
            tooltip=_("#$ -N: nome exibido no scheduler (até 15 caracteres, sem espaços)"),
        ),
        FormField(
            "np",
            _("Núcleos (NP)"),
            "int",
            jobs.cores,
            group=group,
            tooltip=_("#$ -pe: número de núcleos do job"),
        ),
        FormField(
            "nk",
            "Pools (nk)",
            "int",
            jobs.nk,
            group=group,
            tooltip=_("pw.x -nk: número de pools (grupos de k-points); NP deve ser múltiplo de nk"),
        ),
    ]


def pool_notes(np_: int, nk: int) -> list[str]:
    """Warnings of NP and nk; they never block (spec R6.2), though pw.x stops on them
    (``mp_start_pools``)."""
    if np_ < 1:
        return [_("NP deve ser ao menos 1")]
    if nk < 1:
        return [_("nk deve ser ao menos 1")]
    if nk > np_:
        return [
            _("nk = {nk} é maior que NP = {np}: o pw.x para com erro (mp_start_pools)").format(
                nk=nk, np=np_
            )
        ]
    if np_ % nk:
        return [
            _(
                "NP = {np} não é múltiplo de nk = {nk}: o pw.x para com erro (mp_start_pools)"
            ).format(np=np_, nk=nk)
        ]
    return []


def gamma_pool_notes(files: Sequence[PlannedFile], nk: int) -> list[str]:
    """The pw.x inputs with ``K_POINTS gamma`` (a missing card is gamma too) while ``-nk`` is above 1:
    pw.x stops with "Gamma-only calculations not allowed with pools" (``QE:PW/src/setup.f90:683``,
    L-07). The generated texts only: an edit by hand does not redo the notes."""
    if nk <= 1:
        return []
    names = []
    for planned in files:
        if planned.kind != "pw_input":
            continue
        card = InputEditor.from_text(planned.text).card("K_POINTS")
        if card is None or card.option == "gamma":
            names.append(planned.name)
    if not names:
        return []
    return [
        _(
            "{names}: K_POINTS gamma (ou sem o card) com nk = {nk}: o pw.x para (Gamma-only calculations not allowed with pools). Use nk = 1 (campo Pools, no modo avançado) ou uma rede de k-points"
        ).format(names=", ".join(names), nk=nk)
    ]


def script_file(type_: CalcType, work: Work, jobs: JobsConfig) -> PlannedFile:
    values = work.values
    typed = str(values["job_name"] or "")
    name = job_name(typed)
    if typed.strip() and name != typed.strip():
        work.notes.append(
            _(
                "Nome do job ajustado para {name} (até 15 caracteres: letras, números, . _ -; não começa com número)"
            ).format(name=name)
        )
    np_ = values["np"] if values["np"] is not None else jobs.cores
    nk = values["nk"] if values["nk"] is not None else jobs.nk
    work.notes.extend(pool_notes(np_, nk))
    if not jobs.myemail:
        work.notes.append(MYEMAIL_NOTE)
    runs = type_.script_values(work)  # fills ``work.script_inputs``
    text = render(
        type_.script_template,
        {
            "job_name": name,
            "np": np_,
            "nk": nk,
            "myemail": jobs.myemail or "",
            "inputs": work.script_inputs,
            **runs,
        },
    )
    script = type_.script_name
    return PlannedFile(
        script, "qsub", text, _("Script ({script})").format(script=script), SCRIPT_KEY
    )
