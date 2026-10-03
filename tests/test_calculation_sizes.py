"""Architecture rule (CLAUDE.md): no file centralizes a calculation module past ~500 lines."""

from pathlib import Path

import qe_studio.core.calculations as calculations

LIMIT = 500


def test_calculation_files_stay_under_the_size_limit():
    root = Path(calculations.__file__).parent
    long = {
        path.relative_to(root).as_posix(): lines
        for path in root.rglob("*.py")
        if (lines := len(path.read_text(encoding="utf-8").splitlines())) > LIMIT
    }
    assert not long, f"split these by responsibility (> {LIMIT} lines): {long}"
