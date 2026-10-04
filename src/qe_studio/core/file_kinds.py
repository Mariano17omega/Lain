"""What a file is for the viewers and file panels: how it opens and the state it reports.

``viewer_kind`` may read a file's head (a NUL byte means binary); ``status_label`` never reads:
it runs while the file grid and the explorer paint.
"""

from __future__ import annotations

import re
from pathlib import Path

from .qe import projwfc
from .sniff import FileSniff, looks_like_input

TEXT_SUFFIXES = {
    ".in", ".inp", ".out", ".log", ".txt", ".dat", ".gnu", ".md", ".yaml", ".yml", ".json",
    ".xml", ".csv", ".py", ".sh", ".qsub", ".slurm", ".pbs", ".rap", ".xmgr", ".cif", ".xsf",
    ".pwi", ".pwo", ".dos", ".upf", ".plot",
}  # fmt: skip
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
SVG_SUFFIXES = {".svg"}
# Queue logs: PBS/Torque/SGE stdout `job.o12345` and stderr `job.e12345`, job arrays `.o12345.1`.
JOB_LOG = re.compile(r"^.+\.[oe]\d+(?:[.-]\d+)?$", re.IGNORECASE)


def is_job_log(path: Path) -> bool:
    return JOB_LOG.match(path.name) is not None


def viewer_kind(path: Path) -> str:
    """``text``, ``image``, ``svg`` or ``external`` (opened by the desktop)."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in SVG_SUFFIXES:
        return "svg"
    if (
        suffix in TEXT_SUFFIXES
        or is_job_log(path)
        or projwfc.parse_atm_name(path.name)
        or path.name.endswith("pdos_tot")
    ):
        return "text"
    if suffix == "":
        try:
            with open(path, "rb") as handle:
                return "external" if b"\x00" in handle.read(4096) else "text"
        except OSError:
            return "external"
    # An input with a suffix of its own (``si.pw``) is still text: its head says so (spec 11 R4.1).
    return "text" if looks_like_input(path) else "external"


def status_label(path: Path, size: int, sniff: FileSniff | None) -> tuple[str, str] | None:
    """(label, level) for a file's state, or None; the level is ``success``, ``warning`` or
    ``error``. Paint path: never reads the file.

    QE outputs report whether the run finished; queue logs are "SEM ERROS" when empty and "ERRO"
    otherwise, unless they hold a redirected QE output (then the QE label wins).
    """
    if sniff is not None and sniff.is_output and sniff.job_done is not None:
        if not sniff.job_done:
            return "INCOMPLETO", "warning"
        return ("AVISO", "warning") if sniff.warnings else ("OK", "success")
    if is_job_log(path):
        return ("ERRO", "error") if size > 0 else ("SEM ERROS", "success")
    return None


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
