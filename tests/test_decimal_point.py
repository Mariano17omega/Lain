"""The decimal separator of Lain is the point, as QE reads it (CLAUDE.md, "Numbers"): the reports and
messages of "Criar cálculo", the text of a site's coordinates and the literals in the code. A comma
typed by the user is still read as a point. The one exception is the CSV export (spec 32)."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable

import numpy as np
import pytest

from i18n_static import python_files
from qe_studio.core.calc_create.surface.adsorb import _number_text, parse_coords
from qe_studio.core.calc_create.surface.report import REPORT_KEY, decimal
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.plotting.table import Column, PlotTable, cell, to_csv

from calc_helpers import JOBS
from surface_helpers import BULK, MOLECULE, SLAB_001, SUPERCELL_001, read

# The files allowed a decimal comma in code, with the reason.
CSV_EXCEPTION = {"core/plotting/table.py"}  # Excel and Origin in pt-BR read the CSV so (spec 32)
COMMA_BETWEEN_DIGITS = re.compile(r"\d,\d")
COMMA_WITH_UNIT = re.compile(r"\d,\d+ ?(Å|eV|Ry)\b")


def test_decimal_writes_a_point():
    assert decimal(15.098) == "15.10"
    assert decimal(1.85, 1) == "1.9"
    assert decimal(0.9743, 3) == "0.974"
    assert decimal(12) == "12.00"


def test_the_coordinates_of_a_site_are_shown_with_a_point():
    assert _number_text(np.array([0.25, 0.5, 0.75])) == "0.25 0.5 0.75"


@pytest.mark.parametrize("typed", ["0.25 0.5 0.75", "0,25 0,5 0,75", "0,25; 0.5; 0,75"])
def test_a_comma_typed_is_read_as_a_point(typed):
    """What the keyboard of a Portuguese locale types is accepted; only what Lain writes changes."""
    found = parse_coords(typed)
    assert found is not None and np.allclose(found, [0.25, 0.5, 0.75])


def surface_plans():
    """A Slab with a molecule, a supercell and a molecule on a surface, as the tests of their types
    build them: the three that write a ``geracao.md`` and notes with numbers."""
    return {
        "slab": by_id("slab").plan(read(BULK), {"molecule": read(MOLECULE)}, JOBS, "avancado"),
        "supercell": by_id("supercell").plan(read(SLAB_001), {}, JOBS, "avancado"),
        "adsorption": by_id("adsorption").plan(
            read(SUPERCELL_001),
            {"molecule": read(MOLECULE), "site": (43,), "remove_h": True},
            JOBS,
            "avancado",
        ),
    }


@pytest.mark.parametrize("name", ["slab", "supercell", "adsorption"])
def test_the_report_and_the_notes_of_a_surface_type_use_the_point(name):
    result = surface_plans()[name]
    assert result.errors == ()
    report = result.by_key(REPORT_KEY)
    assert report is not None
    shown = "\n".join([report.text, *result.notes])
    assert re.search(r"\d\.\d", shown)  # there are numbers to look at
    assert COMMA_BETWEEN_DIGITS.search(shown) is None, COMMA_BETWEEN_DIGITS.search(shown)


def comma_decimals_in_code(files: Iterable[tuple[str, str]] | None = None) -> list[str]:
    """``(source, name)`` of ``files`` (default: every module of the package) that write a decimal
    comma, as ``name:line: what``."""
    found = []
    for text, name in python_files() if files is None else files:
        if name in CSV_EXCEPTION:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                words = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if node.func.attr == "replace" and words == [".", ","]:
                    found.append(f"{name}:{node.lineno}: replace('.', ',') writes a decimal comma")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and COMMA_WITH_UNIT.search(node.value)
            ):
                match = COMMA_WITH_UNIT.search(node.value)
                assert match is not None
                found.append(f"{name}:{node.lineno}: {match.group(0)!r} in a text")
    return found


def test_no_decimal_comma_is_written_in_the_code():
    """A new ``.replace(".", ",")`` or a ``0,05 eV`` in a message fails here; the CSV is the one
    exception, and the next test says why it stays."""
    assert comma_decimals_in_code() == []


def test_the_guard_sees_a_decimal_comma():
    """The scan above is not blind: it reports both forms on a source that has them, and lets the
    reading of a comma (``replace(",", ".")``) and the CSV pass."""
    sample = (
        'x = f"{v:.1f}".replace(".", ",")\n'
        'message = "pelo menos 0,05 eV de gap"\n'
        'y = typed.replace(",", ".")\n'
    )
    found = comma_decimals_in_code([(sample, "core/sample.py"), (sample, *CSV_EXCEPTION)])
    assert len(found) == 2
    assert "replace('.', ',')" in found[0] and "'0,05 eV'" in found[1]


def test_the_csv_keeps_its_decimal_comma():
    """The exception is deliberate (spec 32): the file is for a spreadsheet in pt-BR, not for QE."""
    assert cell(0.5) == "0,5" and cell(-2.25) == "-2,25"
    table = PlotTable.of([Column("x", np.array([0.5, 1.25]))])
    assert to_csv(table) == "x\n0,5\n1,25\n"
