"""Whether a simulation folder holds the trace of a failed run (spec 50 R2).

A ``CRASH`` file (pw.x writes it only when it stops on an error) or a job stdout log
(``job.o12345``) that is not empty. One ``scandir`` of the folder itself, no file is opened; it
runs in the detection worker, never while painting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .file_kinds import is_job_stdout

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


def run_error(folder: Path) -> RunError | None:
    """The error ``folder`` shows, or None. ``CRASH`` (any size) wins over a job log; of several
    logs the first by name that has content. Subfolders and ``job.e<id>`` do not count."""
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
        if _has_content(entry):
            return RunError("job_log", entry.name)
    return None


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
