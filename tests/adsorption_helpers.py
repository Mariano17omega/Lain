"""SCF runs for the adsorption-energy tests (specs 78 and 97), always copied out of the fixtures."""

import shutil
from collections.abc import Callable
from pathlib import Path

from conftest import FIXTURES

SOURCES = {"si": "si_bands", "al": "al_bands", "ni": "qe731_ni_spin_fixed"}
SI = FIXTURES / "si_bands"
SI_ATOMS_LINE = 43  # "number of atoms/cell = 2" in si.scf.out
SI_SECOND_SITE = 89  # "tau(   2)"
SI_PSEUDO_FILE = 70  # ".../Si.pz-rrkj.UPF"


def copy_scf_outputs(folder: Path) -> Path:
    """The three SCF runs of spec 78 (input and output) side by side in ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    for stem, source in SOURCES.items():
        for suffix in (".in", ".out"):
            shutil.copy(FIXTURES / source / f"{stem}.scf{suffix}", folder / f"{stem}.scf{suffix}")
    return folder


def scf_paths(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.scf.out"))


def si_copy(
    folder: Path,
    name: str,
    *,
    one_atom: bool = False,
    edit: Callable[[list[str]], None] | None = None,
) -> Path:
    """``si.scf.in`` and ``si.scf.out`` as ``<name>.scf.*`` with ``prefix='<name>'``. ``one_atom``
    drops the second site and says ``number of atoms/cell = 1``; ``edit`` changes the output's lines
    (0-based list, ``keepends``) before that."""
    folder.mkdir(parents=True, exist_ok=True)
    text = (SI / "si.scf.in").read_text()
    assert "prefix='silicon'" in text
    (folder / f"{name}.scf.in").write_text(text.replace("prefix='silicon'", f"prefix='{name}'"))
    lines = (SI / "si.scf.out").read_text().splitlines(keepends=True)
    if edit is not None:
        edit(lines)
    if one_atom:
        assert "number of atoms/cell" in lines[SI_ATOMS_LINE - 1]
        assert "tau(   2)" in lines[SI_SECOND_SITE - 1]
        lines[SI_ATOMS_LINE - 1] = "     number of atoms/cell      =            1\n"
        del lines[SI_SECOND_SITE - 1]
    out = folder / f"{name}.scf.out"
    out.write_text("".join(lines))
    return out


def coherent_set(folder: Path, *, big_atoms: int = 2) -> list[Path]:
    """``big`` (Si₂, or Si₁ with ``big_atoms=1``), ``small`` and ``atom`` (Si₁): one level of theory.
    The tie between ``atom`` and ``small`` goes by the file's name: ``atom`` is the substrate."""
    return [
        si_copy(folder, "big", one_atom=big_atoms == 1),
        si_copy(folder, "small", one_atom=True),
        si_copy(folder, "atom", one_atom=True),
    ]
