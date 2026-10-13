"""Tolerant reader of pw.x inputs: ``Structure`` or ``StructureError``, never an exception."""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from viewer3d.core.elements import element_for_label
from viewer3d.core.lattice import BOHR, LatticeError, celldm_from_abc, latgen
from viewer3d.core.qe_lexer import Card, RawInput, split_input
from viewer3d.core.structure import SourceInfo, SpeciesInfo, Structure, StructureError

__all__ = ["StructureError", "parse_input", "read_structure"]

_POSITION_UNITS = ("alat", "bohr", "angstrom", "crystal")
_ALAT_VALUE = re.compile(r"alat\s*=?\s*([^\s]+)", re.IGNORECASE)
_KEYED = re.compile(r"(starting_magnetization|hubbard_u)\((\d+)\)")


class _Fail(Exception):
    """Fatal problem with the input; the message is already in Portuguese."""


def _number(text: str) -> float:
    """Fortran-style real: ``1.0D-6``, ``1.d-8``, ``.5``, ``10.2_dp``."""
    cleaned = re.sub(r"_\w+$", "", text.strip().lower()).replace("d", "e")
    return float(cleaned)


def _real(values: dict[str, str], key: str) -> float | None:
    if key not in values:
        return None
    try:
        return _number(values[key])
    except ValueError:
        raise _Fail(f"valor inválido para {key} em &SYSTEM: '{values[key]}'") from None


def _integer(values: dict[str, str], key: str, what: str) -> int:
    if key not in values:
        raise _Fail(f"{what} ausente ou inválido (nenhum valor de {key} em &SYSTEM)")
    try:
        number = _number(values[key])
    except ValueError:
        number = float("nan")
    if not np.isfinite(number) or number != int(number):
        raise _Fail(f"{what} ausente ou inválido (valor: '{values[key]}')")
    return int(number)


def _rows(card: Card) -> list[tuple[int, list[str]]]:
    return [(number, text.split()) for number, text in card.lines]


def _vectors(card: Card) -> np.ndarray:
    rows = _rows(card)
    if len(rows) < 3:
        raise _Fail(f"CELL_PARAMETERS incompleto: {len(rows)} linhas em vez de 3")
    out = []
    for number, tokens in rows[:3]:
        try:
            out.append([_number(t) for t in tokens[:3]])
        except ValueError:
            raise _Fail(f"CELL_PARAMETERS: linha {number} inválida") from None
        if len(out[-1]) != 3:
            raise _Fail(f"CELL_PARAMETERS: linha {number} precisa de 3 números")
    return np.array(out, dtype=float)


def _cell_bohr(
    raw: RawInput, ibrav: int, celldm: tuple[float, ...], warnings: list[str]
) -> tuple[np.ndarray, float]:
    """Cell (rows, bohr) and ``alat`` (bohr)."""
    card = raw.cards.get("CELL_PARAMETERS")
    if ibrav != 0:
        if card is not None:
            warnings.append("CELL_PARAMETERS ignorado: ibrav diferente de 0")
        if celldm[0] <= 0:
            raise _Fail(f"ibrav = {ibrav} exige celldm(1) ou A em &SYSTEM")
        return latgen(ibrav, celldm), celldm[0]
    if card is None:
        raise _Fail("ibrav = 0 exige o card CELL_PARAMETERS (ausente)")
    vectors = _vectors(card)
    option = card.option
    explicit = None
    if "alat" in option:
        found = _ALAT_VALUE.search(option)
        if found and re.search(r"\d", found.group(1)):
            try:
                explicit = _number(found.group(1))
            except ValueError:
                raise _Fail(f"CELL_PARAMETERS: alat inválido em '({option})'") from None
        unit = "alat"
    elif option in ("bohr", "angstrom"):
        unit = option
    elif option == "":
        unit = "alat" if celldm[0] > 0 else "bohr"
        warnings.append(f"CELL_PARAMETERS sem unidade: assumido {unit}")
    else:
        raise _Fail(f"CELL_PARAMETERS: unidade desconhecida '{option}'")
    if unit == "alat":
        alat = explicit if explicit is not None else celldm[0]
        if alat <= 0:
            raise _Fail("CELL_PARAMETERS em alat exige celldm(1), A ou (alat= valor)")
        return vectors * alat, alat
    cell = vectors if unit == "bohr" else vectors / BOHR
    if celldm[0] > 0:
        warnings.append(f"celldm(1) com CELL_PARAMETERS em {unit}: usado só como alat")
        return cell, celldm[0]
    return cell, float(np.linalg.norm(cell[0]))


def _species(raw: RawInput, ntyp: int | None, warnings: list[str]) -> list[SpeciesInfo]:
    card = raw.cards.get("ATOMIC_SPECIES")
    if card is None:
        return []
    rows = _rows(card)
    if ntyp and 0 < ntyp < len(rows):
        rows = rows[:ntyp]
    species: list[SpeciesInfo] = []
    for number, tokens in rows:
        mass = None
        if len(tokens) > 1:
            try:
                mass = _number(tokens[1])
            except ValueError:
                warnings.append(f"ATOMIC_SPECIES: massa inválida na linha {number}")
        pseudo = tokens[2] if len(tokens) > 2 else None
        species.append(SpeciesInfo(tokens[0], mass, pseudo, len(species) + 1))
    return species


def _positions(raw: RawInput, nat: int, warnings: list[str]):
    card = raw.cards.get("ATOMIC_POSITIONS")
    if card is None:
        raise _Fail("sem ATOMIC_POSITIONS")
    unit = card.option.split()[0] if card.option else ""
    if unit == "crystal_sg":
        raise _Fail("ATOMIC_POSITIONS crystal_sg não é suportado")
    if unit == "":
        unit = "alat"
        warnings.append("ATOMIC_POSITIONS sem unidade: assumido alat")
    elif unit not in _POSITION_UNITS:
        raise _Fail(f"ATOMIC_POSITIONS: unidade desconhecida '{unit}'")
    rows = _rows(card)
    if len(rows) < nat:
        raise _Fail(f"nat = {nat}, mas ATOMIC_POSITIONS tem {len(rows)} linhas")
    if len(rows) > nat:
        warnings.append(
            f"ATOMIC_POSITIONS tem {len(rows)} linhas, mais que nat = {nat}: extras ignoradas"
        )
    labels, coords, flags = [], [], []
    for number, tokens in rows[:nat]:
        try:
            if len(tokens) < 4:
                raise ValueError
            xyz = [_number(t) for t in tokens[1:4]]
        except ValueError:
            text = " ".join(tokens)
            raise _Fail(f"ATOMIC_POSITIONS: linha {number} inválida: '{text}'") from None
        flag = None
        if len(tokens) >= 7:
            try:
                flag = tuple(int(_number(t)) for t in tokens[4:7])
            except ValueError:
                warnings.append(f"ATOMIC_POSITIONS: if_pos inválido na linha {number}")
        elif len(tokens) > 4:
            warnings.append(f"ATOMIC_POSITIONS: if_pos incompleto na linha {number}")
        labels.append(tokens[0])
        coords.append(xyz)
        flags.append(flag)
    return unit, labels, np.array(coords, dtype=float), flags


def _build(raw: RawInput, path: str | None) -> Structure:
    warnings: list[str] = []
    system = raw.namelists.get("system")
    if system is None:
        raise _Fail("namelist &SYSTEM ausente")
    control = raw.namelists.get("control", {})

    ibrav = _integer(system, "ibrav", "ibrav")
    nat = _integer(system, "nat", "nat")
    if nat < 1:
        raise _Fail(f"nat ausente ou inválido (valor: {nat})")
    ntyp = None
    if "ntyp" in system:
        try:
            ntyp = int(_number(system["ntyp"]))
        except ValueError:
            warnings.append(f"ntyp inválido: '{system['ntyp']}'")

    celldm = tuple(_real(system, f"celldm({i})") or 0.0 for i in range(1, 7))
    if "celldm(1)" in system and celldm[0] <= 0:
        raise _Fail(f"celldm(1) deve ser positivo (valor: {celldm[0]})")
    a_ang = _real(system, "a") or 0.0
    if a_ang > 0 and celldm[0] > 0:
        warnings.append("A e celldm(1) definidos: celldm(1) tem prioridade")
    elif a_ang > 0:
        celldm = celldm_from_abc(
            ibrav,
            a_ang,
            _real(system, "b") or 0.0,
            _real(system, "c") or 0.0,
            _real(system, "cosab") or 0.0,
            _real(system, "cosac") or 0.0,
            _real(system, "cosbc") or 0.0,
        )
    cell_bohr, alat_bohr = _cell_bohr(raw, ibrav, celldm, warnings)
    cell = cell_bohr * BOHR
    if abs(np.linalg.det(cell)) < 1e-8:
        raise _Fail("célula com volume nulo")

    unit, labels, coords, flags = _positions(raw, nat, warnings)
    if unit == "crystal":
        frac = coords
    else:
        scale = {"alat": alat_bohr * BOHR, "bohr": BOHR, "angstrom": 1.0}[unit]
        frac = np.linalg.solve(cell.T, (coords * scale).T).T

    species = _species(raw, ntyp, warnings)
    if not species:
        warnings.append("ATOMIC_SPECIES ausente: espécies deduzidas das posições")
    known = {s.label for s in species}
    for label in labels:
        if label not in known:
            if species:
                warnings.append(f"rótulo '{label}' não está em ATOMIC_SPECIES")
            species.append(SpeciesInfo(label, None, None, len(species) + 1))
            known.add(label)
    if ntyp is not None and ntyp != len(species):
        warnings.append(f"ntyp = {ntyp}, mas há {len(species)} espécies")
    for s in species:
        if not element_for_label(s.label).known:
            warnings.append(f"espécie '{s.label}': elemento não reconhecido (cinza, raio 1.0 Å)")
    if "HUBBARD" in raw.cards:
        warnings.append("card HUBBARD presente: não interpretado")

    magnetization: dict[int, float] = {}
    hubbard: dict[int, float] = {}
    for key, value in system.items():
        match = _KEYED.fullmatch(key)
        if match:
            try:
                target = magnetization if match.group(1) == "starting_magnetization" else hubbard
                target[int(match.group(2))] = _number(value)
            except ValueError:
                warnings.append(f"valor inválido para {key}: '{value}'")
    try:
        nspin = int(_number(system.get("nspin", "1")))
    except ValueError:
        nspin = 1

    source = SourceInfo(
        path=path,
        ibrav=ibrav,
        nat=nat,
        ntyp=ntyp,
        prefix=control.get("prefix", "pwscf"),
        calculation=control.get("calculation", "scf"),
        nspin=nspin,
        alat_bohr=alat_bohr,
        celldm=celldm,
        starting_magnetization=magnetization,
        hubbard_u=hubbard,
        warnings=tuple(warnings),
    )
    return Structure(cell, tuple(labels), frac, tuple(flags), tuple(species), source)


def parse_input(text: str, path: str | None = None) -> Structure | StructureError:
    """Parse the text of a pw.x input."""
    try:
        return _build(split_input(text), path)
    except _Fail as exc:
        return StructureError(str(exc))
    except LatticeError as exc:
        return StructureError(str(exc))
    except Exception as exc:  # safety net: the GUI must never see a traceback
        return StructureError(f"erro inesperado ao ler o input ({type(exc).__name__}: {exc})")


def read_structure(path: str | os.PathLike[str]) -> Structure | StructureError:
    """Read a pw.x input file."""
    try:
        text = Path(path).read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return StructureError(f"arquivo não encontrado: {path}")
    except OSError as exc:
        return StructureError(f"não foi possível ler o arquivo ({exc.strerror or exc})")
    if not text.strip():
        return StructureError("arquivo vazio")
    return parse_input(text, str(path))
