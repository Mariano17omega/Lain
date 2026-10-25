"""The ``prefix`` of the pw.x inputs of a folder of the cluster (spec 70 R1): what names the stop file.

pw.x stops at its next check when it finds ``<prefix>.EXIT`` in its working folder (QE 7.1,
``Modules/check_stop.f90``). The cluster mode only knows names, sizes and dates, so the files at the
top of the folder, up to 1 MB each, are copied into a temporary folder of the cache, read and
removed. Inputs are told by their content (PRD §3), never by their name: only pw.x's count, since
it is pw.x that looks for the file.

``fetch_prefixes`` blocks: it runs in a worker.
"""

from __future__ import annotations

import logging
import shlex
import tempfile
from pathlib import Path

from ...i18n import _
from .. import cancel
from ..appdirs import cache_dir
from ..calc_create.scf_info import DEFAULT_PREFIX
from ..config import AppConfig
from ..qe.input_edit import read_input_text, unquote
from ..qe.input_lint import lint
from ..sniff import looks_like_input
from ..sync.command import run_command
from ..sync.rsync import child_env, small_files_command
from .actions import EXTRA_SECONDS, ActionFailure, checked_name, failure_of
from .listing import RSYNC_MISSING, RemoteFailure, classify, local_version

log = logging.getLogger(__name__)


def pw_prefixes(folder: Path) -> tuple[str, ...]:
    """The ``prefix`` of every pw.x input in ``folder`` (``pwscf`` when one sets none), each once,
    in alphabetical order. Workers only."""
    found: set[str] = set()
    for path in sorted(folder.iterdir()):
        cancel.check()
        if not path.is_file() or not looks_like_input(path):
            continue
        doc = lint(read_input_text(path))
        if doc.program != "pw":
            continue
        entry = doc.get("control", "prefix")
        found.add((unquote(entry.value_text).strip() if entry else "") or DEFAULT_PREFIX)
    return tuple(sorted(found))


def fetch_prefixes(
    config: AppConfig, remote_dir: str, password: str | None = None
) -> tuple[str, ...] | ActionFailure:
    """The ``prefix`` of the pw.x inputs of ``remote_dir`` (empty: none), or why it could not be
    read. A ``prefix`` that could not enter a command is a failure. ``password``: the one typed in
    this session (``auth: password``); it reaches ssh through ``SSH_ASKPASS`` only."""
    cluster = config.cluster
    try:
        env = child_env(cluster, password=password)  # writes the askpass helper once
        version = local_version(config.sync.rsync_binary, env)
        if version is None:
            return ActionFailure(RSYNC_MISSING, local=True)
        cache = cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="inputs-", dir=cache) as scratch:
            argv = small_files_command(config, remote_dir, Path(scratch), version)
            log.debug("inputs: %s", shlex.join(argv))
            result = run_command(argv, env, cluster.connect_timeout + EXTRA_SECONDS)
            failure = classify(result, []) if result.timed_out or result.code != 0 else None
            if isinstance(failure, RemoteFailure):
                return failure_of(failure)
            prefixes = pw_prefixes(Path(scratch))
    except OSError as exc:
        message = _("Não foi possível executar o rsync ({error}).").format(error=exc)
        return ActionFailure(message, local=True)
    for prefix in prefixes:
        try:
            checked_name(prefix)
        except ValueError:
            message = _("prefix não suportado para o arquivo de parada: {prefix}.")
            return ActionFailure(message.format(prefix=prefix))
    return prefixes
