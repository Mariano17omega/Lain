"""An SCF at the relaxed structure of a converged relax / vc-relax (spec 24 R3.3, R4).

"Gerar SCF convergido" writes ``scf_convergido_<prefix>.in`` next to the output: the relax input
with ``calculation = 'scf'``, without ``restart_mode``, ``nstep``, ``&IONS`` and ``&CELL``, and with
the final positions (and, for a vc-relax, the final cell) as the output printed them. Everything
else (pseudopotentials, ``K_POINTS``, cutoffs, ``prefix``, ``outdir``…) stays as written: the edits
go through ``InputEditor``.

Whether the context menu offers it is decided from caches (``scf_availability``); the file is
built in a worker (``generate_scf_file``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..sniff import FileKind, FileSniff, looks_like_input
from ..unique_names import write_new
from .final_structure import FinalStructure, read_final_structure
from .input_edit import InputEditor

if TYPE_CHECKING:
    from ..calculations.base import DetectionResult

RELAX = ("relax", "vc-relax")
SCF_STEM = "scf_convergido"
SEP = "_"  # between the stem and the prefix (spec 24, assumed decision 1)
DEFAULT_PREFIX = "pwscf"  # pw.x's when the input sets none
NO_INPUT = "Input do relax não encontrado na pasta"
# The cell's geometry, which CELL_PARAMETERS replaces once ibrav = 0 (an ``alat`` cell keeps
# celldm(1): it is the unit of its rows).
_CELL_KEYS = frozenset({"a", "b", "c", "cosab", "cosac", "cosbc"})
_CELLDM = re.compile(r"celldm\((\d)\)")
_UNSAFE = re.compile(r"[\\/\0]")


class ScfError(Exception):
    """Why the SCF cannot be generated, in Portuguese: shown as is."""


@dataclass(frozen=True)
class ScfResult:
    text: str
    prefix: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedScf:
    path: Path
    warnings: tuple[str, ...] = ()


# -- what the menu offers (caches only) -------------------------------------------------------------
def can_generate_scf(sniff: FileSniff | None) -> bool:
    """A pw.x relax / vc-relax output whose geometry is known to have converged and whose run
    ended. A huge output whose 1 MB tail missed the BFGS marker does not count (R3.3)."""
    if sniff is None or sniff.kind is not FileKind.PW_OUT or sniff.pw is None:
        return False
    pw = sniff.pw
    return sniff.calculation in RELAX and pw.geometry_converged is True and pw.job_done


def pair_input(output: Path, results: Iterable[DetectionResult] | None) -> Path | None:
    """The input of ``output``: the same name with ``.in`` (when it is a QE input), else the
    ``relax_in`` of the folder's detection, if that result's output is this one."""
    same = output.with_suffix(".in")
    if same != output and same.is_file() and looks_like_input(same):
        return same
    for result in results or ():
        found = result.file("relax_in")
        if found is not None and result.file("relax_out") == output:
            return found
    return None


def _not_relax(name: str, calculation: str | None) -> str:
    return f"{name} não é um relax/vc-relax (calculation = '{calculation or 'scf'}')"


def pair_problem(pair: Path | None, sniff: FileSniff | None) -> str:
    """Why the paired input cannot be used ("" when it can). A missing or unreadable sniff is no
    objection: the worker reads the input anyway."""
    if pair is None:
        return NO_INPUT
    if sniff is not None and sniff.kind is FileKind.PW_IN and sniff.calculation not in RELAX:
        return _not_relax(pair.name, sniff.calculation)
    if sniff is not None and sniff.kind not in (FileKind.PW_IN, FileKind.UNKNOWN):
        return f"{pair.name} não é um input do pw.x"
    return ""


def scf_availability(
    output: Path,
    sniff: FileSniff | None,
    results: Iterable[DetectionResult] | None,
    sniff_of: Callable[[Path], FileSniff | None],
) -> str | None:
    """The "Gerar SCF convergido" item of ``output``: None hides it, "" enables it, and any other
    text disables it with that tooltip. Reads caches, and at most the head of the paired input."""
    if not can_generate_scf(sniff):
        return None
    pair = pair_input(output, results)
    return pair_problem(pair, sniff_of(pair) if pair is not None else None)


# -- the SCF ----------------------------------------------------------------------------------------
def _int(text: str | None) -> int | None:
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def scf_from_relax(final: FinalStructure, in_text: str, name: str = "O input") -> ScfResult:
    """The relax input ``in_text`` turned into an SCF at ``final``. Raises ``ScfError`` (nothing
    to write) when the input is no relax or its ``nat`` disagrees with the output."""
    editor = InputEditor.from_text(in_text)
    calculation = (editor.get("control", "calculation") or "scf").lower()
    if calculation not in RELAX:
        raise ScfError(_not_relax(name, calculation))
    nat, count = _int(editor.get("system", "nat")), len(final.positions.lines)
    if nat != count:
        raise ScfError(
            f"nat = {nat if nat is not None else '?'} no input, {count} posições na saída"
        )

    warnings: list[str] = []
    written = editor.raw("control", "calculation") or ""
    quote = written[0] if written[:1] in ("'", '"') else "'"
    editor.set("control", "calculation", f"{quote}scf{quote}")
    for key in ("restart_mode", "nstep"):
        editor.remove("control", key)
    for namelist in ("ions", "cell"):
        while editor.remove_namelist(namelist):  # every one: a repeated &ions too
            pass
    editor.replace_card("ATOMIC_POSITIONS", final.positions.unit, list(final.positions.lines))
    if calculation == "vc-relax":
        _final_cell(editor, final, warnings)
    if editor.issues:
        raise ScfError(f"Não foi possível montar o SCF: {editor.issues[0]}")
    return ScfResult(editor.text(), editor.get("control", "prefix"), tuple(warnings))


def _final_cell(editor: InputEditor, final: FinalStructure, warnings: list[str]) -> None:
    """The vc-relax's cell as printed, with ibrav = 0 (decision 5 of the spec)."""
    cell = final.cell
    if cell is None:
        raise ScfError("A saída não traz a célula final (CELL_PARAMETERS) do vc-relax")
    if final.positions.unit == "alat" and cell.unit != "alat":
        raise ScfError(
            f"Posições em alat com a célula em {cell.unit}: o alat do SCF seria outro "
            "e o Lain não converte unidades"
        )
    if cell.unit == "alat" and cell.alat is None:
        raise ScfError("CELL_PARAMETERS (alat) sem o valor de alat na saída")
    ibrav = editor.get("system", "ibrav")
    editor.replace_card("CELL_PARAMETERS", cell.unit, list(cell.rows))
    editor.set("system", "ibrav", "0")
    if ibrav is not None and ibrav.strip() != "0":
        warnings.append(
            f"ibrav = {ibrav.strip()} trocado por 0: a célula final vai em CELL_PARAMETERS"
        )
    for key in editor.keys("system"):
        celldm = _CELLDM.fullmatch(key)
        if key in _CELL_KEYS or (celldm and not (cell.unit == "alat" and celldm.group(1) == "1")):
            editor.remove("system", key)
    if cell.unit == "alat" and cell.alat is not None:
        editor.set("system", "celldm(1)", cell.alat)  # the unit of the rows, as printed


def scf_name(prefix: str | None) -> str:
    """``scf_convergido_<prefix>.in`` (``pwscf`` without a prefix, as pw.x)."""
    clean = _UNSAFE.sub("_", (prefix or "").strip()) or DEFAULT_PREFIX
    return f"{SCF_STEM}{SEP}{clean}.in"


def _read_input(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:  # an old latin-1 comment: keep its characters
        return raw.decode("latin-1")


def generate_scf_file(output: Path, results: Iterable[DetectionResult] | None) -> GeneratedScf:
    """Write the SCF of ``output`` in its folder under the first free name (never over a file).
    Raises ``ScfError`` and writes nothing when it cannot. Workers only: reads both files."""
    pair = pair_input(output, results)
    if pair is None:
        raise ScfError(NO_INPUT)
    try:
        in_text = _read_input(pair)
        final = read_final_structure(output)
    except OSError as exc:
        name = Path(exc.filename).name if exc.filename else output.name
        raise ScfError(f"Não foi possível ler {name}: {exc.strerror or exc}") from exc
    if final is None:
        raise ScfError(
            f"{output.name} não tem o bloco final de coordenadas (Begin final coordinates)"
        )
    result = scf_from_relax(final, in_text, pair.name)
    name = scf_name(result.prefix)
    try:
        path = write_new(output.parent / name, result.text)
    except OSError as exc:
        raise ScfError(f"Não foi possível gravar {name}: {exc.strerror or exc}") from exc
    return GeneratedScf(path, result.warnings)
