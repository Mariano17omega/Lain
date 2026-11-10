"""What a fragment of a pw.x input must renumber when atoms and species leave it (spec 30 R2.2).

The input numbers things by position: the species of ``ATOMIC_SPECIES`` (``starting_magnetization(2)``
is the second one) and the atoms of ``ATOMIC_POSITIONS`` (the ``V`` lines of ``HUBBARD``). Dropping the
first species of three makes the old 2 the new 1, so each key and each index follows its species or
atom, and what belonged to one that left goes with it. Edits keep the lines they do not touch as
written (``InputEditor``); nothing here raises.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ...i18n import _
from ..qe.input_edit import InputEditor

__all__ = ["SPECIES_KEYS", "remap_hubbard", "remap_species_keys"]

# ``&SYSTEM`` keys indexed by species, the species being the *last* index (``hubbard_j(m,i)``,
# ``starting_ns_eigenvalue(m,s,i)``). Lowercase, as the lexer keeps them.
SPECIES_KEYS = frozenset(
    {
        "starting_magnetization",
        "starting_charge",
        "angle1",
        "angle2",
        "london_c6",
        "london_rvdw",
        "hubbard_u",
        "hubbard_j0",
        "hubbard_alpha",
        "hubbard_beta",
        "hubbard_u_back",
        "hubbard_alpha_back",
        "hubbard_j",
        "starting_ns_eigenvalue",
    }
)
# The keys whose species is the *first* index (``hubbard_occ(i,n)``, ``n`` being the manifold).
FIRST_INDEX_KEYS = frozenset({"hubbard_occ"})
_KEY = re.compile(r"(\w+)\(([^()]*)\)")
_COMMENT = re.compile(r"[!#]")
_TOKEN = re.compile(r"\S+")
_MANIFOLDS = re.compile(r"(?:-\d[a-zA-Z])+$")  # the end of a label: ``-3d``, ``-2p-3s``


def remap_species_keys(editor: InputEditor, mapping: Mapping[int, int]) -> list[str]:
    """Follow the species through ``mapping`` (old 1-based index → new one; absent = dropped): the keys of
    a dropped species are removed, the others renamed in place. Returns notes."""
    found: list[tuple[str, str, list[str], int, int]] = []  # key, base, indices, position, species
    notes: list[str] = []
    for key in editor.keys("system"):
        match = _KEY.fullmatch(key)
        if match is None:
            continue
        base, indices = match.group(1), match.group(2).split(",")
        if base == "hubbard_v":
            notes.append(_("{key} usa índices de átomo: não foi renumerado").format(key=key))
            continue
        position = 0 if base in FIRST_INDEX_KEYS else len(indices) - 1
        if (base in SPECIES_KEYS or base in FIRST_INDEX_KEYS) and indices[
            position
        ].strip().isdigit():
            found.append((key, base, indices, position, int(indices[position])))
    for key, *_rest, species in found:
        if species not in mapping:
            editor.remove("system", key)
    # The map only ever lowers an index, so renaming from the lowest never lands on a key not yet moved.
    for key, base, indices, position, species in sorted(found, key=lambda item: item[4]):
        new = mapping.get(species)
        if new is not None and new != species:
            renamed = [*indices[:position], str(new), *indices[position + 1 :]]
            editor.rename_key("system", key, f"{base}({','.join(renamed)})")
    return notes


def _species_of(label: str) -> str:
    """``Fe-3d`` → ``Fe``, ``O-2p-3s`` → ``O``: the species of a ``HUBBARD`` manifold label, whose own
    name may hold a ``-`` (``Fe-up-3d`` → ``Fe-up``)."""
    return _MANIFOLDS.sub("", label)


def _atom_index(index: int, atoms: Mapping[int, int], nat: int, nat_new: int) -> int | None:
    """The new number of atom ``index`` (None: it left). One past ``nat`` is taken as a periodic image
    of the 3×3×3 supercell ``V`` may cite: ``index = atom + nat·k``, kept as ``new atom + nat_new·k``.
    That numbering is an assumption (``INPUT_PW`` only says "index of the atom"): the caller notes it."""
    atom, image = (index - 1) % nat + 1, (index - 1) // nat
    new = atoms.get(atom)
    return None if new is None else new + nat_new * image


def remap_hubbard(
    editor: InputEditor, dropped: set[str], atoms: Mapping[int, int], nat: int
) -> list[str]:
    """The ``HUBBARD`` card (QE 7.1 and later) of a fragment: the lines of a species in ``dropped`` go; a
    ``V`` line (``V Fe-3d O-2p i j value``) goes when it names an atom that left, else its two atom
    indices are renumbered through ``atoms`` (old → new). An empty card is removed. Returns notes."""
    rows = editor.card_rows("HUBBARD")
    if not rows:
        return []
    nat_new = len(atoms)
    out: list[str] = []
    notes: list[str] = []
    images = False
    for row in rows:
        code = _COMMENT.split(row, maxsplit=1)[0]
        tokens = list(_TOKEN.finditer(code))
        words = [token.group() for token in tokens]
        labels = words[1:3] if words[:1] == ["V"] else words[1:2]
        if any(_species_of(label) in dropped for label in labels):
            continue
        if words[:1] == ["V"] and len(words) >= 5 and words[3].isdigit() and words[4].isdigit():
            new = [_atom_index(int(word), atoms, nat, nat_new) for word in words[3:5]]
            if None in new:
                notes.append(
                    _("HUBBARD: linha V removida (cita um átomo fora do fragmento): {row}").format(
                        row=row.strip()
                    )
                )
                continue
            images = images or any(int(word) > nat for word in words[3:5])
            for token, number in sorted(
                zip(tokens[3:5], new, strict=True), key=lambda p: -p[0].start()
            ):
                row = row[: token.start()] + str(number) + row[token.end() :]
        out.append(row)
    if out == rows:
        return notes
    if images:
        notes.append(
            _(
                "HUBBARD: índice de átomo vizinho (maior que nat) renumerado pela supercélula 3×3×3; "
                "confira"
            )
        )
    if out:
        editor.replace_card_rows("HUBBARD", out)
    else:
        editor.remove_card("HUBBARD")
        notes.append(_("HUBBARD sem linhas neste fragmento: o card foi removido"))
    return notes
