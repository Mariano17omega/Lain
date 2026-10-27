"""Small files of a folder of the cluster, read here: the ``prefix`` that names the stop file (spec 70
R1, spec 71 R2) and the job name of a script (spec 71 R3).

pw.x stops at its next check when it finds ``<prefix>.EXIT`` in its working folder (QE 7.1,
``Modules/check_stop.f90``). The cluster's administrator asks for the ``prefix`` of the SCF, relax and
vc-relax inputs: one file per ``prefix`` of those inputs, never the ``prefix`` of an nscf or bands run.
The cluster mode only knows names, sizes and dates, so the files at the top of the folder, up to 1 MB
each, are copied into a temporary folder of the cache, read and removed. Inputs are told by their
content (PRD §3), never by their name: only pw.x's count, since it is pw.x that looks for the file.

rsync's codes 23 and 24 (a file that could not be read, or that vanished while it was copied) are
normal in a folder where pw.x runs: what arrived is read, and the copy fails only when what was needed
did not arrive (spec 71 R1).

Everything here blocks: it runs in a worker.
"""

from __future__ import annotations

import logging
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ...i18n import _
from .. import cancel
from ..appdirs import cache_dir
from ..calc_create.scf_info import DEFAULT_PREFIX
from ..config import AppConfig
from ..qe.input_edit import read_input_text, unquote
from ..qe.input_lint import InputDoc, lint
from ..qsub_lint import job_name
from ..sniff import looks_like_input
from ..sync.command import CommandResult, run_command
from ..sync.rsync import child_env, small_files_command
from .actions import EXTRA_SECONDS, ActionFailure, checked_name, failure_of
from .listing import PARTIAL, RSYNC_MISSING, VANISHED, RemoteFailure, classify, local_version

log = logging.getLogger(__name__)

STOP_CALCULATIONS = ("scf", "relax", "vc-relax")  # the cluster administrator's rule (spec 71 R2)
SCRATCH_PREFIX = "inputs-"  # the temporary folders of the cache


@dataclass(frozen=True)
class StopSource:
    prefix: str
    inputs: tuple[str, ...]  # the names of the inputs that set it


def _calculation(doc: InputDoc) -> str:
    """``calculation`` of a pw.x input, lowercased; ``scf`` when it sets none, as pw.x does."""
    entry = doc.get("control", "calculation")
    return (unquote(entry.value_text).strip() if entry else "").lower() or "scf"


def stop_sources(folder: Path) -> tuple[StopSource, ...]:
    """The ``prefix`` of every SCF, relax or vc-relax input of pw.x in ``folder`` (``pwscf`` when one
    sets none), each once with the inputs that set it, in alphabetical order. Workers only."""
    found: dict[str, list[str]] = {}
    for path in sorted(folder.iterdir()):
        cancel.check()
        if not path.is_file() or not looks_like_input(path):
            continue
        doc = lint(read_input_text(path))
        if doc.program != "pw" or _calculation(doc) not in STOP_CALCULATIONS:
            continue
        entry = doc.get("control", "prefix")
        prefix = (unquote(entry.value_text).strip() if entry else "") or DEFAULT_PREFIX
        found.setdefault(prefix, []).append(path.name)
    return tuple(StopSource(prefix, tuple(found[prefix])) for prefix in sorted(found))


def copy_small_files(
    config: AppConfig,
    remote_dir: str,
    scratch: Path,
    password: str | None = None,
    only: str | None = None,
) -> CommandResult | ActionFailure:
    """Copy the files at the top of ``remote_dir``, up to 1 MB each (``only``: just that one), into
    ``scratch``; rsync's answer, or why it could not run. ``password``: the one typed in this session
    (``auth: password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        version = local_version(config.sync.rsync_binary, env)
        if version is None:
            return ActionFailure(RSYNC_MISSING, local=True)
        argv = small_files_command(config, remote_dir, scratch, version, only)
        log.debug("small files: %s", shlex.join(argv))
        return run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
    except OSError as exc:
        return _not_run(exc)


def _not_run(exc: OSError) -> ActionFailure:
    message = _("Não foi possível executar o rsync ({error}).").format(error=exc)
    return ActionFailure(message, local=True)


def _unusable(result: CommandResult, found: bool) -> ActionFailure | None:
    """Why the copy of ``result`` cannot be used; None when it can: a whole copy, or a partial one
    (codes 23 and 24) that brought what was needed (``found``)."""
    whole = result.code == 0
    if not result.timed_out and (whole or (result.code in (PARTIAL, VANISHED) and found)):
        if not whole:
            log.warning("small files: rsync ended with code %s, what arrived is read", result.code)
        return None
    failure = classify(result, [])
    assert isinstance(failure, RemoteFailure)  # a whole copy was handled above
    return failure_of(failure)


def _scratch() -> tempfile.TemporaryDirectory[str]:
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX, dir=cache)


def fetch_stop_sources(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> tuple[StopSource, ...] | ActionFailure:
    """The stop sources of ``remote_dir`` (empty: none), or why they could not be read. A ``prefix``
    that could not enter a command is a failure."""
    try:
        with _scratch() as scratch:
            result = copy_small_files(config, remote_dir, Path(scratch), password)
            if isinstance(result, ActionFailure):
                return result
            sources = () if result.timed_out else stop_sources(Path(scratch))
    except OSError as exc:
        return _not_run(exc)
    failure = _unusable(result, bool(sources))
    if failure is not None:
        return failure
    for source in sources:
        try:
            checked_name(source.prefix)
        except ValueError:
            message = _("prefix não suportado para o arquivo de parada: {prefix}.")
            return ActionFailure(message.format(prefix=source.prefix))
    return sources


def fetch_job_name(
    config: AppConfig, remote_dir: str, script: str, password: str | None = None
) -> str | ActionFailure:
    """The name SGE gives the job of ``script`` in ``remote_dir`` (its ``#$ -N``, else its file name),
    read from a copy of the script; why it could not be read otherwise. ``script`` has passed
    ``checked_name``."""
    try:
        with _scratch() as scratch:
            result = copy_small_files(config, remote_dir, Path(scratch), password, only=script)
            if isinstance(result, ActionFailure):
                return result
            copied = Path(scratch) / script
            arrived = not result.timed_out and copied.is_file()
            text = read_input_text(copied) if arrived else None
    except OSError as exc:
        return _not_run(exc)
    failure = _unusable(result, text is not None)
    if failure is not None:
        return failure
    if text is None:
        message = _("O script {script} não foi encontrado na pasta, ou passa de 1 MB.")
        return ActionFailure(message.format(script=script))
    return job_name(text, script)
