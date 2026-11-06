"""Every path and module name the code, the tests and the docs cite exists (spec 78.5 R1): a module
moved to another folder leaves no stale citation behind, in a comment, a string or a list of a test.

A path (``core/…``, ``ui/…``, also after ``src/qe_studio/``) is relative to ``src/qe_studio``: a
file or a folder, ``<module>.<attribute>`` of a module that exists, or, with no ``.py`` and no ``/``
at the end, the start of a file's path (the prefix lists of ``test_i18n.py``). A dotted name
(``qe_studio.core.…``, or ``core.…`` as the docstrings write it) goes down packages and modules:
past a module the rest are its attributes, and a package's attribute must be defined at the top of
its ``__init__.py``. A short ``ui.…`` is not checked: ``ui.language``, ``ui.font_scale``… are keys
of ``config.yaml``, not modules."""

import ast
import functools
import re
from pathlib import Path

import qe_studio

PACKAGE = Path(qe_studio.__file__).parent
ROOT = PACKAGE.parents[1]
CITED_PATH = re.compile(r"(?:(?<![\w/.-])|(?<=src/qe_studio/))((?:core|ui)/[A-Za-z0-9_./-]*)")
DOTTED_NAME = re.compile(r"(?<![\w.])(qe_studio\.(?:core|ui)|core)((?:\.[A-Za-z_]\w*)+)")
# Paths that do not exist on purpose: the input of a check, never a file of the package.
FAKE_PATHS = {
    "core/sample.py",  # tests/test_decimal_point.py: the comma finder on a made-up source
    "core/x.py",  # tests/test_i18n.py: the static checks on a made-up source
    "ui/x.py",  # tests/test_i18n.py: the same
    "ui/new_widget.py",  # tests/test_architecture.py: a filesystem call FS_ALLOWED does not list
}


def existing(paths: list[Path]) -> list[Path]:
    """The files of ``paths`` that exist, this one left out: its examples are made up."""
    return [path for path in paths if path.is_file() and path != Path(__file__)]


def path_sources() -> list[Path]:
    """The files whose ``core/…`` and ``ui/…`` citations are checked."""
    return existing(
        [
            *sorted(PACKAGE.rglob("*.py")),
            *sorted((ROOT / "tests").glob("*.py")),
            *sorted((ROOT / "scripts").glob("*.py")),
            ROOT / "CLAUDE.md",
            ROOT / "README.md",
            PACKAGE / "locale" / "README.md",
            *sorted((ROOT / ".claude" / "skills" / "spec-sdd").rglob("*.md")),
        ]
    )


def name_sources() -> list[Path]:
    """The files whose ``qe_studio.core…`` and ``qe_studio.ui…`` names are checked."""
    return existing(
        [
            *sorted(PACKAGE.rglob("*.py")),
            *sorted((ROOT / "tests").glob("*.py")),
            *sorted((ROOT / "scripts").glob("*.py")),
            ROOT / "CLAUDE.md",
            ROOT / "README.md",
        ]
    )


def where(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def cited_paths(text: str) -> list[tuple[int, str]]:
    """The ``core/…`` and ``ui/…`` paths ``text`` cites, with their line, a final period left
    out."""
    return [
        (number, match.group(1).rstrip("."))
        for number, line in enumerate(text.splitlines(), 1)
        for match in CITED_PATH.finditer(line)
    ]


def dotted_names(text: str) -> list[tuple[int, str]]:
    """The ``qe_studio.core.…`` and ``qe_studio.ui.…`` names ``text`` cites, with their line; a
    short ``core.…`` is read as ``qe_studio.core.…``."""
    return [
        (number, "qe_studio." + match.group(1).removeprefix("qe_studio.") + match.group(2))
        for number, line in enumerate(text.splitlines(), 1)
        for match in DOTTED_NAME.finditer(line)
    ]


def files_under(package: Path) -> list[str]:
    return sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def path_exists(package: Path, files: list[str], cited: str) -> bool:
    """Whether ``cited`` names a file or a folder of ``package``, ``<module>.<attribute>``, or (no
    ``.py`` and no ``/`` at the end) the start of a file's path."""
    if (package / cited).exists():
        return True
    if cited.endswith((".py", "/")):
        return False
    module, _, attribute = cited.rpartition(".")
    if module and attribute and (package / f"{module}.py").is_file():
        return True
    return any(name.startswith(cited) for name in files)


@functools.cache
def defined_at_top(init: Path) -> frozenset[str]:
    """The names the top of ``init`` binds: functions, classes, assignments and imports."""
    if not init.is_file():
        return frozenset()
    names = set()
    for node in ast.parse(init.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
    return frozenset(names)


def resolves(package: Path, name: str) -> bool:
    """Whether the dotted ``name`` (``qe_studio.…``) is a package, a module or an attribute of one
    under ``package``: past a module anything goes; a package's attribute is defined at its top."""
    here = package
    for part in name.split(".")[1:]:
        if (here / part).is_dir():
            here = here / part
        elif (here / f"{part}.py").is_file():
            return True
        else:
            return part in defined_at_top(here / "__init__.py")
    return True


def test_every_cited_path_exists():
    files = files_under(PACKAGE)
    stale = [
        f"{where(path)}:{line}: {cited}"
        for path in path_sources()
        for line, cited in cited_paths(path.read_text(encoding="utf-8"))
        if cited not in FAKE_PATHS and not path_exists(PACKAGE, files, cited)
    ]
    assert stale == [], "paths that do not exist (spec 78.5 maps the old folders):\n" + "\n".join(
        stale
    )


def test_every_dotted_module_name_resolves():
    stale = [
        f"{where(path)}:{line}: {name}"
        for path in name_sources()
        for line, name in dotted_names(path.read_text(encoding="utf-8"))
        if not resolves(PACKAGE, name)
    ]
    assert stale == [], "module names that do not resolve:\n" + "\n".join(stale)


def test_the_citations_are_found_in_text():
    text = "See `core/qe/scf.py`. Not tests/core/x.py,\nnor xui/y.py, but src/qe_studio/ui/app.py."
    assert cited_paths(text) == [(1, "core/qe/scf.py"), (2, "ui/app.py")]
    code = 'patch("qe_studio.ui.app.main")\nimport qe_studio.core.config  # qe_studio.i18n\n'
    assert dotted_names(code) == [(1, "qe_studio.ui.app.main"), (2, "qe_studio.core.config")]
    doc = "With ``core.files.paths.is_hidden``; not ``ui.language``, nor self.core.x, nor score.y."
    assert dotted_names(doc) == [(1, "qe_studio.core.files.paths.is_hidden")]


def test_the_checker_flags_a_stale_prefix_and_a_stale_module(tmp_path):
    (tmp_path / "core" / "qe").mkdir(parents=True)
    (tmp_path / "core" / "qe" / "scf.py").write_text("def read_scf():\n    pass\n")
    (tmp_path / "core" / "__init__.py").write_text("from .qe import scf as scf_module\nLIMIT = 1\n")
    (tmp_path / "ui" / "plot").mkdir(parents=True)
    (tmp_path / "ui" / "plot" / "plot_workflow.py").write_text("")
    files = files_under(tmp_path)
    assert not path_exists(tmp_path, files, "ui/plot_")  # the prefix of a file that moved
    assert path_exists(tmp_path, files, "ui/plot/plot_")
    assert path_exists(tmp_path, files, "core/qe/scf.read_scf")
    assert path_exists(tmp_path, files, "core/qe/")
    assert not path_exists(tmp_path, files, "core/scf.py")
    assert resolves(tmp_path, "qe_studio.core.qe.scf.read_scf")
    assert resolves(tmp_path, "qe_studio.core.LIMIT")
    assert resolves(tmp_path, "qe_studio.core.scf_module")
    assert not resolves(tmp_path, "qe_studio.core.velho")
    assert not resolves(tmp_path, "qe_studio.core.qe.velho")
    (short,) = dotted_names("``core.velho.attr``")  # a docstring's short form, moved away
    assert not resolves(tmp_path, short[1])
