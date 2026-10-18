"""Whether a simulation folder holds the trace of a failed run (spec 50 R2).

A ``CRASH`` file (pw.x writes it only when it stops on an error) or a job stdout log
(``job.o12345``) that is not empty, unless the log is a QE output that finished (``JOB DONE``: a run
without ``> scf.out`` prints there, and its row in the grid reads OK, not ERRO). One ``scandir`` of
the folder itself; only a log with content is sniffed, through the caller's cache. It runs in the
detection worker, never while painting.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .file_kinds import is_job_stdout
from .sniff import FileSniff

CRASH_NAME = "CRASH"


@dataclass(frozen=True)
class RunError:
    kind: Literal["crash", "job_log"]
    name: str  # the file that caused it

    @property
    def tooltip(self) -> str:
        if self.kind == "crash":
            return f"Erro de simulação: arquivo {self.name}"
        return f"Erro de simulação: {self.name} não está vazio"


def run_error(folder: Path, sniff: Callable[[Path], FileSniff] | None = None) -> RunError | None:
    """The error ``folder`` shows, or None. ``CRASH`` (any size) wins over a job log; of several
    logs the first by name that has content and, when ``sniff`` is given, is not a finished QE
    output. Subfolders and ``job.e<id>`` do not count."""
    logs: list[os.DirEntry[str]] = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name == CRASH_NAME:
                    if _is_regular(entry):
                        return RunError("crash", CRASH_NAME)
                elif is_job_stdout(Path(entry.name)):
                    logs.append(entry)
    except OSError:
        return None
    for entry in sorted(logs, key=lambda e: e.name):
        if _has_content(entry) and not (sniff is not None and _finished(sniff(Path(entry.path)))):
            return RunError("job_log", entry.name)
    return None


def _finished(sniff: FileSniff) -> bool:
    """A QE output with ``JOB DONE``: what ``file_kinds.status_label`` shows as OK or AVISO."""
    return sniff.is_output and sniff.job_done is True


def _is_regular(entry: os.DirEntry[str]) -> bool:
    try:
        return entry.is_file(follow_symlinks=False)
    except OSError:
        return False


def _has_content(entry: os.DirEntry[str]) -> bool:
    try:
        return entry.is_file() and entry.stat().st_size > 0
    except OSError:
        return False
