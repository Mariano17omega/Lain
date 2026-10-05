"""Summary of a QE output file (spec 12): state, time, parallelization, system, results, messages.

``summarize(path)`` streams the file once, whatever its size. ``pw.x`` outputs also go through
``parse_relax`` in that same pass (relax and vc-relax outputs can be hundreds of MB), and the Fermi /
HOMO-LUMO values come from the ``PwOutput`` the sniff cache already holds.

``parse_scf`` (spec 9) is not used: it describes the first SCF cycle only, and a relax output needs
the last one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from ... import cancel
from ...sniff import sniff
from ..pw_output import PwOutput
from ..relax import parse_relax
from .build import RELAX_CALCULATIONS, build_summary
from .model import Level, OutputSummary, SummaryIssue, SummaryRow, SummarySection
from .scan import Scanner
from .text import to_text

__all__ = [
    "Level",
    "OutputSummary",
    "SummaryIssue",
    "SummaryRow",
    "SummarySection",
    "summarize",
    "summarize_lines",
    "to_text",
]


def _observe(lines: Iterable[str], scanner: Scanner) -> Iterator[str]:
    """Pass the lines through, letting the scanner see each one (so a second parser can share
    the read)."""
    for number, line in enumerate(lines, 1):
        if number % cancel.CHECK_EVERY_LINES == 0:
            cancel.check()
        scanner.feed(number, line)
        yield line


def summarize_lines(lines: Iterable[str], pw: PwOutput | None = None) -> OutputSummary:
    """``pw``: the parsed pw.x output when known; without it there are no Fermi / HOMO-LUMO values,
    no calculation type and no relax steps."""
    scanner = Scanner()
    stream = _observe(lines, scanner)
    relax = None
    if pw is not None and pw.calculation in RELAX_CALCULATIONS:
        relax = parse_relax(stream)
    else:
        for _ in stream:
            pass
    return build_summary(scanner.finish(), pw, relax)


def summarize(path: Path) -> OutputSummary:
    """Raises ``OSError`` when the file cannot be read."""
    pw = sniff(path).pw
    with open(path, encoding="utf-8", errors="replace") as handle:
        return summarize_lines(handle, pw)
