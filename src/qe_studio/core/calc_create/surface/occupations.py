"""The occupations of the adsorbed system, from its two SCFs (spec 96, which replaces spec 42 R4.2).

The most permissive wins: ``smearing`` in either SCF gives ``smearing``; ``fixed``, the tetrahedra and
``from_input`` never come from the molecule. A surface with ``smearing`` keeps its own (the extended
system sets the broadening), unless it has no ``degauss`` (pw.x stops: its SCF never ran) and the
molecule's smearing has one: then the molecule's ``smearing`` and ``degauss`` come as a pair. A
surface without ``smearing`` takes the molecule's ``occupations``, ``smearing`` and ``degauss`` when
the molecule has smearing, and keeps its own otherwise.

Values are compared as pw.x reads them (``QE:Modules/read_namelists.f90:181-183`` for what is left
out, the aliases of ``QE:PW/src/set_occupations.f90:48-60``) and written as the SCF they come from
writes them. The notes say what differed; nothing blocks. Qt-free.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ....i18n import _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float
from ..edits import put_string
from ..scf_info import ScfInfo

__all__ = ["NO_DEGAUSS", "SAME_OCCUPATIONS", "merge_occupations"]

SMEARING = "smearing"
FIXED = "fixed"  # pw.x's occupations when none is written
GAUSSIAN = "gaussian"  # pw.x's smearing when none is written
_ALIASES = {
    "gaussian": ("gaussian", "gauss"),
    "methfessel-paxton": ("methfessel-paxton", "m-p", "mp"),
    "marzari-vanderbilt": ("marzari-vanderbilt", "cold", "m-v", "mv"),
    "fermi-dirac": ("fermi-dirac", "f-d", "fd"),
}
_FAMILY = {alias: family for family, aliases in _ALIASES.items() for alias in aliases}

# Spec 96 R1.4, the reminder for the adsorption energy (F6 of the report of 11/11/2026).
SAME_OCCUPATIONS = _(
    "Energia de adsorção: a superfície limpa e a molécula isolada devem usar as ocupações deste input (occupations, smearing e degauss)"
)
NO_DEGAUSS = _(
    "occupations 'smearing' sem degauss: o pw.x para; escreva o degauss no modo Avançado"
)


@dataclass(frozen=True)
class _Scheme:
    """The occupations an SCF writes, stripped ("" when left out)."""

    occupations: str
    smearing: str
    degauss_text: str

    @classmethod
    def read(cls, value: Callable[[str, str], str | None]) -> _Scheme:
        texts = (
            (value("system", key) or "").strip() for key in ("occupations", SMEARING, "degauss")
        )
        return cls(*texts)

    @property
    def kind(self) -> str:
        """``occupations`` as pw.x tells them apart: ``tetrahedra-opt`` is ``tetrahedra_opt``."""
        return self.shown.lower().replace("-", "_")

    @property
    def shown(self) -> str:
        return self.occupations or FIXED

    @property
    def is_smearing(self) -> bool:
        return self.kind == SMEARING

    @property
    def smearing_shown(self) -> str:
        return self.smearing or GAUSSIAN

    @property
    def family(self) -> str:
        name = self.smearing_shown.lower()
        return _FAMILY.get(name, name)

    @property
    def degauss(self) -> float | None:
        """A broadening pw.x accepts (``> 0``, ``set_occupations.f90:42-46``), else None."""
        number = fortran_float(self.degauss_text)
        return number if number is not None and number > 0 else None


def merge_occupations(editor: InputEditor, molecule: ScfInfo) -> list[str]:
    """Write the adsorbed system's occupations into ``editor`` (the surface's text); returns the notes."""
    mine, theirs = _Scheme.read(editor.get), _Scheme.read(molecule.value)
    notes = _differences(mine, theirs)
    if theirs.is_smearing and not mine.is_smearing:
        put_string(editor, "system", "occupations", theirs.occupations)
        _take_broadening(editor, mine, theirs)
    elif theirs.is_smearing and mine.degauss is None and theirs.degauss is not None:
        _take_broadening(editor, mine, theirs)
    if notes:
        notes.append(SAME_OCCUPATIONS)
    result = _Scheme.read(editor.get)
    if result.is_smearing and result.degauss is None:
        notes.append(NO_DEGAUSS)
    return notes


def _take_broadening(editor: InputEditor, mine: _Scheme, theirs: _Scheme) -> None:
    """The molecule's ``smearing`` and ``degauss`` in place of the surface's: a key the molecule
    leaves out goes (pw.x's default, not a value left over in the surface)."""
    if theirs.smearing:
        put_string(editor, "system", SMEARING, theirs.smearing)
    else:
        editor.remove("system", SMEARING)
    if theirs.degauss is None:
        editor.remove("system", "degauss")
    elif mine.degauss != theirs.degauss:
        editor.set("system", "degauss", theirs.degauss_text)


def _kept(key: str, mine: str, theirs: str) -> str:
    return _("{key}: superfície '{value}', molécula '{value_2}'; vale o da superfície").format(
        key=key, value=mine, value_2=theirs
    )


def _differences(mine: _Scheme, theirs: _Scheme) -> list[str]:
    """What differs between the two SCFs' occupations and which side applies (spec 96 R1.4)."""
    if mine.is_smearing and theirs.is_smearing:
        if mine.degauss is None and theirs.degauss is not None:
            return [
                _(
                    "degauss: a superfície não tem; valem o smearing e o degauss da molécula ('{smearing}', {degauss:g} Ry)"
                ).format(smearing=theirs.smearing_shown, degauss=theirs.degauss)
            ]
        notes = []
        if mine.family != theirs.family:
            notes.append(_kept(SMEARING, mine.smearing_shown, theirs.smearing_shown))
        if None not in (mine.degauss, theirs.degauss) and mine.degauss != theirs.degauss:
            notes.append(
                _(
                    "{key}: molécula {theirs:g} Ry, superfície {mine:g} Ry; vale o da superfície"
                ).format(key="degauss", theirs=theirs.degauss, mine=mine.degauss)
            )
        return notes
    if theirs.is_smearing:
        return [
            _(
                "occupations: superfície '{value}', molécula '{value_2}'; valem o occupations, o smearing e o degauss da molécula"
            ).format(value=mine.shown, value_2=theirs.shown)
        ]
    if mine.is_smearing or mine.kind != theirs.kind:
        return [_kept("occupations", mine.shown, theirs.shown)]
    return []
