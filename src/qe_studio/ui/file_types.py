"""How files look in the explorer, file grid and workspace: icon and colors.

What a file *is* (how it opens, the state it reports) is ``core/file_kinds.py``.
"""

from __future__ import annotations

from pathlib import Path

from ..core.file_kinds import IMAGE_SUFFIXES, is_job_log
from ..core.qe import projwfc

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
# Theme color of each level of ``core.file_kinds.status_label`` (and of banners).
LEVEL_TOKENS = {"success": "success", "warning": "warning", "error": "error"}


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


# The visual types of the grid's filter (``core.filtering.VISUALS``) by icon color token.
_VISUAL_CATEGORIES = {
    "icon_input": "inputs",
    "icon_output": "saídas",
    "icon_data": "dados",
    "icon_image": "imagens",
    "icon_vector": "imagens",  # svg, eps, pdf: figures too
}


def visual_category(path: Path) -> str:
    """``inputs``, ``saídas``, ``dados``, ``imagens`` or ``outros``: what a file looks like."""
    _icon, token = file_visual(path)
    return _VISUAL_CATEGORIES.get(token, "outros")


def level_token(level: str) -> str:
    return LEVEL_TOKENS.get(level, "text_dim")
