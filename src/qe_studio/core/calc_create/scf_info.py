"""What "Criar cálculo" takes from the user's SCF input (spec 25 R4.1).

``scf_info`` reads the text with ``InputEditor`` (the derived inputs are edits of that same text) and
the crystal with ``qe.lattice`` (ASE refuses ``ibrav != 0``). Missing values are None: each
calculation type falls back to its own default. ``read_scf`` reads the file and, when the SCF has
already run next to it, the number of bands pw.x used. Workers only.
"""

from __future__ import annotations

import dataclasses
import functools
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..qe.input_edit import InputEditor, read_input_text
from ..qe.lattice import Crystal, StructureError, crystal_from_editor
from ..qe.pw_input import fortran_float
from .kpath import KMesh

__all__ = ["DEFAULT_PREFIX", "ScfInfo", "ScfInputError", "read_scf", "scf_info"]

DEFAULT_PREFIX = "pwscf"  # pw.x's when the input sets none


class ScfInputError(Exception):
    """Why the file cannot be the SCF of a new calculation, in Portuguese."""


@dataclass(frozen=True)
class ScfInfo:
    text: str
    path: Path | None = None
    prefix: str = DEFAULT_PREFIX
    outdir: str | None = None
    pseudo_dir: str | None = None
    ibrav: int | None = None
    nat: int | None = None
    ntyp: int | None = None
    ecutwfc: float | None = None
    ecutrho: float | None = None
    nspin: int = 1
    occupations: str | None = None
    smearing: str | None = None
    degauss: float | None = None
    nbnd: int | None = None
    kpoints_option: str | None = None  # of the K_POINTS card ("automatic", "gamma"…); None: no card
    kmesh: KMesh | None = None  # when the card is automatic
    species: tuple[str, ...] = ()  # ATOMIC_SPECIES labels
    crystal: Crystal | None = field(default=None, repr=False)
    structure_problem: str | None = None  # why ``crystal`` is None
    scf_bands: int | None = None  # Kohn-Sham states of the SCF's own output, when it ran
    warnings: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.path.name if self.path is not None else "SCF"

    def value(self, namelist: str, key: str) -> str | None:
        """A value of the SCF as written (no outer quotes), for the defaults of other keys."""
        return _reader(self.text).get(namelist, key)

    @property
    def spin(self) -> bool:
        """Collinear spin: bands.x runs once per channel."""
        return self.nspin == 2


@functools.lru_cache(maxsize=16)
def _reader(text: str) -> InputEditor:
    """A read-only editor of an SCF's text (never edited: ``plan`` makes its own)."""
    return InputEditor.from_text(text)


def _int(text: str | None) -> int | None:
    value = fortran_float(text) if text is not None else None
    return int(value) if value is not None and value == int(value) else None


def _float(text: str | None) -> float | None:
    return fortran_float(text) if text is not None else None


def _warnings(outdir: str | None, pseudo_dir: str | None) -> list[str]:
    out = []
    if outdir and PurePosixPath(outdir).is_absolute():
        out.append(
            f"outdir é absoluto ({outdir}): cálculos com o mesmo prefix nesse diretório se "
            "sobrescrevem"
        )
    if pseudo_dir is None:
        out.append("sem pseudo_dir: o pw.x procura os pseudopotenciais em $ESPRESSO_PSEUDO")
    elif not PurePosixPath(pseudo_dir).is_absolute() and not pseudo_dir.startswith(("~", "$")):
        out.append(
            f"pseudo_dir relativo ({pseudo_dir}): confira se ele vale a partir da pasta nova"
        )
    return out


def scf_info(text: str, path: Path | None = None) -> ScfInfo:
    """The facts of an SCF input. Raises ``ScfInputError`` when it is no pw.x SCF."""
    name = path.name if path is not None else "O arquivo"
    editor = InputEditor.from_text(text)
    if editor.issues:
        raise ScfInputError(f"{name} não pôde ser lido: {editor.issues[0]}")
    if not editor.has_namelist("system"):
        raise ScfInputError(f"{name} não é um input do pw.x (sem &SYSTEM)")
    calculation = (editor.get("control", "calculation") or "scf").strip().lower()
    if calculation != "scf":
        raise ScfInputError(f"O arquivo não é um SCF (calculation = '{calculation}')")

    def get(namelist: str, key: str) -> str | None:
        value = editor.get(namelist, key)
        return value.strip() if value is not None and value.strip() else None

    card = editor.card("K_POINTS")
    kmesh = (
        KMesh.parse(card.lines[0]) if card and card.option == "automatic" and card.lines else None
    )
    species_card = editor.card("ATOMIC_SPECIES")
    species = tuple(line.split()[0] for line in species_card.lines) if species_card else ()
    try:
        crystal, problem = crystal_from_editor(editor), None
    except StructureError as exc:
        crystal, problem = None, str(exc)
    outdir, pseudo_dir = get("control", "outdir"), get("control", "pseudo_dir")
    return ScfInfo(
        text=text,
        path=path,
        prefix=get("control", "prefix") or DEFAULT_PREFIX,
        outdir=outdir,
        pseudo_dir=pseudo_dir,
        ibrav=_int(get("system", "ibrav")),
        nat=_int(get("system", "nat")),
        ntyp=_int(get("system", "ntyp")),
        ecutwfc=_float(get("system", "ecutwfc")),
        ecutrho=_float(get("system", "ecutrho")),
        nspin=_int(get("system", "nspin")) or 1,
        occupations=(get("system", "occupations") or "").lower() or None,
        smearing=get("system", "smearing"),
        degauss=_float(get("system", "degauss")),
        nbnd=_int(get("system", "nbnd")),
        kpoints_option=card.option if card is not None else None,
        kmesh=kmesh,
        species=species,
        crystal=crystal,
        structure_problem=problem,
        warnings=tuple(_warnings(outdir, pseudo_dir)),
    )


def _bands_of_output(path: Path) -> int | None:
    """Kohn-Sham states printed by the SCF's output next to it (``X.out`` of ``X.in``)."""
    from ..sniff import FileKind, sniff

    output = path.with_suffix(".out")
    if output == path or not output.is_file():
        return None
    found = sniff(output)
    return found.pw.n_bands if found.kind is FileKind.PW_OUT and found.pw is not None else None


def read_scf(path: Path) -> ScfInfo:
    """``scf_info`` of a file, plus ``scf_bands``. Raises ``ScfInputError``. Workers only."""
    try:
        text = read_input_text(path)
    except OSError as exc:
        raise ScfInputError(f"Não foi possível ler {path.name}: {exc.strerror or exc}") from exc
    info = scf_info(text, path)
    return dataclasses.replace(info, scf_bands=_bands_of_output(path))
