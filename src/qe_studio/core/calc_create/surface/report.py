"""``geracao.md``: what a surface type did, written next to its input (spec 40 R1.5).

The user's scripts write a ``.md`` beside every ``.in``; the folder gets one ``geracao.md`` with a title
and one ``- **label**: value`` line per fact. Numbers take a decimal point and atoms are counted from
1, as QE and VESTA do. It is no input: no "Nome do arquivo" field, no ``.in`` rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ....i18n import _

if TYPE_CHECKING:
    from ..types.base import PlannedFile

__all__ = ["REPORT_KEY", "REPORT_NAME", "decimal", "report_file", "report_text"]

REPORT_NAME = "geracao.md"
REPORT_KEY = "report"
TITLE = _("# Relatório da geração")
TAB_LABEL = _("Relatório ({REPORT_NAME})").format(REPORT_NAME=REPORT_NAME)


def decimal(value: float, digits: int = 2) -> str:
    """``15.098`` → ``15.10``: a decimal point, as QE writes numbers."""
    return f"{value:.{digits}f}"


def report_text(lines: Sequence[tuple[str, str]]) -> str:
    return "\n".join([TITLE, "", *(f"- **{label}**: {value}" for label, value in lines)]) + "\n"


def report_file(lines: Sequence[tuple[str, str]]) -> PlannedFile:
    from ..types.base import PlannedFile  # the types import this module: no cycle at import time

    return PlannedFile(REPORT_NAME, "report", report_text(lines), TAB_LABEL, REPORT_KEY)
