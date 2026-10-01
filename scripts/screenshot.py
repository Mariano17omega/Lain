"""Render the main window off-screen to PNG (both themes) for visual checks against the mockups.

    uv run python scripts/screenshot.py [--out DIR] [--plot] [--text]

Builds a demo project from the test fixtures (01_relax, 02_scf, 03_bands, 04_pdos).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def build_project(base: Path) -> Path:
    project = base / "MoS2_monolayer"
    shutil.copytree(FIXTURES / "si_relax", project / "01_relax")
    (project / "02_scf").mkdir(parents=True)
    shutil.copy(FIXTURES / "al_bands" / "al.scf.out", project / "02_scf" / "scf.out")
    shutil.copy(FIXTURES / "al_bands" / "al.scf.in", project / "02_scf" / "scf.in")
    bands = project / "03_bands"
    bands.mkdir()
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
        ("bands.dat", "bands.dat"),
    ]:
        shutil.copy(FIXTURES / "al_bands" / old, bands / new)
    pdos = project / "04_pdos_orbitals"
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
    return project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "screenshots"))
    parser.add_argument("--plot", action="store_true", help="also generate a band plot")
    parser.add_argument(
        "--text", action="store_true", help="show an output in the text viewer, search open"
    )
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="qe-studio-shot-"))
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
    os.environ["XDG_DATA_HOME"] = str(tmp / "data")
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    project = build_project(tmp)

    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from qe_studio.core.config import LoadedConfig, parse_config
    from qe_studio.core.plotting.style import register_fonts
    from qe_studio.ui.app import install_excepthook
    from qe_studio.ui.main_window import MainWindow
    from qe_studio.ui.theme.manager import ThemeManager

    app = QApplication(sys.argv[:1])
    install_excepthook()
    register_fonts()
    config = parse_config(
        {
            "paths": {"local_root": str(project), "remote_root": "/scratch/mariano/MoS2"},
            "cluster": {"host": "10.220.200.1", "user": "mariano"},
        }
    )
    for theme_name in ("dark", "light"):
        theme = ThemeManager(theme_name)
        theme.apply(app)
        settings = QSettings(str(tmp / f"{theme_name}.ini"), QSettings.Format.IniFormat)
        window = MainWindow(LoadedConfig(config, None), theme, settings)
        window.resize(1440, 900)
        window.show()
        for folder in sorted(p for p in project.iterdir() if p.is_dir()):
            window.service.detect_now(folder)
        window.explorer.select_path(project / "03_bands")
        window.open_file(project / "03_bands" / "bands.in")
        if args.plot:
            from PyQt6.QtCore import QEventLoop, QTimer

            loop = QEventLoop()
            window.plot_ready.connect(loop.quit)
            window.plot_failed.connect(loop.quit)
            QTimer.singleShot(15000, loop.quit)
            window.generate_plot_for(project / "03_bands", auto_export=False)
            loop.exec()
        if args.text:
            from PyQt6.QtCore import QEventLoop, QTimer

            window.open_file(project / "02_scf" / "scf.out")
            viewer = window.workspace.current()
            loop = QEventLoop()
            viewer.loaded.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            viewer.search.field.setText("total energy")
            viewer.open_search()
            viewer.search.next_match()
        for _ in range(30):
            app.processEvents()
        window.service.wait(3000)
        app.processEvents()
        path = out / f"main_{theme_name}.png"
        window.grab().save(str(path))
        print(path)
        window.close()
        window.deleteLater()
        app.processEvents()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
