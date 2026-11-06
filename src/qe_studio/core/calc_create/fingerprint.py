"""``fingerprint.md``: where a new calculation came from (spec 80).

Written next to the inputs when step 1's "Gerar fingerprint.md" is on: a title and a two-column table
with the type, the folder, the time, the Lain version and one row per SCF the calculation was made
from. A path inside the project's ``local_root`` is shown relative to it, any other one absolute.
The text is in the interface's language, like ``geracao.md``. Qt-free; ``shown_path`` resolves
links, so the writer (a worker) calls it with the disk, and the "Arquivos" preview without, on the
paths ``real_paths`` resolved in a worker: both write the same text.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ... import __version__
from ...i18n import _
from ..files.paths import real_path
from .scf_info import ScfInfo
from .types.base import CalcType, FormField

__all__ = [
    "FINGERPRINT_NAME",
    "Source",
    "fingerprint_text",
    "real_paths",
    "shown_path",
    "sources",
]

FINGERPRINT_NAME = "fingerprint.md"
TITLE = _("# Fingerprint do cálculo")
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class Source:
    """One SCF the calculation came from: what it is for (step 1's label, a field's label) and where."""

    label: str
    path: Path


def sources(
    calc_type: CalcType,
    scf: ScfInfo,
    fields: Sequence[FormField],
    values: Mapping[str, Any],
    scfs: Sequence[ScfInfo] = (),
) -> list[Source]:
    """The SCFs of the calculation, in the order the window shows them. A ``multi_scf`` type lists
    its ``scfs`` ("SCF 1", "SCF 2"…) and nothing else; any other, the base SCF (with step 1's label
    for it) and every SCF a form field picked (the molecule, the "outro SCF"). An SCF without a
    path is left out."""
    if calc_type.multi_scf:
        return [
            Source(_("SCF {n}").format(n=n), info.path)
            for n, info in enumerate(scfs, 1)
            if info.path is not None
        ]
    found = [Source(calc_type.scf_label, scf.path)] if scf.path is not None else []
    for form_field in fields:
        value = values.get(form_field.id)
        if form_field.kind == "scf_file" and isinstance(value, ScfInfo) and value.path is not None:
            found.append(Source(form_field.label, value.path))
    return found


def shown_path(path: Path, root: Path, resolve: bool = True) -> str:
    """``proj/0_Relax/scf.in`` when ``path`` is inside ``root``, else its absolute path (``/`` as
    the separator in the relative one). ``resolve=False`` only normalizes the text, no disk: for the
    GUI thread, on paths ``real_paths`` already followed the links of."""
    if resolve:
        full, base = real_path(path), real_path(root)
    else:
        full, base = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    if full.is_relative_to(base):
        return full.relative_to(base).as_posix()
    return str(full)


def real_paths(paths: Iterable[Path]) -> dict[Path, Path]:
    """Each of ``paths`` with its links followed, as ``shown_path`` resolves it, keyed by the path
    as given. Touches the disk: a worker."""
    return {path: real_path(path) for path in paths}


def _cell(text: str) -> str:
    """Plain text in a table cell: a ``|`` would end the cell."""
    return text.replace("|", "\\|")


def _code(text: str) -> str:
    """``text`` as inline code that survives a ``|`` (a table cell) and a backtick in it."""
    text = _cell(text)
    fence = "``" if "`" in text else "`"
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def fingerprint_text(
    calc_type: CalcType,
    folder_name: str,
    found: Sequence[Source],
    root: Path,
    created: datetime,
    *,
    resolve: bool = True,
) -> str:
    """The Markdown of ``fingerprint.md``; ``created`` is local time."""
    rows = [
        (_("Tipo de cálculo"), f"{calc_type.label} ({_code(calc_type.id)})"),
        (_("Pasta"), _code(folder_name)),
        (_("Criado em"), created.strftime(_TIME_FORMAT)),
        (_("Lain"), __version__),
        *((source.label, _code(shown_path(source.path, root, resolve))) for source in found),
    ]
    # Outside the f-string: Python 3.11 does not tokenize inside one, so xgettext would miss them.
    field, value = _("Campo"), _("Valor")
    table = [f"| {field} | {value} |", "|---|---|"]
    table += [f"| {_cell(label)} | {value} |" for label, value in rows]
    return "\n".join([TITLE, "", *table]) + "\n"
