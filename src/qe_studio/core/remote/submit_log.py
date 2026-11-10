"""The jobs Lain submitted (spec 71 R3): one line per job in ``<data_dir>/submitted_jobs.log``.

The cluster gives no link between a job that still waits and the folder it was submitted from (its
``<name>.o<id>`` comes when it starts), but Lain knows it for the jobs it submitted itself. So each
job ``qsub`` accepted is written here, a table that reads in any text editor: a ``#`` header, then
tab-separated fields (date in UTC, ``user@host``, job-ID, job name, folder, script). A job of this
folder still in the queue, matched by ID **and** name (SGE reuses IDs), blocks a new submission.

The file is written whole (``atomic_write_text``); Lain runs once per user (spec 27-3), so two
writers never race. A line that cannot be read is skipped. A file that does not exist has no jobs,
but one that exists and cannot be read stops the checks that rely on it (``log_for_check``): a job
still waiting in the queue would go unseen. Everything here touches the disk: it runs in a worker.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ...i18n import _
from ..appdirs import atomic_write_text, data_dir
from .failure import RemoteFailure

log = logging.getLogger(__name__)

LOG_NAME = "submitted_jobs.log"
FIELDS = ("date_utc", "account", "job_id", "name", "remote_dir", "script")
HEADER = "# " + "\t".join(FIELDS)


@dataclass(frozen=True)
class Logged:
    date_utc: str  # 2026-10-26T14:03:12Z
    account: str  # user@host
    job_id: str
    name: str
    remote_dir: str
    script: str


def log_path() -> Path:
    return data_dir() / LOG_NAME


def _parse(text: str) -> list[Logged]:
    entries = []
    for line in text.splitlines():
        fields = line.split("\t")
        if line.startswith("#") or len(fields) != len(FIELDS) or not all(fields):
            continue
        entries.append(Logged(*fields))
    return entries


def read_log(path: Path | None = None) -> list[Logged]:
    """The jobs of the log, oldest first; none when it does not exist. ``OSError`` when it exists
    and cannot be read."""
    path = path or log_path()
    try:
        return _parse(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        return []


def log_for_check(outcome: str) -> list[Logged] | RemoteFailure:
    """The jobs of the log, for a check that may not go on without them; a failure when it cannot
    be read. ``outcome``: the sentence that ends its message ("Nada foi submetido.")."""
    try:
        return read_log()
    except OSError as exc:
        log.warning("file: cannot read the log of submitted jobs: %s", exc)
        message = _("Não foi possível ler o registro de jobs submetidos ({error}). {outcome}")
        return RemoteFailure(message.format(error=exc, outcome=outcome), local=True)


def line_of(entry: Logged) -> str:
    """``entry`` as one line of the table; ``ValueError`` when a field would break it."""
    fields = [getattr(entry, field) for field in FIELDS]
    if any(not value or "\t" in value or "\n" in value or "\r" in value for value in fields):
        message = _("o job {job_id} tem um campo vazio ou com tabulação ou quebra de linha")
        raise ValueError(message.format(job_id=entry.job_id))
    return "\t".join(fields)


def record(
    account: str, job_id: str, name: str, remote_dir: str, script: str, path: Path | None = None
) -> Logged:
    """Add a job ``qsub`` accepted to the log (made when missing). ``OSError`` or ``ValueError``
    when it cannot be written: the job was submitted all the same."""
    path = path or log_path()
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = Logged(when, account, job_id, name, remote_dir, script)
    line = line_of(entry)
    try:
        old = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        old = ""
    head = "" if old.startswith(HEADER) else HEADER + "\n"
    body = old if not old or old.endswith("\n") else old + "\n"
    atomic_write_text(path, head + body + line + "\n")
    return entry


def logged_here(entries: list[Logged], account: str, remote_dir: str) -> set[tuple[str, str]]:
    """``(job-ID, name)`` of the jobs of ``entries`` submitted by ``account`` from ``remote_dir``."""
    folder = remote_dir.rstrip("/")
    return {
        (entry.job_id, entry.name)
        for entry in entries
        if entry.account == account and entry.remote_dir.rstrip("/") == folder
    }


def logged_under(entries: list[Logged], account: str, remote_dir: str) -> list[Logged]:
    """The jobs of ``entries`` submitted by ``account`` from ``remote_dir`` or a folder below it (a
    folder moved to the trash takes them along, spec 84)."""
    folder = PurePosixPath(remote_dir)
    return [
        entry
        for entry in entries
        if entry.account == account and PurePosixPath(entry.remote_dir).is_relative_to(folder)
    ]
