"""Leak probe (spec 52 R5): every text the window shows in a language, as JSON, from a new process.

    python tests/i18n_probe.py --language en [--project DIR] --scenario main --scenario plot

The language is chosen once, before the modules with texts are imported (spec end R1), so each
language needs a process of its own: the tests run this script (``i18n_helpers.probe_texts``) and
compare its texts with the catalog. The window is the one of ``scripts/screenshot.py``
(``open_window``) on ``DIR``, or on the screenshots' demo project. The scenarios run in the order
given, on the same window, and the texts are read after each: those of every widget alive (hidden
pages and every menu included), as in ``widget_texts``. Painted text (the badges of the tree and the
grid, figures, the 3D view) belongs to no widget: the spec of each area tests it through its model.

A spec of the series adds its scenarios to ``SCENARIOS``: a function ``(window, project)`` that
brings the window to what is checked, opening dialogs without ``exec()`` (a modal loop would wait
forever). An unexpected exception ends the process with code 1 and the traceback on stderr: the
app's excepthook would open a modal box instead. The last line of stdout is ``{scenario: [texts]}``.
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


SCENARIOS: dict[str, Callable[..., None]] = {"main": main_scenario, "plot": plot_scenario}


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
    parser.add_argument("--scenario", action="append", required=True, choices=list(SCENARIOS))
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="lain-i18n-probe-"))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[name] = str(tmp / name.lower())
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
        SCENARIOS[name](window, project)
        settle(window, app)
        texts[name] = visible_texts()
    print(json.dumps(texts, ensure_ascii=False), flush=True)
    window.close()
    QThreadPool.globalInstance().waitForDone(2000)
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stderr.flush()
    os._exit(0)  # no interpreter teardown with Qt threads alive (as ui/app.py:finish)


if __name__ == "__main__":
    sys.exit(main())
