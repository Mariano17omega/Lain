"""Render the main window off-screen to PNG (both themes) for visual checks against the mockups.

    uv run python scripts/screenshot.py [--out DIR] [--plot] [--text] [--input] [--diff] [--summary] [--spin] [--nav] [--scale N] [--language en]

Builds a demo project from the test fixtures (01_relax, 02_scf, 03_bands, 04_pdos).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from qe_studio import i18n  # no texts: the language is installed before the modules that have them

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


# The cluster's queue the jobs indicator shows (spec 64): the screenshots never log in to a cluster.
DEMO_JOBS = """\
Running jobs:
 job-ID  # name                      owner      start time          running in
------------------------------------------------------------------------------
  23538 32 Nd2Fe14B-4f-129           usuario_a  10/15/2026 17:53:02 physica.q
  23601 32 MoS2-bands                usuario    10/23/2026 09:12:40 physica.q

Waiting jobs:
 job-ID  # name                      owner      submit time
-------------------------------------------------------------------
  23542 32 Sm3NbO8-HP-130            usuario_a  10/15/2026 18:05:21
  23644 32 MoS2-pdos                 usuario    10/22/2026 23:39:04
"""


def demo_jobs(_config, _password=None):
    """``fetch_jobs`` of the screenshots: ``DEMO_JOBS``, at once."""
    from qe_studio.core.cluster_jobs import parse_qstatus

    return parse_qstatus(DEMO_JOBS)


def open_window(project: Path, tmp: Path, theme_name: str, scale: float):
    """The main window on ``project`` as the screenshots show it: the theme applied, the folders
    detected, ``03_bands`` selected and its ``bands.in`` open. A ``QApplication`` must exist; the
    window's QSettings are an ini file in ``tmp``. No excepthook is installed: the caller chooses
    (``tests/i18n_probe.py`` uses this too)."""
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from qe_studio.core.config import LoadedConfig, parse_config
    from qe_studio.ui import jobs_controller
    from qe_studio.ui.main_window import MainWindow
    from qe_studio.ui.theme.manager import ThemeManager

    jobs_controller.fetch_jobs = demo_jobs  # no login to the example cluster
    config = parse_config(
        {
            "paths": {"local_root": str(project), "remote_root": "/scratch/usuario/MoS2"},
            "cluster": {"host": "cluster.example.org", "user": "usuario"},
            "ui": {"font_scale": scale},
        }
    )
    theme = ThemeManager(theme_name, font_scale=config.ui.font_scale)
    theme.apply(QApplication.instance())
    settings = QSettings(str(tmp / f"{theme_name}.ini"), QSettings.Format.IniFormat)
    window = MainWindow(LoadedConfig(config, None), theme, settings)
    window.resize(1440, 900)
    window.show()
    for folder in sorted(p for p in project.iterdir() if p.is_dir()):
        window.service.detect_now(folder)
    window.explorer.select_path(project / "03_bands")
    window.open_file(project / "03_bands" / "bands.in")
    return window


def generate_plot(window, folder: Path, timeout_ms: int = 15000) -> str | None:
    """Plot ``folder`` (nothing exported) and wait for it: None once the plot is shown, else why
    it is not."""
    from PyQt6.QtCore import QEventLoop, QTimer

    outcome: list[str | None] = []
    loop = QEventLoop()

    def ready(session: object) -> None:
        outcome.append(None)
        loop.quit()

    def failed(message: str) -> None:
        outcome.append(message or "the plot failed")
        loop.quit()

    window.plot_ready.connect(ready)
    window.plot_failed.connect(failed)
    QTimer.singleShot(timeout_ms, loop.quit)
    window.generate_plot_for(folder, auto_export=False)
    if not outcome:  # it may be done already
        loop.exec()
    window.plot_ready.disconnect(ready)
    window.plot_failed.disconnect(failed)
    return outcome[0] if outcome else f"no plot after {timeout_ms} ms"


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
    parser.add_argument(
        "--language", choices=i18n.LANGUAGES, default=i18n.SOURCE_LANGUAGE,
        help="the program's language; not pt_BR goes into the file names (main_dark_en.png)",
    )  # fmt: skip
    args = parser.parse_args()
    # Before the modules with texts are imported: they are translated while they load (spec end R1).
    i18n.install(args.language)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="qe-studio-shot-"))
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
    os.environ["XDG_DATA_HOME"] = str(tmp / "data")
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    project = build_project(tmp)
    if args.spin:
        shutil.copytree(FIXTURES / "qe731_ni_spin_bands", project / "05_spin_bands")

    from PyQt6.QtWidgets import QApplication

    from qe_studio.core.plotting.style import register_fonts
    from qe_studio.ui.app import install_excepthook

    app = QApplication(sys.argv[:1])
    install_excepthook()
    register_fonts()
    suffix = "" if args.language == i18n.SOURCE_LANGUAGE else f"_{args.language}"
    for theme_name in ("dark", "light"):
        window = open_window(project, tmp, theme_name, args.scale)
        if args.plot or args.spin:
            generate_plot(window, project / ("05_spin_bands" if args.spin else "03_bands"))
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
        path = out / f"main_{theme_name}{suffix}.png"
        window.grab().save(str(path))
        print(path)
        window.close()
        window.deleteLater()
        app.processEvents()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
