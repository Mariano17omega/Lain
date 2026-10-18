"""The ``Structure`` of a pw.x input (spec 43 R1): any ``calculation`` (scf, nscf, bands, relax, vc-relax…).

Read with what Lain already has, never ASE: ``InputEditor`` (the viewer's lexer), ``crystal_from_editor``
(QE 7.1's ``latgen``: every ``ibrav``) and the ``if_pos`` flags of ``surface/model.flags_of``. A relax input
shows its *input* geometry. Errors are ``StructureReadError`` with a Portuguese sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...i18n import _
from ..calc_create.surface.model import flags_of
from ..qe.input_edit import InputEditor, read_input_text
from ..qe.lattice import StructureError, crystal_from_editor
from ..qe.pw_input import fortran_float
from ..sniff import INPUT_READ_LIMIT
from .elements import UNKNOWN_RADIUS, element_for_label
from .model import SourceInfo, SpeciesInfo, Structure

__all__ = ["StructureReadError", "read_structure", "structure_of_text"]

DEFAULT_PREFIX = "pwscf"
DEFAULT_CALCULATION = "scf"
_MAGNETIZATION = re.compile(r"starting_magnetization\((\d+)\)")


class StructureReadError(Exception):
    """Why the structure of a file cannot be shown, in Portuguese."""


def read_structure(path: Path) -> Structure:
    """The structure of the input ``path``. Workers only: it reads the file."""
    path = Path(path)
    try:
        if path.stat().st_size > INPUT_READ_LIMIT:
            raise StructureReadError(
                _("{name} passa de 2 MB: grande demais para um input").format(name=path.name)
            )
        text = read_input_text(path)
    except OSError as exc:
        raise StructureReadError(
            _("Não foi possível ler {name}: {value}").format(
                name=path.name, value=exc.strerror or exc
            )
        ) from exc
    return structure_of_text(text, path)


def structure_of_text(text: str, path: Path | None = None) -> Structure:
    """The structure of an input's text. Raises ``StructureReadError``."""
    name = path.name if path is not None else _("o input")
    editor = InputEditor.from_text(text)
    if not editor.has_namelist("system"):
        raise StructureReadError(_("{name} não é um input do pw.x (sem &SYSTEM)").format(name=name))
    try:
        crystal = crystal_from_editor(editor)
    except StructureError as exc:
        raise StructureReadError(
            _("Estrutura de {name} ilegível: {exc}").format(name=name, exc=exc)
        ) from exc
    count = len(crystal.labels)
    flags = (flags_of(text) + (None,) * count)[:count]
    ntyp = _integer(editor, "system", "ntyp")
    species, warnings = _species(editor, ntyp, crystal.labels)
    source = SourceInfo(
        path=str(path) if path is not None else None,
        ibrav=_integer(editor, "system", "ibrav") or 0,
        nat=count,
        ntyp=ntyp,
        prefix=editor.get("control", "prefix") or DEFAULT_PREFIX,
        calculation=(editor.get("control", "calculation") or DEFAULT_CALCULATION).lower(),
        nspin=_integer(editor, "system", "nspin") or 1,
        starting_magnetization=_magnetization(editor),
        warnings=tuple(warnings),
    )
    return Structure(crystal.cell, crystal.labels, crystal.frac, flags, species, source)


def _integer(editor: InputEditor, namelist: str, key: str) -> int | None:
    text = editor.get(namelist, key)
    value = fortran_float(text) if text is not None else None
    return int(value) if value is not None and value == int(value) else None


def _species(
    editor: InputEditor, ntyp: int | None, labels: tuple[str, ...]
) -> tuple[tuple[SpeciesInfo, ...], list[str]]:
    """The rows of ``ATOMIC_SPECIES`` (up to ``ntyp``), plus an empty entry for each position label
    without a row; and the warnings of both kinds of trouble."""
    card = editor.card("ATOMIC_SPECIES")
    rows = list(card.lines) if card is not None else []
    if ntyp is not None:
        rows = rows[:ntyp]
    species: list[SpeciesInfo] = []
    known: set[str] = set()
    for row in rows:
        words = row.split()
        if not words or words[0] in known:
            continue
        mass = fortran_float(words[1]) if len(words) > 1 else None
        pseudo = words[2] if len(words) > 2 else None
        species.append(SpeciesInfo(words[0], mass, pseudo, len(species) + 1))
        known.add(words[0])
    warnings = []
    for label in dict.fromkeys(labels):
        if label not in known:
            species.append(SpeciesInfo(label, None, None, len(species) + 1))
            known.add(label)
            warnings.append(
                _(
                    "Espécie {label} sem linha em ATOMIC_SPECIES (massa e pseudopotencial vazios)"
                ).format(label=label)
            )
    radius = f"{UNKNOWN_RADIUS:.1f}".replace(".", ",")
    warnings += [
        _("Espécie sem elemento conhecido: {label} (cinza, raio {radius} Å)").format(
            label=s.label, radius=radius
        )
        for s in species
        if not element_for_label(s.label).known
    ]
    return tuple(species), warnings


def _magnetization(editor: InputEditor) -> dict[int, float]:
    """``starting_magnetization(i)`` by species number."""
    found: dict[int, float] = {}
    for key in editor.keys("system"):
        match = _MAGNETIZATION.fullmatch(key)
        text = editor.get("system", key) if match else None
        value = fortran_float(text) if text is not None else None
        if match and value is not None:
            found[int(match.group(1))] = value
    return found
