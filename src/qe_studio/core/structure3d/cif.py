"""A CIF of a pw.x input's structure (spec 74): P1, every atom, built by hand.

The text is a data file, so it does not change with the interface language. Fractions are written
as the input has them (not wrapped into [0, 1)).
"""

from __future__ import annotations

import re
from pathlib import Path

from ...i18n import _
from ..files.unique_names import write_new
from .elements import symbol_from_label
from .model import Structure
from .source import StructureReadError, read_structure

__all__ = ["CifError", "cif_text", "write_cif"]

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


class CifError(Exception):
    """Why a CIF cannot be written, in Portuguese."""


def _site_label(label: str, number: int) -> str:
    """``O43``: the input's label and the atom's number, the 3D window's name. A label that ends in a
    digit takes ``_``: ``O1`` + 12 and ``O11`` + 2 would both be ``O112``. The number is then always the
    last digits, and no two atoms have one number."""
    return f"{label}_{number}" if label[-1:].isdigit() else f"{label}{number}"


def cif_text(structure: Structure) -> str:
    symbols = []
    for label in structure.labels:
        symbol = symbol_from_label(label)
        if symbol is None:
            raise CifError(
                _(
                    "O rótulo {label} não corresponde a um elemento: "
                    "o CIF precisa do símbolo químico"
                ).format(label=label)
            )
        symbols.append(symbol)
    a, b, c, alpha, beta, gamma = structure.lattice_parameters
    source = structure.source
    origin = Path(source.path).name if source.path else "input"
    lines = [
        f"# Gerado pelo Lain a partir de {origin}",
        f"data_{_UNSAFE.sub('_', source.prefix)}",
        "_symmetry_space_group_name_H-M 'P 1'",
        "_symmetry_Int_Tables_number 1",
        f"_cell_length_a {a:.8f}",
        f"_cell_length_b {b:.8f}",
        f"_cell_length_c {c:.8f}",
        f"_cell_angle_alpha {alpha:.8f}",
        f"_cell_angle_beta {beta:.8f}",
        f"_cell_angle_gamma {gamma:.8f}",
        f"_cell_volume {structure.volume:.8f}",
        f"_chemical_formula_sum '{structure.formula}'",
        "loop_",
        "_symmetry_equiv_pos_as_xyz",
        "'x, y, z'",
        "loop_",
        "_atom_site_label",
        "_atom_site_type_symbol",
        "_atom_site_fract_x",
        "_atom_site_fract_y",
        "_atom_site_fract_z",
        "_atom_site_occupancy",
    ]
    for number, (label, symbol, frac) in enumerate(
        zip(structure.labels, symbols, structure.frac, strict=True), start=1
    ):
        x, y, z = (f"{value:.8f}" for value in frac)
        lines.append(f"{_site_label(label, number)} {symbol} {x} {y} {z} 1.0")
    return "\n".join(lines) + "\n"


def write_cif(path: Path) -> Path:
    """Write the CIF of the input ``path`` beside it (``si.scf.in`` → ``si.scf.cif``, ``_2``… if
    taken) and return where it went. Workers only: it reads and writes files."""
    path = Path(path)
    try:
        structure = read_structure(path)
    except StructureReadError as exc:
        raise CifError(str(exc)) from exc
    return write_new(path.with_suffix(".cif"), cif_text(structure), first=2)
