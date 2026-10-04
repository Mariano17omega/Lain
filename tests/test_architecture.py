"""Architecture rules of CLAUDE.md, checked (spec 15 R6): file size, layers, Qt in ``core`` and file
reading in ``ui``. The checks read the source (AST), so they catch the common case, not every one."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import qe_studio

PACKAGE = Path(qe_studio.__file__).parent
LIMIT = 500
# Files allowed past LIMIT, each with its reason. Starts (and should stay) empty.
SIZE_EXCEPTIONS: dict[str, str] = {}
# The only core modules with Qt: QProcess/signals of the sync, and the background-task helper.
QT_IN_CORE = {"core/sync/controller.py", "core/sync/monitor.py", "core/tasks.py"}
# ui modules that read files: the app's own resources (QSS, theme tokens, SVG icons).
UI_READERS = {"ui/theme/manager.py"}
READ_CALLS = {"read_text", "read_bytes", "loadtxt"}
# Moved out of ui/ by spec 15 R5: they must load without Qt (and be tested without it).
QT_FREE = [
    "qe_studio.core.text_preview",
    "qe_studio.core.file_kinds",
    "qe_studio.core.plotting.session",
    "qe_studio.core.sync.request",
    "qe_studio.core.paths",
    "qe_studio.core.navigation",
    "qe_studio.core.filtering",
    "qe_studio.core.nav_store",
    "qe_studio.core.fuzzy",
    "qe_studio.core.folder_index",
    "qe_studio.core.config_template",
    "qe_studio.core.about",
]


def sources(layer: str = "") -> list[Path]:
    return sorted((PACKAGE / layer).rglob("*.py"))


def name_of(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


def imported_modules(path: Path) -> set[str]:
    """Absolute names of the modules ``path`` imports (relative imports resolved)."""
    module = "qe_studio." + name_of(path).removesuffix(".py").replace("/", ".")
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                names.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                names.add(node.module)
    return names


def test_no_file_is_over_the_size_limit():
    long = {
        name_of(path): lines
        for path in sources()
        if (lines := len(path.read_text(encoding="utf-8").splitlines())) > LIMIT
        and name_of(path) not in SIZE_EXCEPTIONS
    }
    assert not long, f"split these by responsibility (> {LIMIT} lines): {long}"


def test_core_never_imports_the_ui():
    offenders = {
        name_of(path): sorted(m for m in imported_modules(path) if m.startswith("qe_studio.ui"))
        for path in sources("core")
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_qt_in_core_only_where_allowed():
    with_qt = {
        name_of(path)
        for path in sources("core")
        if any(m.split(".")[0] == "PyQt6" for m in imported_modules(path))
    }
    assert with_qt == QT_IN_CORE


def test_the_ui_does_not_read_files():
    offenders = {}
    for path in sources("ui"):
        if name_of(path) in UI_READERS:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                offenders.setdefault(name_of(path), []).append(f"open() line {node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr in READ_CALLS:
                offenders.setdefault(name_of(path), []).append(f"{func.attr} line {node.lineno}")
    assert offenders == {}, "reading files is core's job (CLAUDE.md, ui/ holds interface logic)"


def test_the_import_checker_resolves_relative_imports():
    tasks = imported_modules(PACKAGE / "core" / "sync" / "controller.py")
    assert {"qe_studio.core.config", "qe_studio.core.tasks", "PyQt6.QtCore"} <= tasks
    window = imported_modules(PACKAGE / "ui" / "main_window.py")
    assert "qe_studio.core.file_ops" in window and "qe_studio.ui.plot_workflow" in window


@pytest.mark.parametrize("module", QT_FREE)
def test_the_modules_moved_to_core_load_without_qt(module):
    code = f"import sys, {module}; sys.exit('PyQt6' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], timeout=60).returncode == 0
