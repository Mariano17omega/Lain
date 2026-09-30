import os
import shutil
from pathlib import Path

import pytest

# Must be set before any PyQt6 import so tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(items):
    # Last, so the fixtures check also sees what this run's tests wrote.
    items.sort(key=lambda item: item.name == "test_fixtures_are_untouched")


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


@pytest.fixture
def demo_project(tmp_path) -> Path:
    """Project tree like the mockup: 01_relax, 02_scf, 03_bands (PRD names), 04_pdos."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "si_relax", project / "01_relax")
    (project / "02_scf").mkdir()
    shutil.copy(FIXTURES / "al_bands/al.scf.out", project / "02_scf/scf.out")
    bands = project / "03_bands"
    bands.mkdir()
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
    ]:
        shutil.copy(FIXTURES / "al_bands" / old, bands / new)
    pdos = project / "04_pdos"
    (pdos / "orbitals").mkdir(parents=True)
    src = FIXTURES / "al_pdos_flat"
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.nscf.out", "nscf.out"),
        ("al.projwfc.out", "projwfc.out"),
        ("pdos.dat.pdos_tot", "pdos.dat.pdos_tot"),
    ]:
        shutil.copy(src / old, pdos / new)
    for path in src.glob("*pdos_atm*"):
        shutil.copy(path, pdos / "orbitals" / path.name)
    (project / "03_bands" / "tmp").mkdir()
    return project


@pytest.fixture
def main_window(qtbot, demo_project, tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QMenu

    def blocking_menu(menu, *args):
        # A real popup would wait for a click forever (pytest-timeout cannot interrupt it).
        raise AssertionError("QMenu.exec would block the test; patch it")

    monkeypatch.setattr(QMenu, "exec", blocking_menu)

    from qe_studio.core.config import LoadedConfig, parse_config
    from qe_studio.core.detection import FolderMemory
    from qe_studio.ui.main_window import MainWindow
    from qe_studio.ui.theme.manager import ThemeManager

    config = parse_config({"paths": {"local_root": str(demo_project)}})
    theme = ThemeManager("dark")
    theme.apply()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(
        LoadedConfig(config, None), theme, settings, FolderMemory(tmp_path / "memory.json")
    )
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()
