"""Guards for the properties that make core/ portable."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "viewer3d"
CORE = sorted((SRC / "core").glob("*.py"))
ALL = sorted(SRC.rglob("*.py"))


@pytest.mark.parametrize("path", CORE, ids=lambda p: p.name)
def test_core_does_not_import_qt(path):
    text = path.read_text()
    assert not re.search(r"^\s*(from|import)\s+PyQt6", text, re.MULTILINE)


@pytest.mark.parametrize("path", sorted((SRC / "ui").glob("*.py")), ids=lambda p: p.name)
def test_ui_does_not_read_files_or_import_ase(path):
    text = path.read_text()
    assert not re.search(r"\bopen\(|read_text\(|read_bytes\(|\bimport ase\b|from ase\b", text)


@pytest.mark.parametrize("path", ALL, ids=lambda p: str(p.relative_to(SRC)))
def test_modules_stay_small(path):
    assert len(path.read_text().splitlines()) <= 400


def test_loading_a_structure_never_imports_ase_io():
    code = (
        "import sys\n"
        "from viewer3d.core.example import SI_DIAMOND_INPUT\n"
        "from viewer3d.core.qe_input import parse_input\n"
        "from viewer3d.core.bonds import bonds_for\n"
        "s = parse_input(SI_DIAMOND_INPUT); bonds_for(s)\n"
        "assert 'ase.data' in sys.modules\n"
        "assert not any(m == 'ase.io' or m.startswith('ase.io.') for m in sys.modules)\n"
        "assert 'PyQt6' not in sys.modules\n"
        "assert 'matplotlib' not in sys.modules\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
