"""Löwdin charges and the spilling parameter of a projwfc.x output (spec 99).

``print_lowdin`` (``QE:PP/src/projwfc.f90:280-377``) ends the output with a ``Lowdin Charges:`` block:
- ``nspin = 1`` and spin-orbit: one ``Atom #`` line per l, the atom's total repeated on each;
- ``nspin = 2`` and noncollinear without spin-orbit: one ``Atom #`` line with every l (↑+↓), then a
  ``spin up`` line per l, a ``spin down`` line per l and a ``polarization`` line (↑−↓) with every l;
then ``Spilling Parameter: 1 − Σ charges / nelec``. Each l value is ``, s =  0.9412`` (a space before
the ``=``); the m components that may follow (``pz=  0.6750``) have none and are not read.

The block goes to ``filowdin`` instead when the input names one, and ``pawproj`` does not print it.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .. import cancel
from .projwfc import STATE_LINE

SPILLING_WARN = 0.05  # above it the PDOS warns and the Summary marks the value (user's choice)
TAIL_BYTES = 1 << 20  # what ``read_lowdin`` reads first: the block closes the output
HEADER = "Lowdin Charges:"
ORBITALS = "spdf"

_VALUE = r"(-?\d+\.\d+|\*+)"  # f8.4, or the stars of an overflow
_ATOM = re.compile(rf"Atom #\s*(\d+|\*+):\s*total charge =\s*{_VALUE}")
_SPIN = re.compile(rf"^\s*(spin up|spin down|polarization)\s*=\s*{_VALUE}")
_ORBITAL = re.compile(rf",\s*([spdf]) =\s*{_VALUE}")
_SPILLING = re.compile(rf"Spilling Parameter:\s*{_VALUE}")


@dataclass(frozen=True)
class AtomCharges:
    """The charges of one atom, in electrons; the per-spin ones only with two channels."""

    atom: int
    total: float
    orbitals: dict[str, float] = field(default_factory=dict)  # "s".."f" → ↑+↓
    up: float | None = None
    down: float | None = None
    polarization: float | None = None  # ↑−↓
    orbitals_up: dict[str, float] = field(default_factory=dict)
    orbitals_down: dict[str, float] = field(default_factory=dict)
    orbitals_pol: dict[str, float] = field(default_factory=dict)
    line: int | None = None  # of its first ``Atom #`` line, when the reader was given numbers


@dataclass(frozen=True)
class LowdinCharges:
    atoms: tuple[AtomCharges, ...]
    spilling: float | None
    spilling_line: int | None = None
    species: dict[int, str] = field(default_factory=dict)  # from the list of states
    channels: dict[int, frozenset[str]] = field(default_factory=dict)  # the l of each atom's states
    spinor: bool = False  # ``s_z=`` in the states: ↑/↓ are the spinor's components along z

    @property
    def spin_resolved(self) -> bool:
        return any(atom.up is not None for atom in self.atoms)

    def charge_of(self, atoms: Collection[int]) -> tuple[float, float | None] | None:
        """Total charge and polarization (None without spin) of the ``atoms`` in the block; None
        when none of them is."""
        wanted = set(atoms)
        chosen = [atom for atom in self.atoms if atom.atom in wanted]
        if not chosen:
            return None
        polarizations = [atom.polarization for atom in chosen if atom.polarization is not None]
        return sum(atom.total for atom in chosen), sum(polarizations) if polarizations else None


def spilling_is_high(value: float | None) -> bool:
    return value is not None and value > SPILLING_WARN


def _number(text: str) -> float | None:
    return None if text.startswith("*") else float(text)


@dataclass
class _Atom:
    """An atom while its lines are read (the same fields as ``AtomCharges``)."""

    atom: int
    total: float | None
    orbitals: dict[str, float] = field(default_factory=dict)
    up: float | None = None
    down: float | None = None
    polarization: float | None = None
    orbitals_up: dict[str, float] = field(default_factory=dict)
    orbitals_down: dict[str, float] = field(default_factory=dict)
    orbitals_pol: dict[str, float] = field(default_factory=dict)
    line: int | None = None

    def frozen(self) -> AtomCharges:
        return AtomCharges(
            self.atom,
            self.total if self.total is not None else sum(self.orbitals.values()),
            self.orbitals,
            self.up,
            self.down,
            self.polarization,
            self.orbitals_up,
            self.orbitals_down,
            self.orbitals_pol,
            self.line,
        )


def _orbitals(line: str, into: dict[str, float]) -> list[str]:
    """Store the ``, l = value`` pairs of ``line``; their l, in order."""
    found = []
    for label, text in _ORBITAL.findall(line):
        found.append(label)
        if (value := _number(text)) is not None:
            into[label] = value
    return found


class LowdinReader:
    """Feed it the lines of a projwfc.x output in order, then call ``finish()``."""

    def __init__(self) -> None:
        self._seen = False  # a header was read
        self._in_block = False  # between the header and the spilling
        self._atoms: dict[int, _Atom] = {}
        self._current: _Atom | None = None
        self._spilling: tuple[float | None, int | None] | None = None
        self._species: dict[int, str] = {}
        self._channels: dict[int, set[str]] = {}
        self._spinor = False

    def feed(self, line: str, number: int | None = None) -> None:
        if self._in_block:
            self._feed_block(line, number)
        elif "state #" in line and (match := STATE_LINE.match(line)):
            atom = int(match["atom"])
            self._species.setdefault(atom, match["species"].strip())
            if (l := int(match["l"])) < len(ORBITALS):  # noqa: E741 - physics notation
                self._channels.setdefault(atom, set()).add(ORBITALS[l])
            self._spinor = self._spinor or "s_z=" in line
        elif HEADER in line:
            self._start()

    def _start(self) -> None:
        """A block begins: an earlier one (an appended rerun) is dropped."""
        self._seen = self._in_block = True
        self._atoms, self._current, self._spilling = {}, None, None

    def _feed_block(self, line: str, number: int | None) -> None:
        if "Atom #" in line and (match := _ATOM.search(line)):
            self._atom_line(match, line, number)
        elif "=" in line and self._current is not None and (match := _SPIN.match(line)):
            kind, value = match.group(1), _number(match.group(2))
            atom = self._current
            if kind == "spin up":
                atom.up = value
                _orbitals(line, atom.orbitals_up)
            elif kind == "spin down":
                atom.down = value
                _orbitals(line, atom.orbitals_down)
            else:
                atom.polarization = value
                _orbitals(line, atom.orbitals_pol)
        elif "Spilling" in line and (match := _SPILLING.search(line)):
            self._spilling = (_number(match.group(1)), number)
            self._in_block = False
        elif HEADER in line:
            self._start()

    def _atom_line(self, match: re.Match[str], line: str, number: int | None) -> None:
        raw, total = match.group(1), _number(match.group(2))
        current = self._current
        orbitals: dict[str, float] = {}
        labels = _orbitals(line, orbitals)
        if raw.isdigit():
            atom = int(raw)
            new = current is None or atom != current.atom
        else:  # i3 overflow past atom 999: a line that starts at s opens the next atom
            new = current is None or labels[:1] == ["s"]
            atom = 1 if current is None else current.atom + 1 if new else current.atom
        if new:
            current = self._current = self._atoms[atom] = _Atom(atom, total, line=number)
        assert current is not None
        current.orbitals.update(orbitals)

    def finish(self) -> LowdinCharges | None:
        """None when the output has no block."""
        if not self._seen:
            return None
        spilling, line = self._spilling or (None, None)
        return LowdinCharges(
            tuple(atom.frozen() for atom in self._atoms.values()),
            spilling,
            line,
            dict(self._species),
            {atom: frozenset(ls) for atom, ls in self._channels.items()},
            self._spinor,
        )


def read_lines(lines: Iterable[str]) -> LowdinCharges | None:
    reader = LowdinReader()
    for line in cancel.checked(lines):
        reader.feed(line)
    return reader.finish()


def read_lowdin(path: Path) -> LowdinCharges | None:
    """The block of the projwfc.x output ``path`` (no line numbers), or None. Only the end of the file
    is read, unless the block is longer than that; raises ``OSError`` as ``open`` does."""
    with open(path, "rb") as handle:
        size = handle.seek(0, 2)
        handle.seek(max(0, size - TAIL_BYTES))
        tail = handle.read().decode("utf-8", errors="replace")
    if size <= TAIL_BYTES:
        return read_lines(tail.splitlines())
    if (start := tail.rfind(HEADER)) >= 0:
        return read_lines(tail[start:].splitlines())
    if "Atom #" not in tail and "Spilling Parameter" not in tail:
        return None  # no block (``filowdin``, ``pawproj``): the rest is not read
    with open(path, encoding="utf-8", errors="replace") as handle:
        return read_lines(handle)  # a block longer than the tail
