"""Result types of the output summary (spec 12 R1): what the summary tab shows and "Copiar" copies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Level = Literal["success", "warning", "error"]


@dataclass(frozen=True)
class SummaryRow:
    label: str
    value: str
    level: Level | None = None  # colors the value
    line: int | None = None  # 1-based line of the output the value comes from
    children: tuple[SummaryRow, ...] = ()  # expandable sub-rows (stress, pseudopotentials…)


@dataclass(frozen=True)
class SummarySection:
    title: str  # sentence case; the UI uppercases it like the panel headers
    rows: tuple[SummaryRow, ...]


@dataclass(frozen=True)
class SummaryIssue:
    level: Level  # "error" for a %%%% block, "warning" for "Message from routine"
    routine: str
    message: str
    line: int | None = None
    count: int = 1  # identical repetitions folded into this one


@dataclass(frozen=True)
class OutputSummary:
    program: str | None  # PWSCF, BANDS, PROJWFC… (None when the file has no "Program" line)
    sections: tuple[SummarySection, ...] = ()
    issues: tuple[SummaryIssue, ...] = field(default_factory=tuple)
