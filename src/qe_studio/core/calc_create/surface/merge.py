"""What the input of a molecule on a surface takes from each SCF (spec 42 R4, the adsorbed branch of
``assemble_namelists`` / ``assemble_species`` of the scripts).

The input starts from the surface's text (the unit's: ``Work.editor``): cell, cutoffs, mesh and every
other line stay the surface's. ``ATOMIC_SPECIES`` keeps the surface's rows and adds the molecule's
species it lacks (a species in both keeps the surface's pseudopotential, with a note when they differ).
The namelists become a relax of the whole system: no ``&CELL``, no ``nbnd`` (pw.x's default counts the
molecule's electrons), the molecule's occupations (it may close the gap) and the smaller
``mixing_beta``. Other differences between the two SCFs are only noted. Qt-free.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from ....i18n import _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..edits import put_number, put_string
from ..scf_info import ScfInfo
from .elements import element_of

__all__ = [
    "NBND_NOTE",
    "SpeciesMerge",
    "adsorbed_prefix",
    "difference_notes",
    "formula",
    "merge_namelists",
    "merge_species",
]

NBND_NOTE = _("nbnd removido: o pw.x calcula o padrão para o sistema com a molécula")
SMEARING_KEYS = ("smearing", "degauss")


@dataclass(frozen=True)
class SpeciesMerge:
    rows: tuple[str, ...]  # the ATOMIC_SPECIES rows of the new input
    added: tuple[str, ...]  # the molecule's labels the surface lacked
    notes: tuple[str, ...] = ()


def _number(text: str) -> float | None:
    return fortran_float(text)


def merge_species(surface_rows: Sequence[str], molecule_rows: Sequence[str]) -> SpeciesMerge:
    """The surface's rows, then the molecule's rows of the labels the surface lacks, in its order."""
    rows = list(surface_rows)
    have = {row.split()[0]: row.split() for row in rows if row.split()}
    added: list[str] = []
    notes: list[str] = []
    for row in molecule_rows:
        words = row.split()
        if not words:
            continue
        label = words[0]
        mine = have.get(label)
        if mine is None:
            rows.append(row.strip())
            have[label] = words
            added.append(label)
            continue
        if mine[2:3] != words[2:3]:
            notes.append(
                _("{label}: vale o pseudopotencial da superfície ({join})").format(
                    label=label, join=" ".join(mine[2:3])
                )
            )
        elif (_number(mine[1]) if len(mine) > 1 else None) != (
            _number(words[1]) if len(words) > 1 else None
        ):
            notes.append(
                _("{label}: vale a massa da superfície ({join})").format(
                    label=label, join=" ".join(mine[1:2])
                )
            )
    return SpeciesMerge(tuple(rows), tuple(added), tuple(notes))


def merge_namelists(editor: InputEditor, molecule: ScfInfo | None) -> list[str]:
    """Turn the surface's namelists in ``editor`` into the adsorbed system's; returns the notes.
    Without ``molecule`` only what the surface loses (``&CELL``, ``nbnd``). ``calculation`` and the
    relax keys are the type's (``RelaxType.edit``)."""
    notes: list[str] = []
    while editor.remove_namelist("cell"):
        pass
    if editor.get("system", "nbnd") is not None:
        editor.remove("system", "nbnd")
        notes.append(NBND_NOTE)
    if molecule is None:
        return notes
    occupations = molecule.value("system", "occupations")
    if occupations:
        put_string(editor, "system", "occupations", occupations.strip())
        smearing = molecule.value("system", "smearing")
        if smearing:
            put_string(editor, "system", "smearing", smearing.strip())
        degauss = _number(molecule.value("system", "degauss") or "")
        if degauss is not None:
            put_number(editor, "system", "degauss", degauss)
    mine = _number(editor.get("electrons", "mixing_beta") or "")
    theirs = _number(molecule.value("electrons", "mixing_beta") or "")
    if mine is not None and theirs is not None and theirs < mine:
        put_number(editor, "electrons", "mixing_beta", theirs)
    return notes


def _written(scf: ScfInfo, namelist: str, key: str) -> str:
    value = scf.value(namelist, key)
    return value.strip() if value and value.strip() else ""


def _cutoffs(scf: ScfInfo) -> tuple[float | None, float | None]:
    rho = (
        scf.ecutrho
        if scf.ecutrho is not None
        else (4 * scf.ecutwfc if scf.ecutwfc is not None else None)
    )
    return scf.ecutwfc, rho


def difference_notes(
    surface: ScfInfo, molecule: ScfInfo, added: Sequence[str], pseudo_dir_set: bool
) -> list[str]:
    """What differs between the two SCFs and is kept from the surface: informative only."""
    notes: list[str] = []
    for key, mine, theirs in zip(
        ("ecutwfc", "ecutrho"), _cutoffs(surface), _cutoffs(molecule), strict=True
    ):
        if mine is not None and theirs is not None and theirs > mine:
            notes.append(
                _(
                    "{key}: molécula {theirs:g} Ry, superfície {mine:g} Ry; vale o da superfície"
                ).format(key=key, theirs=theirs, mine=mine)
            )
    for key in ("vdw_corr", "input_dft"):
        mine, theirs = _written(surface, "system", key), _written(molecule, "system", key)
        if mine.lower() != theirs.lower():
            notes.append(
                _("{key}: superfície '{value}', molécula '{value_2}'; vale o da superfície").format(
                    key=key, value=mine or "nenhum", value_2=theirs or "nenhum"
                )
            )
    if surface.nspin != molecule.nspin:
        notes.append(
            _("nspin: superfície {nspin}, molécula {nspin_2}; vale o da superfície").format(
                nspin=surface.nspin, nspin_2=molecule.nspin
            )
        )
    mine, theirs = surface.pseudo_dir or "", molecule.pseudo_dir or ""
    if added and not pseudo_dir_set and mine.rstrip("/") != theirs.rstrip("/"):
        notes.append(
            _(
                "pseudo_dir: superfície '{mine}', molécula '{theirs}'; os pseudopotenciais de {join} precisam estar no da superfície"
            ).format(mine=mine, theirs=theirs, join=", ".join(added))
        )
    return notes


def formula(labels: Sequence[str]) -> str:
    """``HgCH3``: the elements in the order they first appear, with their counts."""
    counts = Counter(element_of(label) for label in labels)
    return "".join(f"{element}{n if n > 1 else ''}" for element, n in counts.items())


def adsorbed_prefix(
    surface_prefix: str, molecule_labels: Sequence[str], sites: Sequence[tuple[str, int]]
) -> str:
    """``<surface>-<formula>-<site>``: ``kaolinite-slab-001-2x1x1-HgCH3-O43`` or ``…-O43-O46``
    (``sites``: label and 1-based number, ascending)."""
    site = "-".join(f"{label}{number}" for label, number in sorted(sites, key=lambda s: s[1]))
    return f"{surface_prefix}-{formula(molecule_labels)}-{site}"
