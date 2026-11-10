"""Whether a job's stdout log (``job.o12345``) holds nothing but the job's machines (spec 85).

The cluster's scripts run ``cat "$PE_HOSTFILE"``, so the log of a job that went well has one line
per machine instead of being empty. A log is clean when every line has the format of a hostfile
and, when the folder's ``.qsub`` tells the cores of the job, there are as many lines as machines.
Without that script only the format is checked: an error that cannot be measured is not reported.

It reads the folder's scripts: worker only, through ``core/sniff.py``, which keeps the verdict. This
module imports neither ``core/sniff.py`` nor ``core/files/file_kinds.py``: they import it.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from .job_script import job_name, pe_slots

# The stdout half of a queue log: PBS/Torque/SGE ``job.o12345``, job arrays ``job.o12345.1``.
JOB_STDOUT = re.compile(r"^(?P<name>.+)\.o\d+(?:[.-]\d+)?$", re.IGNORECASE)
CORES_PER_MACHINE = 32  # a fact of the cluster, like the QE paths of the templates (decision 4)

SCRIPT_SUFFIX = ".qsub"
# ``ther02 32 physica.q@ther02 UNDEFINED``: the machine's name varies, the ``@`` of the third column
# stays. An ``@`` anywhere else does not count: an error message can have one too.
_HOST_LINE = re.compile(r"^\S+\s+\d+\s+\S+@\S+\s+\S+$")


def machines_of(cores: int) -> int:
    """How many machines a job of ``cores`` takes: rounded up (16 → 1, 48 → 2, decision 6)."""
    return math.ceil(cores / CORES_PER_MACHINE)


def host_lines(text: str) -> int | None:
    """How many lines ``text`` has when all of its non-empty ones are hostfile lines; else None,
    also when there is no such line (a log of only blanks stays an error)."""
    lines = [stripped for line in text.splitlines() if (stripped := line.strip())]
    if not lines or not all(_HOST_LINE.match(line) for line in lines):
        return None
    return len(lines)


def job_cores(folder: Path, name: str) -> int | None:
    """The slots of the ``.qsub`` of ``folder`` (not its subfolders) whose job is ``name``. None
    when no script is that job's, the script has no ``-pe``, two of them disagree, or on OSError."""
    slots: set[int | None] = set()
    try:
        for script in folder.iterdir():
            if script.suffix.lower() == SCRIPT_SUFFIX and script.is_file():
                text = script.read_text(encoding="utf-8", errors="replace")
                if job_name(text, script.name) == name:
                    slots.add(pe_slots(text))
    except OSError:
        return None
    return slots.pop() if len(slots) == 1 else None


def clean_job_log(path: Path, text: str) -> bool:
    """Does the job log ``path``, whose whole text is ``text``, only list the job's machines? A
    ``.e<id>`` never does. The scripts are read last, only for a log that looks like a hostfile."""
    match = JOB_STDOUT.match(path.name)
    if match is None:
        return False
    lines = host_lines(text)
    if lines is None:
        return False
    cores = job_cores(path.parent, match["name"])
    return cores is None or lines == machines_of(cores)
