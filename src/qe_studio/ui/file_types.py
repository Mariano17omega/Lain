"""How files look and open in the explorer, file grid and workspace."""

from __future__ import annotations

import re
from pathlib import Path

from ..core.qe import projwfc
from ..core.sniff import FileSniff

TEXT_SUFFIXES = {
    ".in", ".inp", ".out", ".log", ".txt", ".dat", ".gnu", ".md", ".yaml", ".yml", ".json",
    ".xml", ".csv", ".py", ".sh", ".qsub", ".slurm", ".pbs", ".rap", ".xmgr", ".cif", ".xsf",
    ".pwi", ".pwo", ".dos", ".upf", ".plot",
}  # fmt: skip
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
SVG_SUFFIXES = {".svg"}
# Queue logs: PBS/Torque/SGE stdout `job.o12345` and stderr `job.e12345`, job arrays `.o12345.1`.
JOB_LOG = re.compile(r"^.+\.[oe]\d+(?:[.-]\d+)?$", re.IGNORECASE)

_VISUALS = [
    (IMAGE_SUFFIXES, ("image", "icon_image")),
    ({".svg", ".eps", ".ps"}, ("polyline", "icon_vector")),
    ({".pdf"}, ("picture_as_pdf", "icon_vector")),
    ({".in", ".inp", ".pwi"}, ("description", "icon_input")),
    ({".out", ".log", ".pwo"}, ("terminal", "icon_output")),
    ({".gnu", ".dat", ".csv", ".xmgr", ".dos", ".rap"}, ("analytics", "icon_data")),
    ({".yaml", ".yml", ".json", ".xml"}, ("data_object", "icon_other")),
    ({".py", ".sh", ".qsub", ".slurm", ".pbs", ".ipynb"}, ("code", "icon_other")),
    ({".plot"}, ("tune", "icon_other")),  # saved plot settings
]


def is_job_log(path: Path) -> bool:
    return JOB_LOG.match(path.name) is not None


def file_visual(path: Path, is_dir: bool = False) -> tuple[str, str]:
    """(Material Symbol name, color token) for a file or folder."""
    if is_dir:
        return "folder", "icon_folder"
    name = path.name
    if projwfc.parse_atm_name(name) or projwfc.is_pdos_tot_name(name):
        return "bar_chart", "icon_data"
    if is_job_log(path):
        return "assignment_late", "icon_output"
    suffix = path.suffix.lower()
    for suffixes, visual in _VISUALS:
        if suffix in suffixes:
            return visual
    return "draft", "icon_other"


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
    return "external"


def status_label(path: Path, size: int, sniff: FileSniff | None) -> tuple[str, str] | None:
    """(label, colour token) for a file's state, or None. Paint path: never reads the file.

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
