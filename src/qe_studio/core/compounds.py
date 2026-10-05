"""Compounds and the atom selection remembered for each (spec 21).

A compound is identified by the **sequence of species in the order of the input** (``Al Al O O O``):
atom numbers (the ``N`` of ``pdos_atm#N``) follow that order, so the same sequence means the same
atoms. Positions never enter the key (a relax moves atoms, not the compound); the formula is only a
label. The selection is kept in the app data dir (``compounds.json``), never inside a simulation
folder (they get synced), like ``NavigationStore`` and ``FolderMemory``.

Since the key ignores positions, a selection saved with one geometry is reused by another (a dopant
in another site, a different relax) of the same sequence. The positions seen when it was saved go
with it (``sites``, spec 27-6), and ``geometry_drift`` tells the plot to warn: it never changes the
selection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from .appdirs import atomic_write_text, data_dir, set_aside_corrupt
from .qe.structure import Site, format_formula

log = logging.getLogger(__name__)

# {"version": 1, "compounds": {key: {"formula": "Al2O3", "atoms": [1, 2, 4], "sites": [[x, y, z]…]}}}
# "sites" (Å, 0.01) came later without a new version: readers ignore keys they do not know.
FORMAT_VERSION = 1
SITE_DECIMALS = 2
DRIFT_TOLERANCE = 0.5  # Å: a relax moves atoms less; a dopant in another site moves more

Position = tuple[float, float, float]


@dataclass(frozen=True)
class Compound:
    key: str
    formula: str  # for display only


@dataclass(frozen=True)
class AtomChoices:
    """What the atom picker needs: the atoms of a calculation and the compound they belong to."""

    sites: tuple[Site, ...]
    compound: Compound | None

    @property
    def available(self) -> bool:
        return bool(self.sites) and self.compound is not None


def compound_key(species: Sequence[str]) -> str:
    """``Al Al O O O`` → ``Al2O3:<10 hex digits>``. The readable part collapses runs only, so
    ``Al O Al`` stays ``AlOAl``; the hash is of the full sequence."""
    label = ""
    for name, run in groupby(species):
        count = sum(1 for _ in run)
        label += name + (str(count) if count > 1 else "")
    digest = hashlib.sha1(" ".join(species).encode("utf-8")).hexdigest()[:10]
    return f"{label}:{digest}"


def compound_of(sites: Sequence[Site]) -> Compound | None:
    """The compound of a site list, None when it is empty."""
    if not sites:
        return None
    counts: dict[str, int] = {}
    for site in sites:
        counts[site.species] = counts.get(site.species, 0) + 1
    formula = format_formula(counts) or ""
    return Compound(compound_key([site.species for site in sites]), formula)


@dataclass(frozen=True)
class GeometryDrift:
    """How the structure differs from the one a selection was saved with: the atom (1-based) that
    moved most and how far (Å), or, with another number of atoms, ``counts`` (saved, current)."""

    atom: int | None
    distance: float | None
    counts: tuple[int, int] | None = None


def geometry_drift(
    saved: Sequence[Position], current: Sequence[Position], tol: float = DRIFT_TOLERANCE
) -> GeometryDrift | None:
    """None when every atom is within ``tol`` Å of where it was saved, else the worst one.

    Positions are Cartesian as pw.x printed them, never wrapped: an atom that left the cell on one
    side and came back on the other counts as a large move (a false positive the spec accepts).
    """
    if len(saved) != len(current):
        return GeometryDrift(None, None, (len(saved), len(current)))
    worst: GeometryDrift | None = None
    for index, (old, new) in enumerate(zip(saved, current, strict=True), start=1):
        distance = math.dist(old, new)
        if distance > tol and (worst is None or distance > (worst.distance or 0.0)):
            worst = GeometryDrift(index, distance)
    return worst


def normalize_selection(atoms: Sequence[int] | None, valid: Sequence[int]) -> list[int] | None:
    """The selected atoms that exist, sorted; None (= every atom) when all of them, or none, remain."""
    known = set(valid)
    kept = sorted({a for a in atoms or () if a in known})
    return kept if kept and len(kept) < len(known) else None


def atoms_summary(selected: Sequence[int] | None, total: int) -> str:
    """``todos`` or ``3 de 12``: what the picker button shows beside itself."""
    return "todos" if selected is None else f"{len(selected)} de {total}"


class CompoundStore:
    """``selection(key)`` is None when nothing was saved for the compound (= every atom).

    The file is read once, on first use, and written on every change (atomically). An unreadable
    file is renamed ``compounds.json.corrompido-<date>`` and never overwritten; if it cannot be
    renamed the store keeps working in memory and writes nothing.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "compounds.json"
        self._lock = threading.RLock()
        self._compounds: dict[str, dict] | None = None
        self._warning: str | None = None
        self._read_only = False

    # -- queries ---------------------------------------------------------------------------------
    def selection(self, key: str) -> list[int] | None:
        with self._lock:
            entry = self._load().get(key)
            atoms = entry.get("atoms") if isinstance(entry, dict) else None
            if not isinstance(atoms, list):
                return None
            kept = [a for a in atoms if isinstance(a, int) and not isinstance(a, bool) and a > 0]
            return sorted(set(kept)) or None

    def stored_sites(self, key: str) -> list[Position] | None:
        """The positions (Å) seen when the selection was saved; None when the entry has none (saved
        before spec 27-6) or they do not read as ``[[x, y, z], …]``."""
        with self._lock:
            entry = self._load().get(key)
            sites = entry.get("sites") if isinstance(entry, dict) else None
            if not isinstance(sites, list):
                return None
            out: list[Position] = []
            for site in sites:
                if not (isinstance(site, list) and len(site) == 3 and all(map(_is_number, site))):
                    return None
                out.append((float(site[0]), float(site[1]), float(site[2])))
            return out

    def pop_warning(self) -> str | None:
        """The message about a corrupt file, once (None afterwards or when it was fine)."""
        with self._lock:
            self._load()
            warning, self._warning = self._warning, None
            return warning

    # -- changes ---------------------------------------------------------------------------------
    def save(
        self,
        key: str,
        formula: str,
        atoms: Sequence[int] | None,
        sites: Sequence[Position] | None = None,
    ) -> None:
        """Remember ``atoms`` for the compound, and the positions (Å) they were chosen with when
        ``sites`` is given; None (every atom) removes the entry, so the file does not grow with
        defaults. Other keys of the entry are kept (a newer Lain may have written them)."""
        with self._lock:
            compounds = self._load()
            if atoms is None:
                if compounds.pop(key, None) is None:
                    return
            else:
                old = compounds.get(key)
                entry = dict(old) if isinstance(old, dict) else {}
                entry.update(formula=formula, atoms=sorted({int(a) for a in atoms}))
                if sites is not None:
                    entry["sites"] = [[round(float(c), SITE_DECIMALS) for c in s] for s in sites]
                compounds[key] = entry
            self._write()

    def forget(self, key: str) -> None:
        self.save(key, "", None)

    # -- file ------------------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if self._compounds is not None:
            return self._compounds
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            data = self._set_aside(exc)
        if not isinstance(data, dict):
            data = self._set_aside("o conteúdo não é um objeto JSON")
        compounds = data.get("compounds")
        if data and (data.get("version") != FORMAT_VERSION or not isinstance(compounds, dict)):
            self._set_aside(f"versão de formato desconhecida: {data.get('version')!r}")
            compounds = None
        self._compounds = compounds if isinstance(compounds, dict) else {}
        return self._compounds

    def _set_aside(self, problem: object) -> dict:
        try:
            copy = set_aside_corrupt(self.path)
        except OSError as exc:
            self._read_only = True
            self._warning = (
                f"{self.path.name} ilegível e não pôde ser copiado ({exc.strerror or exc}): "
                "a seleção de átomos desta sessão não será salva"
            )
        else:
            self._warning = f"{self.path.name} estava corrompido; cópia salva em {copy}"
        log.warning("%s (%s)", self._warning, problem)
        return {}

    def _write(self) -> None:
        if self._read_only:
            return
        data = {"version": FORMAT_VERSION, "compounds": self._load()}
        atomic_write_text(self.path, json.dumps(data, indent=1, ensure_ascii=False))


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
