"""The two fragments of a charge-difference calculation (spec 30 R2): an SCF split by atoms.

``atom_rows`` reads the atoms of the user's SCF as written, for the table that picks them.
``split_input`` makes the two pw.x inputs from the text: *isolated* (only the chosen atoms) and *clean*
(all the others). Both keep the cell, cutoffs, ``K_POINTS`` and every line of the original that they
need, byte for byte: the positions keep the text of each line (``if_pos`` flags, comments), the species
no atom uses leave ``ATOMIC_SPECIES`` and what is numbered by species or atom follows them
(``species_keys``). Qt-free; never raises: a selection that cannot be split gives errors and the
original text twice.
"""

from __future__ import annotations

import functools
from collections.abc import Collection
from dataclasses import dataclass

from ..qe.input_edit import InputEditor
from ..qe.pw_input import fortran_float
from .edits import put_number
from .species_keys import remap_hubbard, remap_species_keys

__all__ = [
    "CLEAN",
    "ISOLATED",
    "AtomRow",
    "AtomRows",
    "Fragments",
    "atom_rows",
    "split_input",
]

CLEAN, ISOLATED = "clean", "isolated"
UNITS = ("alat", "bohr", "angstrom", "crystal")
PER_ATOM_CARDS = ("ATOMIC_FORCES", "ATOMIC_VELOCITIES")  # a row per atom, in the atoms' order
WHOLE_SYSTEM_KEYS = ("tot_charge", "tot_magnetization")
NOTHING_SELECTED = "Selecione os átomos do fragmento isolado"
EVERYTHING_SELECTED = "Deixe ao menos um átomo fora da seleção: o SCF clean ficaria vazio"
CONSTRAINTS = "Restrições (CONSTRAINTS) não são suportadas na diferença de carga"
CRYSTAL_SG = "Posições em crystal_sg não são suportadas"


@dataclass(frozen=True)
class AtomRow:
    index: int  # 1-based
    label: str
    x: str  # the coordinates as written
    y: str
    z: str


@dataclass(frozen=True)
class AtomRows:
    unit: str  # of the card: alat, bohr, angstrom, crystal ("" when there are no rows)
    rows: tuple[AtomRow, ...] = ()
    error: str = ""  # why there are none, in Portuguese


@dataclass(frozen=True)
class Fragments:
    clean: str
    isolated: str
    notes: tuple[tuple[str, str], ...] = ()  # (CLEAN | ISOLATED, text): warnings, never block
    errors: tuple[str, ...] = ()  # "Criar" stays disabled


def _int(editor: InputEditor, key: str) -> int | None:
    text = editor.get("system", key)
    number = fortran_float(text) if text is not None else None
    return int(number) if number is not None and number == int(number) else None


def _positions(editor: InputEditor) -> tuple[str, list[str], str]:
    """(unit, the first ``nat`` rows as written, the problem or "")."""
    if editor.issues:
        return "", [], f"Input não pôde ser lido: {editor.issues[0]}"
    card = editor.card("ATOMIC_POSITIONS")
    rows = editor.card_rows("ATOMIC_POSITIONS")
    if card is None or not rows:
        return "", [], "sem ATOMIC_POSITIONS"
    unit = card.option or "alat"
    if unit == "crystal_sg":
        return "", [], CRYSTAL_SG
    if unit not in UNITS:
        return "", [], f"ATOMIC_POSITIONS {unit} não é suportado"
    nat = _int(editor, "nat")
    nat = len(rows) if nat is None else nat
    if nat < 1 or len(rows) < nat:
        return "", [], f"nat = {nat}, mas ATOMIC_POSITIONS tem {len(rows)} linhas"
    return unit, rows[:nat], ""


@functools.lru_cache(maxsize=16)  # the window plans on every edit; the text rarely changes
def atom_rows(text: str) -> AtomRows:
    """The atoms of ``ATOMIC_POSITIONS`` as the SCF writes them, whatever its structure (it needs no
    cell, so an ``ibrav`` the app cannot build still lists them)."""
    unit, rows, problem = _positions(InputEditor.from_text(text))
    if problem:
        return AtomRows("", (), problem)
    out = []
    for index, row in enumerate(rows, 1):
        words = row.split()
        if len(words) < 4:
            return AtomRows("", (), f"linha de ATOMIC_POSITIONS ilegível: {row.strip()}")
        out.append(AtomRow(index, words[0], words[1], words[2], words[3]))
    return AtomRows(unit, tuple(out))


def _fragment(text: str, keep: list[int], nat: int) -> tuple[InputEditor, list[str]]:
    """The input of the atoms ``keep`` (1-based, ascending) and its notes."""
    editor = InputEditor.from_text(text)
    notes: list[str] = []
    positions = editor.card_rows("ATOMIC_POSITIONS") or []
    kept = [positions[i - 1] for i in keep]
    editor.replace_card_rows("ATOMIC_POSITIONS", kept)
    put_number(editor, "system", "nat", len(keep))
    atoms = {old: new for new, old in enumerate(keep, 1)}
    for name in PER_ATOM_CARDS:
        rows = editor.card_rows(name)
        if rows is not None:
            editor.replace_card_rows(name, [rows[i - 1] for i in keep if i <= len(rows)])

    labels = {row.split()[0] for row in kept}
    species = editor.card_rows("ATOMIC_SPECIES")
    if species is not None:
        ntyp = _int(editor, "ntyp")
        species = species if ntyp is None else species[:ntyp]
        mapping, rows, dropped = {}, [], set()
        for old, row in enumerate(species, 1):
            if row.split()[0] in labels:
                rows.append(row)
                mapping[old] = len(rows)
            else:
                dropped.add(row.split()[0])
        editor.replace_card_rows("ATOMIC_SPECIES", rows)
        put_number(editor, "system", "ntyp", len(rows))
        notes += remap_species_keys(editor, mapping)
        notes += remap_hubbard(editor, dropped, atoms, nat)

    if editor.remove("system", "nbnd"):
        notes.append("nbnd removido: o pw.x escolhe pelo número de elétrons do fragmento")
    if _int(editor, "nspin") == 2 and not any(
        key.startswith("starting_magnetization(") for key in editor.keys("system")
    ):
        notes.append(
            "nspin = 2, mas nenhuma espécie deste fragmento tem starting_magnetization: "
            "o pw.x para (some starting_magnetization MUST be set)"
        )
    notes += [
        f"{key} do SCF vale para o sistema inteiro: confira se serve a este fragmento"
        for key in WHOLE_SYSTEM_KEYS
        if editor.get("system", key) is not None
    ]
    return editor, notes


def split_input(text: str, selected: Collection[int]) -> Fragments:
    """``isolated``: the ``selected`` atoms (1-based) alone; ``clean``: the rest. A selection that is
    empty or total, ``CONSTRAINTS`` or a structure that cannot be read are errors, and both texts are
    then the original."""
    editor = InputEditor.from_text(text)
    _, rows, problem = _positions(editor)
    if problem:
        return Fragments(text, text, (), (problem,))
    nat = len(rows)
    chosen = sorted({index for index in selected if 1 <= index <= nat})
    rest = [index for index in range(1, nat + 1) if index not in chosen]
    errors = []
    if not chosen:
        errors.append(NOTHING_SELECTED)
    elif not rest:
        errors.append(EVERYTHING_SELECTED)
    if editor.card("CONSTRAINTS") is not None:
        errors.append(CONSTRAINTS)
    if errors:
        return Fragments(text, text, (), tuple(errors))
    clean, clean_notes = _fragment(text, rest, nat)
    isolated, isolated_notes = _fragment(text, chosen, nat)
    errors = [
        f"{which}: {issue}"
        for which, made in ((CLEAN, clean), (ISOLATED, isolated))
        for issue in made.issues
    ]
    if errors:
        return Fragments(text, text, (), tuple(errors))
    notes = [(CLEAN, note) for note in clean_notes] + [(ISOLATED, note) for note in isolated_notes]
    return Fragments(clean.text(), isolated.text(), tuple(notes))
