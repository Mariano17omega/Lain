"""The ``.qsub`` script every type writes first (spec 25 R6, spec 86): its three fields and its checks.

The cluster side (QE and MPI paths, parallel environment, environment lines, the job's e-mails) is
the cluster's model, fixed in ``qsub/_base.qsub.j2`` and each type's template; the default of NP and the
``MYEMAIL`` come from the ``jobs:`` section of ``config.yaml``. The pools are computed from NP and the
k-points of the inputs (``pools.py``, spec 102) unless typed. The form (``avancado`` mode only) asks
for the job name, NP and the pools. The runs read the inputs' names, chosen or not, from variables at
the top of the script (``Work.run``).
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
from .pools import MAX_POOLS, POOL_STEP, Pools, auto_pools, planned_kpoints

if TYPE_CHECKING:
    from .base import CalcType

__all__ = [
    "JOB_NAME_MAX",
    "MYEMAIL_NOTE",
    "SCRIPT_KEY",
    "choose_pools",
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
            None,
            group=group,
            auto=True,
            hint=_("vazio = automático"),
            tooltip=_(
                "pw.x -nk: número de pools (grupos de k-points). Vazio: o Lain escolhe pelo NP e pelos "
                "k-points (múltiplo de 4, até 16, dividindo o NP). NP deve ser múltiplo de nk"
            ),
        ),
    ]


def choose_pools(work: Work, inputs: Sequence[PlannedFile], jobs: JobsConfig) -> Pools:
    """The script's NP and nk: the nk typed, or (an empty field) the one ``auto_pools`` picks for the
    k-points of the pw.x ``inputs`` (spec 102)."""
    values = work.values
    np_ = values["np"] if values["np"] is not None else jobs.cores
    nks = planned_kpoints(inputs)
    if values["nk"] is None:
        return Pools(np_, auto_pools(np_, nks), True, nks)
    return Pools(np_, values["nk"], False, nks)


def pool_notes(np_: int, nk: int, nks: int | None = None) -> list[str]:
    """Warnings of NP and nk; they never block (spec R6.2), though pw.x stops on the first two
    (``mp_start_pools``). ``nks``: the k-points estimated (``pools.kpoint_count``)."""
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
    notes = []
    if nk > 1 and (nk % POOL_STEP or nk > MAX_POOLS):
        notes.append(
            _("O cluster pede nk múltiplo de {step} e no máximo {max} (nk = {nk})").format(
                step=POOL_STEP, max=MAX_POOLS, nk=nk
            )
        )
    if nks is not None and nk > nks:
        notes.append(
            _(
                "nk = {nk} é maior que os cerca de {nks} k-points do input: {idle} pools ficam sem k-point e os núcleos deles ficam ociosos"
            ).format(nk=nk, nks=nks, idle=nk - nks)
        )
    return notes


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


def script_file(type_: CalcType, work: Work, jobs: JobsConfig, pools: Pools) -> PlannedFile:
    values = work.values
    typed = str(values["job_name"] or "")
    name = job_name(typed)
    if typed.strip() and name != typed.strip():
        work.notes.append(
            _(
                "Nome do job ajustado para {name} (até 15 caracteres: letras, números, . _ -; não começa com número)"
            ).format(name=name)
        )
    work.notes.extend(pool_notes(pools.np, pools.nk, pools.nks))
    if not jobs.myemail:
        work.notes.append(MYEMAIL_NOTE)
    runs = type_.script_values(work)  # fills ``work.script_inputs``
    text = render(
        type_.script_template,
        {
            "job_name": name,
            "np": pools.np,
            "nk": pools.nk,
            "myemail": jobs.myemail or "",
            "inputs": work.script_inputs,
            **runs,
        },
    )
    script = type_.script_name
    return PlannedFile(
        script, "qsub", text, _("Script ({script})").format(script=script), SCRIPT_KEY
    )
