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
# Files with a limit of their own, below LIMIT, so the room made in them is not spent again by
# accident (spec 27-5 R4): the composition root.
PER_FILE_LIMIT: dict[str, int] = {"ui/main_window.py": 450}
# The only core modules with Qt: QProcess/signals of the sync (the rsync run both directions share,
# the pull's conflicts), the reachability monitor and the background-task helper.
QT_IN_CORE = {
    "core/sync/_process.py",
    "core/sync/controller.py",
    "core/sync/monitor.py",
    "core/tasks.py",
}
# ui modules that read files: the app's own resources (QSS, theme tokens, SVG icons).
UI_READERS = {"ui/theme/manager.py"}
READ_CALLS = {"read_text", "read_bytes", "loadtxt"}
# Calls that touch the disk (spec 27-8 R3.2): a ``Path`` that is slow (a network mount) blocks the GUI
# thread. ``ui/`` makes the calls below and no more: a new one belongs in ``core/`` or in a worker
# (``run_task``), not in this list. The counts only shrink; the test also fails when one is *lower*
# than listed, so the list is lowered with the code. The names are the AST's: ``proxy.is_dir(index)``
# of the file models counts too, though it asks a model, not the disk.
FS_CALLS = {
    "resolve",
    "exists",
    "is_dir",
    "is_file",
    "stat",
    "iterdir",
    "glob",
    "rglob",
    "samefile",
}
FS_ALLOWED: dict[str, int] = {
    "ui/app_identity.py": 1,
    "ui/calc_create_controller.py": 2,
    "ui/dialogs/calc_create/setup_page.py": 1,
    "ui/dialogs/mapping.py": 1,
    "ui/dialogs/rename.py": 1,
    "ui/first_run.py": 3,
    "ui/grids_controller.py": 1,
    "ui/help_controller.py": 1,
    "ui/main_window.py": 1,
    "ui/navigation_controller.py": 5,
    "ui/rename_controller.py": 2,
    "ui/sync_coordinator.py": 2,
    "ui/widgets/context_menu.py": 4,
    "ui/widgets/explorer.py": 5,
    "ui/widgets/file_card.py": 2,
    "ui/widgets/file_grid.py": 2,
    "ui/widgets/fs_model.py": 1,
}
# Moved out of ui/ by spec 15 R5: they must load without Qt (and be tested without it).
QT_FREE = [
    "qe_studio.core.text_preview",
    "qe_studio.core.file_kinds",
    "qe_studio.core.plotting.session",
    "qe_studio.core.plotting.gap_label",
    "qe_studio.core.sync.request",
    "qe_studio.core.sync.preview",
    "qe_studio.core.sync.report",
    "qe_studio.core.sync.push_plan",
    "qe_studio.core.paths",
    "qe_studio.core.navigation",
    "qe_studio.core.filtering",
    "qe_studio.core.nav_store",
    "qe_studio.core.fuzzy",
    "qe_studio.core.folder_index",
    "qe_studio.core.config_template",
    "qe_studio.core.about",
    "qe_studio.core.colors",
    "qe_studio.core.fontscale",
    "qe_studio.core.compounds",
    "qe_studio.core.qe.structure",
    "qe_studio.core.plotting.grid",
    "qe_studio.core.plotting.cell_layout",
    "qe_studio.core.plotting.grid_session",
    "qe_studio.core.plotting.offscreen",
    "qe_studio.core.grid_store",
    "qe_studio.core.calculations.grid",
    "qe_studio.core.qe.input_edit",
    "qe_studio.core.qe.final_structure",
    "qe_studio.core.qe.scf_from_relax",
    "qe_studio.core.unique_names",
    "qe_studio.core.qe.lattice",
    "qe_studio.core.calc_create",
    "qe_studio.core.calc_create.render",
    "qe_studio.core.calc_create.kpath",
    "qe_studio.core.calc_create.scf_info",
    "qe_studio.core.calc_create.edits",
    "qe_studio.core.calc_create.unit",
    "qe_studio.core.calc_create.writer",
    "qe_studio.core.calc_create.preview",
    "qe_studio.core.calc_create.types",
    "qe_studio.core.calc_create.types.base",
    "qe_studio.core.calc_create.types.script",
    "qe_studio.core.calc_create.types.fields",
    "qe_studio.core.calc_create.types.files",
    "qe_studio.core.calc_create.types.scf",
    "qe_studio.core.calc_create.types.relax",
    "qe_studio.core.calc_create.types.vc_relax",
    "qe_studio.core.calc_create.types.bandas",
    "qe_studio.core.calc_create.types.pdos",
    "qe_studio.core.calc_create.types.charge",
    "qe_studio.core.calc_create.types.charge_diff",
    "qe_studio.core.calc_create.fragments",
    "qe_studio.core.calc_create.species_keys",
    "qe_studio.core.cancel",
    "qe_studio.core.sizing",
    "qe_studio.core.calculations.load_cache",
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
        if (lines := len(path.read_text(encoding="utf-8").splitlines()))
        > PER_FILE_LIMIT.get(name_of(path), LIMIT)
        and name_of(path) not in SIZE_EXCEPTIONS
    }
    assert not long, f"split these by responsibility (> {LIMIT} lines, or their own limit): {long}"


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


def fs_calls(source: str) -> int:
    """How many calls of ``FS_CALLS`` (``x.exists()``, ``x.resolve()``…) ``source`` makes."""
    return sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FS_CALLS
        for node in ast.walk(ast.parse(source))
    )


def fs_problems(counts: dict[str, int], allowed: dict[str, int] = FS_ALLOWED) -> list[str]:
    """What is wrong between the calls found per file and the ones ``allowed``."""
    problems = []
    for name in sorted(counts.keys() | allowed.keys()):
        found, listed = counts.get(name, 0), allowed.get(name, 0)
        if found > listed:
            problems.append(
                f"{name}: {found} filesystem calls, {listed} allowed: "
                "do it in core/ or a worker, do not raise FS_ALLOWED"
            )
        elif found < listed:
            problems.append(
                f"{name}: {found} filesystem calls, FS_ALLOWED lists {listed}: lower it"
            )
    return problems


def ui_fs_counts() -> dict[str, int]:
    counts = {
        name_of(path): fs_calls(path.read_text(encoding="utf-8"))
        for path in sources("ui")
        if name_of(path) not in UI_READERS
    }
    return {name: found for name, found in counts.items() if found}


def test_the_ui_makes_no_new_filesystem_calls():
    assert fs_problems(ui_fs_counts()) == []


def test_the_filesystem_check_flags_a_new_call_and_a_stale_list():
    assert fs_calls("def f(p):\n    return p.exists() and p.parent.resolve()\n") == 2
    assert fs_calls("def f(p):\n    return open(p), exists(p), p.name\n") == 0
    now = ui_fs_counts()
    assert fs_problems(now) == []
    assert "ui/new_widget.py: 1" in fs_problems({**now, "ui/new_widget.py": 1})[0]
    more = {**now, "ui/main_window.py": FS_ALLOWED["ui/main_window.py"] + 1}
    assert "do not raise FS_ALLOWED" in fs_problems(more)[0]
    fewer = {name: found for name, found in now.items() if name != "ui/first_run.py"}
    assert "lower it" in fs_problems(fewer)[0]


def test_pymatgen_is_not_mentioned():
    """Spec 27-2: the band path is typed, not suggested; no source, template or dependency names
    pymatgen."""
    text_files = [
        path
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix in {".py", ".j2", ".yaml", ".qss", ".md"}
    ]
    text_files.append(PACKAGE.parents[1] / "pyproject.toml")
    named = [str(path) for path in text_files if "pymatgen" in path.read_text("utf-8").lower()]
    assert named == []


def test_the_import_checker_resolves_relative_imports():
    tasks = imported_modules(PACKAGE / "core" / "sync" / "_process.py")
    assert {"qe_studio.core.config", "qe_studio.core.tasks", "PyQt6.QtCore"} <= tasks
    window = imported_modules(PACKAGE / "ui" / "main_window.py")
    assert "qe_studio.core.folder_memory" in window and "qe_studio.ui.plot_workflow" in window


@pytest.mark.parametrize("module", QT_FREE)
def test_the_modules_moved_to_core_load_without_qt(module):
    code = f"import sys, {module}; sys.exit('PyQt6' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], timeout=60).returncode == 0
