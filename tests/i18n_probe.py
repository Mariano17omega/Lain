"""Leak probe (spec 52 R5): every text the window shows in a language, as JSON, from a new process.

    python tests/i18n_probe.py --language en [--project DIR] --scenario main --scenario plot

The language is chosen once, before the modules with texts are imported (spec end R1), so each
language needs a process of its own: the tests run this script (``i18n_helpers.probe_texts``) and
compare its texts with the catalog. The window is the one of ``scripts/screenshot.py``
(``open_window``) on ``DIR``, or on the screenshots' demo project. The scenarios run in the order
given, on the same window, and the texts are read after each: those of every widget alive (hidden
pages and every menu included), as in ``widget_texts``. Painted text (the badges of the tree and the
grid, figures, the 3D view) belongs to no widget: the spec of each area tests it through its model.

A spec of the series adds its scenarios to ``SCENARIOS`` (spec 54's are in
``tests/i18n_scenarios_54.py``, 55's to 57's in ``…_55.py`` to ``…_57.py``, merged below): a function
``(window, project)`` that brings the window to what is checked, opening dialogs without ``exec()``
(a modal loop would wait forever). An unexpected exception ends the process with code 1 and the
traceback on stderr: the app's excepthook would open a modal box instead. The last line of stdout
is ``{scenario: [texts]}``.

A scenario may also return a list of *facts*, what no widget shows: the order of the menus, the
output of ``--help``, the text of an error, what the grid lists. They come in the same JSON as
``{"<scenario>#facts": [...]}``, for the test to compare between languages. After each scenario the
dialogs it opened are closed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import i18n_scenarios_55
from i18n_scenarios_54 import SCENARIOS as SCENARIOS_54
from i18n_scenarios_55 import SCENARIOS as SCENARIOS_55
from i18n_scenarios_56 import SCENARIOS as SCENARIOS_56
from i18n_scenarios_57 import SCENARIOS as SCENARIOS_57
from qe_studio import i18n  # no texts: the language is installed before the modules that have them

ROOT = Path(__file__).resolve().parents[1]
TEXT_GETTERS = ("text", "toolTip", "windowTitle", "placeholderText", "title", "accessibleName")


def _load_screenshot():
    spec = importlib.util.spec_from_file_location("screenshot", ROOT / "scripts" / "screenshot.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/screenshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screenshot = _load_screenshot()


def main_scenario(window, project: Path) -> None:
    """The window as ``open_window`` leaves it: ``03_bands`` selected, its ``bands.in`` open."""


def plot_scenario(window, project: Path) -> None:
    """The band plot of ``03_bands`` and its adjustments panel."""
    error = screenshot.generate_plot(window, project / "03_bands")
    if error is not None:
        raise RuntimeError(f"the band plot of 03_bands failed: {error}")


# -- spec 53: the window, its menus and the general dialogs ---------------------------------------
def shortcuts_scenario(window, project: Path) -> list[str]:
    """The dialog of "Ajuda ▸ Atalhos de teclado"; its rows (table cells: item data, no widget text)
    come back as facts."""
    window.help.show_shortcuts()
    return [" | ".join(row) for row in window.help.dialog.visible_rows()]


def about_scenario(window, project: Path) -> None:
    from qe_studio import APP_NAME, __version__
    from qe_studio.ui.dialogs.about import AboutDialog

    # ``help.show_about`` runs the dialog and schedules its deletion: build the same one.
    AboutDialog(f"{APP_NAME} {__version__}", window.help.about_rows(), window).show()


def palette_scenario(window, project: Path) -> None:
    window.command_palette.open()


def context_menu_scenario(window, project: Path) -> None:
    """The menus of an input, an output and a folder, and of a selection: built, never run."""
    items = window.item_actions
    bands = project / "03_bands"
    items.menu(bands / "bands.in", plot_kind="bands", structure=True, xcrysden="--pwi", push="")
    items.menu(
        bands / "bands.out", plot_kind="bands", summary=True, xcrysden="--pwo", scf="", push=""
    )
    items.menu(bands, favorite=False, push="")
    items.menu(bands, favorite=True, push="")
    items.multi_menu([bands / "bands.in", bands / "bands.out"])


def open_with_scenario(window, project: Path) -> None:
    from qe_studio.ui.dialogs.open_with import OpenWithDialog

    OpenWithDialog("scf.in", window).show()


def rename_scenario(window, project: Path) -> None:
    from qe_studio.ui.dialogs.rename import RenameDialog

    dialog = RenameDialog(project / "02_scf" / "scf.in", window)
    dialog.show()
    dialog.edit.setText("a/b")
    dialog.accept()  # refused: the error line shows


def new_project_scenario(window, project: Path) -> None:
    from qe_studio.ui.dialogs.new_project import NewProjectDialog

    dialog = NewProjectDialog(["01_relax"], ("tmp",), window)
    dialog.show()
    dialog.edit.setText("01_relax")  # an existing name: the error line shows


def overwrite_scenario(window, project: Path) -> None:
    from qe_studio.ui.dialogs.overwrite import OverwriteDialog

    OverwriteDialog([project / "plots" / "bands.png"], "bands", window).show()


def first_run_scenario(window, project: Path) -> None:
    """The welcome state of a missing ``config.yaml`` and the two questions that follow it. The
    overlay stays on: this scenario goes last."""
    from PyQt6.QtWidgets import QMessageBox

    from qe_studio.core.config import LoadedConfig
    from qe_studio.ui.dialogs import first_run as questions

    window.loaded = LoadedConfig(window.config, None, first_run=True)
    window.first_run.refresh()

    def question(parent, title, text, buttons, default):  # QMessageBox.question without its loop
        QMessageBox(QMessageBox.Icon.Question, title, text, buttons, parent).show()
        return QMessageBox.StandardButton.No

    QMessageBox.question = staticmethod(question)  # type: ignore[assignment]
    questions.ask_create_config(window, project / "config.yaml")
    questions.ask_create_with_folder(window, project)


def toast_scenario(window, project: Path) -> None:
    window.toast.show_message("falha ao gravar", "error", details="OSError")
    window.toast.show_message("aviso", "warning")


def tree_scenario(window, project: Path) -> list[str]:
    """The tree with its files shown, and the text painted on a folder with a ``CRASH`` file: the
    badges are drawn, not widgets, so ``paint_badge`` is asked what it was given (no pixel read)."""
    from qe_studio.ui.widgets import explorer

    folder = project / "02_scf"
    (folder / "CRASH").write_text("")
    window.explorer.set_files_shown(True)
    window.service.detect_now(folder)
    painted: list[str] = []
    real = explorer.paint_badge

    def recording(painter, right, center, text, *rest):
        painted.append(text)
        return real(painter, right, center, text, *rest)

    explorer.paint_badge = recording
    try:
        window.explorer.tree.viewport().grab()
    finally:
        explorer.paint_badge = real
    return painted


# -- facts: what no widget shows (the order of the menus, the command line, an error message…) ------
def menus_scenario(window, project: Path) -> list[str]:
    return [action.text() for action in window.menuBar().actions()]


def cli_scenario(window, project: Path) -> list[str]:
    """``lain --help``: argparse prints it and exits."""
    import contextlib
    import io

    from qe_studio.ui.app import parse_args

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        parse_args(["--help"])
    return out.getvalue().splitlines()


def config_scenario(window, project: Path) -> list[str]:
    """What ``load_config`` says of a ``config.yaml`` with an unknown key and an empty energy window."""
    from qe_studio.core.config import ConfigError, load_config

    with tempfile.TemporaryDirectory(prefix="lain-i18n-config-") as folder:
        path = Path(folder) / "config.yaml"
        path.write_text(
            "ui:\n  bogus: 1\nplot:\n  energy_min: 5\n  energy_max: 1\n", encoding="utf-8"
        )
        try:
            load_config(path)
        except ConfigError as exc:
            return str(exc).splitlines()
    raise RuntimeError("the invalid config.yaml was accepted")


def restart_scenario(window, project: Path) -> list[str]:
    """The notice of a reload whose ``ui.language`` is not the running language."""
    from qe_studio.core.language import ENV_LANGUAGE, ENV_LANGUAGE_ALIAS
    from qe_studio.ui.language import restart_notice

    for name in (ENV_LANGUAGE, ENV_LANGUAGE_ALIAS):  # a pinned language ignores the config
        os.environ.pop(name, None)
    return [restart_notice("pt_BR" if i18n.current_language() == "en" else "en")]


def type_filter_scenario(window, project: Path) -> list[str]:
    """What the grid of ``03_bands`` lists with the visual type "saídas" ticked (the stored value,
    whatever its label says)."""
    bar = window.files.filter_bar
    bar.open()
    bar._actions[("visuals", "saídas")].setChecked(True)
    bar.flush()
    proxy, root = window.files.proxy, window.files.view.rootIndex()
    listed = [proxy.index(row, 0, root) for row in range(proxy.rowCount(root))]
    names = [proxy.path(index).name for index in listed if not proxy.is_up(index)]
    bar.dismiss()
    return names


# A scenario brings the window to what is checked; one that returns a list gives facts to compare
# (they go in the JSON as ``<scenario>#facts``). They run in the order given on the command line,
# on the same window: ``first_run`` leaves its overlay on, so it goes last.
SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "main": main_scenario,
    "plot": plot_scenario,
    "shortcuts": shortcuts_scenario,
    "about": about_scenario,
    "palette": palette_scenario,
    "context_menu": context_menu_scenario,
    "open_with": open_with_scenario,
    "rename": rename_scenario,
    "new_project": new_project_scenario,
    "overwrite": overwrite_scenario,
    "first_run": first_run_scenario,
    "toast": toast_scenario,
    "tree": tree_scenario,
    "menus": menus_scenario,
    "cli": cli_scenario,
    "config": config_scenario,
    "restart": restart_scenario,
    "type_filter": type_filter_scenario,
    **SCENARIOS_54,  # spec 54: the viewers and the Resumo (tests/i18n_scenarios_54.py)
    **SCENARIOS_55,  # spec 55: the plots, the atoms, the Grids and the export (…_55.py)
    **SCENARIOS_56,  # spec 56: the Criar cálculo window, the k-path editor, derive (…_56.py)
    **SCENARIOS_57,  # spec 57: the fields and checks of each type, the files of a Slab (…_57.py)
}


def header_texts(model) -> Iterator[object]:
    from PyQt6.QtCore import Qt

    try:
        columns = model.columnCount()
    except TypeError:  # a list model: its columnCount needs the parent
        columns = 1
    for column in range(columns):
        yield model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)


def widget_texts(widget) -> Iterator[object]:
    """Text, tooltip, title, placeholder and accessible name of ``widget``, and of its actions, tabs,
    combo items and model header."""
    from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QTabBar

    for name in TEXT_GETTERS:
        getter = getattr(widget, name, None)
        if callable(getter):
            try:
                yield getter()
            except TypeError:  # one that needs an argument (QTabBar.tabText…)
                continue
    for action in widget.actions():
        yield action.text()
        yield action.toolTip()
    if isinstance(widget, QTabBar):
        for index in range(widget.count()):
            yield widget.tabText(index)
            yield widget.tabToolTip(index)
    if isinstance(widget, QComboBox):
        yield from (widget.itemText(index) for index in range(widget.count()))
    if isinstance(widget, QAbstractItemView) and widget.model() is not None:
        yield from header_texts(widget.model())


def visible_texts() -> list[str]:
    from PyQt6.QtWidgets import QApplication

    found = {text for widget in QApplication.allWidgets() for text in widget_texts(widget)}
    return sorted(text for text in found if isinstance(text, str) and text)


def settle(window, app) -> None:
    for _round in range(30):
        app.processEvents()
    window.service.wait(3000)
    app.processEvents()


def close_dialogs(window) -> None:
    """Close what a scenario opened (a dialog, a window of its own); the main window stays."""
    from PyQt6.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        if widget is not window and widget.isVisible():
            widget.close()


def crash(kind, value, traceback) -> None:
    """An unexpected error ends the probe: the app's own hook would open a modal box."""
    sys.__excepthook__(kind, value, traceback)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)  # sys.exit would not end the process from a hook PyQt calls in a slot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--language", required=True, choices=i18n.LANGUAGES)
    parser.add_argument("--project", type=Path, help="default: the screenshots' demo project")
    parser.add_argument(
        "--plot-dir",
        type=Path,
        help="where the plot_files scenario keeps its .plot files: the first language writes them",
    )
    parser.add_argument("--scenario", action="append", required=True, choices=list(SCENARIOS))
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="lain-i18n-probe-"))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[name] = str(tmp / name.lower())
    i18n_scenarios_55.PLOT_DIR = args.plot_dir
    i18n.install(args.language)  # before the modules with texts are imported
    sys.excepthook = crash

    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtWidgets import QApplication

    from qe_studio.core.plotting.style import register_fonts

    app = QApplication(sys.argv[:1])
    register_fonts()
    project = args.project or screenshot.build_project(tmp)
    window = screenshot.open_window(project, tmp, "dark", 1.0)
    texts = {}
    for name in args.scenario:
        facts = SCENARIOS[name](window, project)
        settle(window, app)
        texts[name] = visible_texts()
        if facts is not None:
            texts[f"{name}#facts"] = facts
        close_dialogs(window)
    print(json.dumps(texts, ensure_ascii=False), flush=True)
    window.close()
    QThreadPool.globalInstance().waitForDone(2000)
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stderr.flush()
    os._exit(0)  # no interpreter teardown with Qt threads alive (as ui/app.py:finish)


if __name__ == "__main__":
    sys.exit(main())
