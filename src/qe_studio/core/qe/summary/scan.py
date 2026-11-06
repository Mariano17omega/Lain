"""One-pass line scanner of a QE output: raw facts with their line numbers (spec 12 R1).

Outputs of relax runs can be hundreds of MB, so the file is never held in memory: ``Scanner.feed``
sees each line once. A cheap ``needle in line`` test comes before every regex (most lines match
nothing, and the regexes are the slow part), like in ``relax.py``.

Values are kept as the regex groups, text as QE printed it; ``build.py`` turns them into rows.
"Last wins" for quantities that repeat (energy, force, pressure…), "first" for the ones that
describe the start (header, initial energy and volume).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from ..relax import NUMBER
from ..structure import SITE
from .model import Level, SummaryIssue

Keep = Literal["first", "last", "both", "all"]


class Hit(NamedTuple):
    groups: tuple[str | None, ...]
    line: int  # 1-based


@dataclass(frozen=True)
class _Rule:
    key: str
    needle: str
    pattern: re.Pattern[str]
    keep: Keep = "first"


def _rule(key: str, needle: str, pattern: str, keep: Keep = "first") -> _Rule:
    return _Rule(key, needle, re.compile(pattern), keep)


_RULES: tuple[_Rule, ...] = (
    # -- general ------------------------------------------------------------------------------
    _rule(
        "program",
        "Program ",
        r"^\s*Program\s+([A-Z0-9_.]+)\s+v\.\s*(\S+)(?:.*?\bstarts on\s+(\S+)\s+at\s+(.+?))?\s*$",
    ),
    _rule("ended", "terminated on", r"terminated on:\s+(\d+:\s*\d+:\s*\d+)\s+(\S+)", "last"),
    _rule("job_done", "JOB DONE", r"JOB DONE"),
    _rule("time", "WALL", r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*(.+?)\s+CPU\s+(.+?)\s+WALL\s*$", "last"),
    _rule("serial", "Serial version", r"Serial version"),
    _rule(
        "parallel", "Parallel version", r"Parallel version \((.+?)\),\s*running on\s+(\d+)\s+proc"
    ),
    _rule("mpi", "Number of MPI processes", r"Number of MPI processes:\s*(\d+)"),
    _rule("threads", "Threads/MPI process", r"Threads/MPI process:\s*(\d+)"),
    _rule("nodes", "MPI processes distributed on", r"MPI processes distributed on\s+(\d+)\s+node"),
    _rule("npool", "K-points division", r"K-points division:\s*npool\s*=\s*(\d+)"),
    _rule(
        "rg_division",
        "R & G space division",
        r"R & G space division:\s*proc/nbgrp/npool/nimage\s*=\s*(.+?)\s*$",
    ),
    _rule("gpu", "GPU acceleration is ACTIVE", r"GPU acceleration is ACTIVE"),
    _rule("memory", "MiB available memory", r"(\d+)\s+MiB available memory", "last"),
    _rule(
        "ram_process",
        "Estimated max dynamical RAM per process",
        r"Estimated max dynamical RAM per process\s*>\s*(\S+\s*\S+)",
        "last",
    ),
    _rule(
        "ram_total",
        "Estimated total dynamical RAM",
        r"Estimated total dynamical RAM\s*>\s*(\S+\s*\S+)",
        "last",
    ),
    _rule("written", "written to file", r"written to file\s+(\S+)", "all"),
    # -- system (pw.x) ------------------------------------------------------------------------
    _rule("nat", "number of atoms/cell", r"number of atoms/cell\s*=\s*(\d+)"),
    _rule("ntyp", "number of atomic types", r"number of atomic types\s*=\s*(\d+)"),
    _rule("alat", "lattice parameter", rf"lattice parameter \(alat\)\s*=\s*({NUMBER})"),
    _rule("volume", "unit-cell volume", rf"^\s*unit-cell volume\s*=\s*({NUMBER})", "both"),
    _rule("nelec", "number of electrons", rf"number of electrons\s*=\s*({NUMBER})"),
    _rule("nbnd", "number of Kohn-Sham states", r"number of Kohn-Sham states\s*=\s*(\d+)"),
    _rule("ecutwfc", "kinetic-energy cutoff", rf"kinetic-energy cutoff\s*=\s*({NUMBER})"),
    _rule("ecutrho", "charge density cutoff", rf"charge density cutoff\s*=\s*({NUMBER})"),
    _rule("xc", "Exchange-correlation", r"Exchange-correlation\s*=\s*(.+?)\s*$"),
    _rule(
        "kpoints",
        "number of k points=",
        r"number of k points=\s*(\d+)(?:\s+(.+?),\s*width \(Ry\)=\s*(\S+))?",
    ),
    _rule("spin_orbit", "with spin-orbit", r"Noncollinear calculation with spin-orbit"),
    # -- results (pw.x) -----------------------------------------------------------------------
    _rule("etot", "!", rf"^\s*!\s+total energy\s*=\s*({NUMBER})\s*Ry", "both"),
    _rule("final_energy", "Final energy", rf"Final energy\s*=\s*({NUMBER})\s*Ry", "last"),
    _rule("final_enthalpy", "Final enthalpy", rf"Final enthalpy\s*=\s*({NUMBER})\s*Ry", "last"),
    _rule(
        "mag_total",
        "total magnetization",
        r"^\s*total magnetization\s*=\s*(.+?)\s+Bohr mag/cell",
        "last",
    ),
    _rule(
        "mag_abs",
        "absolute magnetization",
        r"^\s*absolute magnetization\s*=\s*(.+?)\s+Bohr mag/cell",
        "last",
    ),
    _rule("force", "Total force", rf"Total force\s*=\s*({NUMBER})", "last"),
    _rule("pressure", "P=", rf"\(kbar\)\s+P=\s*({NUMBER})", "last"),
    _rule(
        "bfgs_end",
        "bfgs ",
        r"bfgs\s+(converged|failed)\s+(?:in|after)\s+(\d+)\s+scf\s+cycles\s+and\s+(\d+)\s+bfgs",
        "last",
    ),
    _rule("new_volume", "new unit-cell volume", rf"new unit-cell volume\s*=\s*({NUMBER})", "last"),
)

_ERROR_BAR = re.compile(r"^\s*%{4,}\s*$")
_ERROR_HEAD = re.compile(r"Error in routine\s+(\S+)\s*\(([^)]*)\)\s*:")
_MESSAGE = re.compile(r"Message from routine\s+(\w+)\s*:")
_PSEUDO = re.compile(r"PseudoPot\.\s*#\s*(\d+)\s+for\s+(\S+)\s+read from file:")
_ITERATION = re.compile(r"^\s*iteration\s+#")
_CONVERGED = re.compile(r"convergence has been achieved in\s+(\d+)\s+iterations")
_NOT_CONVERGED = re.compile(r"convergence NOT achieved after\s+(\d+)\s+iterations")


@dataclass
class Facts:
    first: dict[str, Hit] = field(default_factory=dict)
    last: dict[str, Hit] = field(default_factory=dict)
    items: dict[str, list[Hit]] = field(default_factory=dict)
    species: dict[str, int] = field(default_factory=dict)  # formula from the header's site list
    pseudos: dict[int, tuple[str, str, int]] = field(
        default_factory=dict
    )  # n → (element, file, line)
    stress: tuple[tuple[str, str, str], ...] = ()  # kbar rows of the last complete stress tensor
    scf_status: Literal["converged", "not_converged"] | None = None  # of the last SCF cycle
    scf_iterations: int = 0
    scf_line: int | None = None
    fermi_line: int | None = None
    issues: list[SummaryIssue] = field(default_factory=list)

    @property
    def program(self) -> str | None:
        hit = self.first.get("program")
        return hit.groups[0] if hit else None

    def hit(self, key: str, *, first: bool = False) -> Hit | None:
        """The last match of ``key`` (the first one with ``first``; rules that keep one only)."""
        if first:
            return self.first.get(key)
        return self.last.get(key) or self.first.get(key)


class Scanner:
    """Feed it every line in order, then call ``finish()``."""

    def __init__(self) -> None:
        self.facts = Facts()
        self._in_header = True  # the site list of the header comes before the first "!" energy
        self._sites_done = False
        self._last_site = 0
        self._stress: list[tuple[str, str, str]] | None = None
        self._pseudo: tuple[int, str, int] | None = None
        self._message: tuple[str, int] | None = None
        self._error: list[str] | None = None
        self._error_line = 0
        self._folded: dict[tuple[str, str, str], int] = {}  # (level, routine, message) → index

    # -- feeding ------------------------------------------------------------------------------
    def feed(self, number: int, line: str) -> None:
        if self._error is not None:
            self._feed_error(line)
            return
        if self._stress is not None and self._feed_stress(number, line):
            return
        if self._pseudo is not None and line.strip():
            index, element, at = self._pseudo
            self._pseudo = None
            self.facts.pseudos.setdefault(index, (element, line.strip().rsplit("/", 1)[-1], at))
            return
        if self._message is not None and line.strip():
            routine, at = self._message
            self._message = None
            self._add_issue("warning", routine, line.strip(), at)
            return
        if "%%%%" in line and _ERROR_BAR.match(line):
            self._error, self._error_line = [], number
            return
        self._feed_rules(number, line)

    def _feed_rules(self, number: int, line: str) -> None:
        facts = self.facts
        for rule in _RULES:
            if rule.needle in line and (match := rule.pattern.search(line)):
                hit = Hit(match.groups(), number)
                if rule.keep == "all":
                    facts.items.setdefault(rule.key, []).append(hit)
                    continue
                if rule.keep != "last":
                    facts.first.setdefault(rule.key, hit)
                if rule.keep != "first":
                    facts.last[rule.key] = hit
                if rule.key == "etot":
                    self._in_header = False
                elif rule.key == "pressure":
                    self._stress = []
        if "tau(" in line and self._in_header and not self._sites_done:
            self._feed_site(line)
        elif "Message from routine" in line and (match := _MESSAGE.search(line)):
            self._message = (match.group(1), number)
        elif "PseudoPot." in line and (match := _PSEUDO.search(line)):
            self._pseudo = (int(match.group(1)), match.group(2), number)
        elif "iteration #" in line and _ITERATION.match(line):
            facts.scf_iterations += 1
        elif "Self-consistent Calculation" in line:
            facts.scf_status, facts.scf_iterations, facts.scf_line = None, 0, number
        elif "convergence" in line:
            if match := _CONVERGED.search(line):
                facts.scf_status, facts.scf_iterations, facts.scf_line = (
                    "converged",
                    int(match.group(1)),
                    number,
                )
            elif match := _NOT_CONVERGED.search(line):
                facts.scf_status, facts.scf_iterations, facts.scf_line = (
                    "not_converged",
                    int(match.group(1)),
                    number,
                )
        if "Fermi energ" in line or "highest occupied" in line:
            facts.fermi_line = number

    def _feed_site(self, line: str) -> None:
        match = SITE.match(line)
        if match is None:
            return
        index = int(match.group("index"))
        if index <= self._last_site:  # a second list (another coordinate format): count one only
            self._sites_done = True
            return
        self._last_site = index
        species = self.facts.species
        name = match.group("species")
        species[name] = species.get(name, 0) + 1

    def _feed_stress(self, number: int, line: str) -> bool:
        """Three rows of six numbers follow ``P=``: Ry/bohr³ then kbar. True if ``line`` was one."""
        assert self._stress is not None
        tokens = line.split()
        if len(tokens) == 6 and all(_is_number(token) for token in tokens):
            self._stress.append((tokens[3], tokens[4], tokens[5]))
            if len(self._stress) == 3:
                self.facts.stress = tuple(self._stress)
                self._stress = None
            return True
        self._stress = None  # not a stress row: a cut file or another block
        return False

    def _feed_error(self, line: str) -> None:
        assert self._error is not None
        if _ERROR_BAR.match(line):
            self._close_error()
        elif line.strip():
            self._error.append(line.strip())

    def _close_error(self) -> None:
        assert self._error is not None
        lines, self._error = self._error, None
        if not lines:  # a bar with nothing after it (cut file, or two bars in a row)
            return
        routine, message = "?", " ".join(lines)
        if match := _ERROR_HEAD.search(lines[0]):
            routine, message = match.group(1), " ".join(lines[1:])
        self._add_issue("error", routine, message, self._error_line)

    def _add_issue(self, level: Level, routine: str, message: str, line: int) -> None:
        key = (level, routine, message)
        issues = self.facts.issues
        if key in self._folded:
            old = issues[self._folded[key]]
            issues[self._folded[key]] = SummaryIssue(
                old.level, old.routine, old.message, old.line, old.count + 1
            )
            return
        self._folded[key] = len(issues)
        issues.append(SummaryIssue(level, routine, message, line))

    def finish(self) -> Facts:
        """The facts; an error block still open at the end of a cut file counts."""
        if self._error is not None:
            self._close_error()
        return self.facts


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True
