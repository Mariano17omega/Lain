"""Formatting of the summary values and its plain-text rendering (the "Copiar" button)."""

from __future__ import annotations

import re

from .model import OutputSummary, SummaryRow

_TIME_PART = re.compile(r"(\d+(?:\.\d+)?)\s*([hms])")
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0}


def parse_qe_time(text: str) -> float | None:
    """Seconds of a QE time field: ``1.88s``, ``1h10m``, ``3h 4m``, ``38m32.15s``, ``40m 7.94s``."""
    parts = _TIME_PART.findall(text)
    if not parts:
        return None
    return sum(float(value) * _UNIT_SECONDS[unit] for value, unit in parts)


def format_duration(seconds: float) -> str:
    """``1.90 s`` below a minute, then ``38min 07s`` / ``1h 02min 05s``."""
    if round(seconds, 2) < 60:
        return f"{seconds:.2f} s"
    hours, rest = divmod(round(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}min {secs:02d}s"
    return f"{minutes}min {secs:02d}s"


def duration_text(field: str) -> str:
    """A QE time field as a human duration; the raw text when it has no h/m/s part."""
    seconds = parse_qe_time(field)
    return format_duration(seconds) if seconds is not None else field.strip()


def clock_text(text: str) -> str:
    """``7: 0: 9`` (QE pads with spaces, not zeros) → ``7:00:09``."""
    parts = [piece.strip() for piece in text.split(":")]
    if len(parts) == 3 and all(piece.isdigit() for piece in parts):
        return f"{int(parts[0])}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return text.strip()


def normalize_number(text: str) -> str:
    """Drop the trailing zeros QE pads with, keeping the decimal point and one decimal:
    ``100.0000`` → ``100.0``. Integers and exponent forms are left alone."""
    text = text.strip()
    if "." not in text or any(char in text for char in "eEdD"):
        return text
    head, _, tail = text.partition(".")
    return f"{head}.{tail.rstrip('0') or '0'}"


def _rows(row: SummaryRow, depth: int, out: list[tuple[str, str]]) -> None:
    out.append(("  " * depth + row.label, row.value))
    for child in row.children:
        _rows(child, depth + 1, out)


def to_text(summary: OutputSummary) -> str:
    """One block per section, ``label  value`` aligned, expandable rows indented under their parent."""
    blocks = []
    for section in summary.sections:
        pairs: list[tuple[str, str]] = []
        for row in section.rows:
            _rows(row, 0, pairs)
        width = max((len(label) for label, _ in pairs), default=0)
        body = [f"{label.ljust(width)}  {value}".rstrip() for label, value in pairs]
        blocks.append("\n".join([section.title.upper(), *body]))
    return "\n\n".join(blocks) + "\n"
