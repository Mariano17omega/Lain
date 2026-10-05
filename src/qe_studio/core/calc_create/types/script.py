"""The ``.qsub`` script every type writes first (spec 25 R6): its three fields and its checks.

The cluster side (QE and MPI paths, parallel environment, environment lines) comes from the
``jobs:`` section of ``config.yaml``, as do the defaults of NP and the pools; the form (``avancado``
mode only) asks for the job name, NP and the pools. The runs are the inputs' names, chosen or not.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...config import JobsConfig
from ..render import render
from ..scf_info import ScfInfo
from .base import FormField, PlannedFile, Work

if TYPE_CHECKING:
    from .base import CalcType

__all__ = ["JOB_NAME_MAX", "SCRIPT_KEY", "job_name", "pool_notes", "script_fields", "script_file"]

SCRIPT_KEY = "script"
JOB_NAME_MAX = 15
_JOB_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def job_name(name: str) -> str:
    """What ``#$ -N`` gets: letters, digits, ``.``, ``_``, ``-``, at most 15 characters."""
    return _JOB_UNSAFE.sub("_", name.strip())[:JOB_NAME_MAX] or "lain"


def script_fields(type_: CalcType, scf: ScfInfo, jobs: JobsConfig) -> list[FormField]:
    group = SCRIPT_KEY
    return [
        FormField(
            "job_name",
            "Nome do job",
            "text",
            job_name(scf.prefix),
            group=group,
            tooltip="#$ -N: nome exibido no scheduler (até 15 caracteres, sem espaços)",
        ),
        FormField(
            "np",
            "Núcleos (NP)",
            "int",
            jobs.cores,
            group=group,
            tooltip="#$ -pe: número de núcleos do job",
        ),
        FormField(
            "nk",
            "Pools (nk)",
            "int",
            jobs.nk,
            group=group,
            tooltip="pw.x -nk: número de pools (grupos de k-points); NP deve ser múltiplo de nk",
        ),
    ]


def pool_notes(np_: int, nk: int) -> list[str]:
    """Warnings of NP and nk; they never block (spec R6.2), though pw.x stops on them
    (``mp_start_pools``)."""
    if np_ < 1:
        return ["NP deve ser ao menos 1"]
    if nk < 1:
        return ["nk deve ser ao menos 1"]
    if nk > np_:
        return [f"nk = {nk} é maior que NP = {np_}: o pw.x para com erro (mp_start_pools)"]
    if np_ % nk:
        return [f"NP = {np_} não é múltiplo de nk = {nk}: o pw.x para com erro (mp_start_pools)"]
    return []


def script_file(type_: CalcType, work: Work, jobs: JobsConfig) -> PlannedFile:
    values = work.values
    typed = str(values["job_name"] or "")
    name = job_name(typed)
    if typed.strip() and name != typed.strip():
        work.notes.append(
            f"Nome do job ajustado para {name} (até 15 caracteres: letras, números, . _ -)"
        )
    np_ = values["np"] if values["np"] is not None else jobs.cores
    nk = values["nk"] if values["nk"] is not None else jobs.nk
    work.notes.extend(pool_notes(np_, nk))
    text = render(
        type_.script_template,
        {
            "job_name": name,
            "np": np_,
            "nk": nk,
            "qe_bin": jobs.qe_bin,
            "mpi_command": jobs.mpi_command,
            "parallel_env": jobs.parallel_env,
            "omp_threads": jobs.omp_threads,
            "env_lines": list(jobs.env_lines),
            **type_.script_values(work),
        },
    )
    script = type_.script_name
    return PlannedFile(script, "qsub", text, f"Script ({script})", SCRIPT_KEY)
