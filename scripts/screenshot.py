"""Render the main window off-screen to PNG (both themes) for visual checks against the mockups.

    uv run python scripts/screenshot.py [--out DIR] [--plot] [--text] [--input] [--diff] [--summary] [--spin] [--nav] [--scale N]

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


def write_inputs(project: Path) -> tuple[Path, Path, Path]:
    """An input with write errors and a changed copy of the SCF input, for --input and --diff."""
    scf = project / "02_scf" / "scf.in"
    text = scf.read_text()
    broken = project / "02_scf" / "scf_broken.in"
    broken.write_text(
        text.replace("prefix='al',", "prefix='al,").replace("ecutwfc = 100,", "ecutwfc = 100e,")
        .replace("&electrons", "&electron").replace("K_POINTS automatic", "K_POINTS automatc")
    )  # fmt: skip
    changed = project / "02_scf" / "scf_ecut.in"
    changed.write_text(
        text.replace("ecutwfc = 100", "ecutwfc = 80").replace("1.0d-8", "1.0e-8")
        .replace("10 10 10 0 0 0", "8 8 8 0 0 0").replace("calculation = 'scf'", "calculation = 'scf' ! test")
    )  # fmt: skip
    return scf, broken, changed


def wait_for(signal, timeout_ms: int = 5000) -> None:
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def show_navigation(window, project: Path, app) -> None:
    """Spec 16: a deep folder (narrow breadcrumb), favorites, recents, a filter and a selection."""
    from PyQt6.QtCore import QItemSelectionModel

    deep = project / "runs" / "2026" / "campaign" / "a"  # long enough to collapse
    deep.mkdir(parents=True, exist_ok=True)
    for folder in (project / "02_scf", project / "04_pdos_orbitals"):
        window.navigation.set_favorite(folder, True)
    for folder in (project / "01_relax", project / "02_scf", project / "04_pdos_orbitals"):
        window.explorer.select_path(folder)
    window.explorer.select_path(deep)
    window.top_bar.breadcrumb.setFixedWidth(250)
    window.explorer.select_path(project / "03_bands")
    window.top_bar.breadcrumb.setFixedWidth(250)
    for _ in range(10):
        app.processEvents()
    bar = window.files.filter_bar
    bar.open()
    bar.field.setText("out")
    bar._actions[("states", "OK")].setChecked(True)
    bar.flush()
    selection = window.files.view.selectionModel()
    for row in range(window.files.proxy.rowCount(window.files.view.rootIndex())):
        index = window.files.proxy.index(row, 0, window.files.view.rootIndex())
        if not window.files.proxy.is_up(index):
            selection.select(index, QItemSelectionModel.SelectionFlag.Select)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "screenshots"))
    parser.add_argument(
        "--scale", type=float, default=1.0, help="ui.font_scale, 0.8 to 1.6 (spec 19)"
    )
    parser.add_argument("--plot", action="store_true", help="also generate a band plot")
    parser.add_argument(
        "--spin", action="store_true", help="plot the spin-polarized bands (Ni, spec 13)"
    )
    parser.add_argument(
        "--text", action="store_true", help="show an output in the text viewer, search open"
    )
    parser.add_argument("--input", action="store_true", help="an input with write errors (spec 11)")
    parser.add_argument(
        "--diff", nargs="?", const="params", choices=["params", "text"],
        help="compare two inputs in the diff tab (spec 11)",
    )  # fmt: skip
    parser.add_argument(
        "--summary", action="store_true", help="the summary tab of the vc-relax output (spec 12)"
    )
    parser.add_argument(
        "--nav", action="store_true",
        help="breadcrumb, favorites, recents, grid filter and multi-selection (spec 16)",
    )  # fmt: skip
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="qe-studio-shot-"))
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
    os.environ["XDG_DATA_HOME"] = str(tmp / "data")
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    project = build_project(tmp)
    if args.spin:
        shutil.copytree(FIXTURES / "qe731_ni_spin_bands", project / "05_spin_bands")

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
            "ui": {"font_scale": args.scale},
        }
    )
    for theme_name in ("dark", "light"):
        theme = ThemeManager(theme_name, font_scale=config.ui.font_scale)
        theme.apply(app)
        settings = QSettings(str(tmp / f"{theme_name}.ini"), QSettings.Format.IniFormat)
        window = MainWindow(LoadedConfig(config, None), theme, settings)
        window.resize(1440, 900)
        window.show()
        for folder in sorted(p for p in project.iterdir() if p.is_dir()):
            window.service.detect_now(folder)
        window.explorer.select_path(project / "03_bands")
        window.open_file(project / "03_bands" / "bands.in")
        if args.plot or args.spin:
            from PyQt6.QtCore import QEventLoop, QTimer

            loop = QEventLoop()
            window.plot_ready.connect(loop.quit)
            window.plot_failed.connect(loop.quit)
            QTimer.singleShot(15000, loop.quit)
            target = "05_spin_bands" if args.spin else "03_bands"
            window.generate_plot_for(project / target, auto_export=False)
            loop.exec()
            if args.spin:
                window.params.set_param("spin_layout", "side")
                window.params.set_param("show_legend", True)
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
        if args.input or args.diff:
            scf, broken, changed = write_inputs(project)
            if args.input:
                window.open_file(broken)
                wait_for(window.workspace.current().loaded)
                window.workspace.current().editor.go_to_line(1)
            if args.diff:
                diff = window.workspace.open_diff(scf, changed)
                wait_for(diff.loaded)
                if args.diff == "text":
                    diff.show_text()
                window.set_panel_visible("workspace", True)
        if args.nav:
            show_navigation(window, project, app)
        if args.summary:
            summary = project / "01_relax" / "si.rel.out"
            window.open_summary(summary)
            view = window.workspace.widget_for(f"summary:{summary}")
            wait_for(view.loaded)
            view.sections[1].rows[-1].expand()  # the pseudopotentials of "Sistema"
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
