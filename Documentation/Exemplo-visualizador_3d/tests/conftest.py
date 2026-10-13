import os
from pathlib import Path

# Must run before any Qt platform plugin is loaded.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from viewer3d.core.example import SI_DIAMOND_INPUT  # noqa: E402
from viewer3d.core.qe_input import parse_input, read_structure  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="session")
def si():
    return parse_input(SI_DIAMOND_INPUT)


@pytest.fixture(scope="session")
def h3chg():
    from helpers import h3chg_input

    return parse_input(h3chg_input())


@pytest.fixture(scope="session")
def kaolinite():
    return read_structure(SAMPLES / "scf.in")
