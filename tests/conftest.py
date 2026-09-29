import os
import shutil
from pathlib import Path

import pytest

# Must be set before any PyQt6 import so tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path_factory, monkeypatch):
    """Keep app data/config/cache writes out of the real home directory."""
    base = tmp_path_factory.mktemp("userdirs")
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(var, str(base / var.lower()))


def copy_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(FIXTURES / name, target)
    return target


@pytest.fixture
def al_pdos_orbitals(tmp_path) -> Path:
    """Al PDOS files rearranged into the PRD layout (scf/nscf/projwfc names + orbitals/)."""
    src = FIXTURES / "al_pdos_flat"
    folder = tmp_path / "04_pdos"
    (folder / "orbitals").mkdir(parents=True)
    shutil.copy(src / "al.scf.out", folder / "scf.out")
    shutil.copy(src / "al.nscf.out", folder / "nscf.out")
    shutil.copy(src / "al.projwfc.out", folder / "projwfc.out")
    shutil.copy(src / "pdos.dat.pdos_tot", folder / "pdos.dat.pdos_tot")
    for path in src.glob("*pdos_atm*"):
        shutil.copy(path, folder / "orbitals" / path.name)
    return folder
