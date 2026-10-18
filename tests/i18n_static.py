"""Static check of spec end R4.1: no visible text outside ``_()`` / ``N_()`` / ``ngettext()``.

An AST walk over ``src/qe_studio`` reports two kinds of literal that are not marked:

- any string with a Portuguese accented letter (outside docstrings, logs and the explicit list of
  exceptions below);
- a string passed straight to a call that shows text (``setText``, ``QLabel``, ``QMessageBox.*``,
  ``ParamField``, ``LoadError``…).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

SOURCE = Path(__file__).resolve().parents[1] / "src" / "qe_studio"
ACCENTED = re.compile(r"[áâãàéêíóôõúçÁÂÃÀÉÊÍÓÔÕÚÇ]")
# What reads as a sentence or a label (not an identifier such as ``"error"`` or ``"bool"``).
SENTENCE = re.compile(r"\s|^[A-ZÀ-Ý]|[…:.]$")
LETTERS = re.compile(r"[A-Za-zÀ-ÿ]{2,}")

FIELD_CLASSES = {"ParamField", "FormField"}
FIELD_TEXTS = {"label", "tooltip", "suffix", "hint"}  # the keywords of those the user reads
MARKERS = {"_", "N_", "ngettext", "pgettext"}
# Calls whose string arguments the user reads.
SINKS = {
    "setText",
    "setToolTip",
    "setWindowTitle",
    "setPlaceholderText",
    "setStatusTip",
    "setAccessibleName",
    "setTitle",
    "setPrefix",
    "setSuffix",
    "setHeaderLabels",
    "setHorizontalHeaderLabels",
    "showMessage",
    "addAction",
    "addMenu",
    "addTab",
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "QGroupBox",
    "QAction",
    "QRadioButton",
    "information",
    "warning",
    "critical",
    "question",
    "LoadError",
    "set_message",
    "show_message",
    "add_row",
}
LOG_OBJECTS = {"log", "logger", "logging"}


class Finding(NamedTuple):
    path: str
    line: int
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.text!r}"


# Literals that are Portuguese on purpose and are not shown as written: the data values the
# catalog translates where they are shown (``N_`` would be noise on every use), the tokens the
# files keep. (file relative to ``src/qe_studio``, literal) pairs.
EXCEPTIONS: set[tuple[str, str]] = {
    ("core/sync/push_plan.py", "já existe"),  # PushAction value: the preview shows PUSH_TITLES
    ("ui/dialogs/about.py", '<a href="'),  # markup
    ("ui/file_types.py", "saídas"),  # a filter token: core/filtering.py shows VISUALS through _()
    ("ui/shutdown.py", "exportações"),  # shutdown step names: log only
    ("ui/shutdown.py", "detecção"),
    ("ui/shutdown.py", "árvore"),
    ("ui/widgets/structure3d/panel.py", " px"),  # a unit
    ("core/calc_create/types/pdos.py", "&PROJWFC "),  # namelist names of the tooltips
    ("core/calc_create/types/relax.py", "&IONS ion_dynamics"),
    ("core/calc_create/types/vc_relax.py", "&CELL cell_dynamics"),
    ("core/calc_create/types/script.py", "Pools (nk)"),  # QE's own term
}
# Whole files whose accented literals are data (none yet).
SKIPPED_FILES: set[str] = set()


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    name = owner.id if isinstance(owner, ast.Name) else None
    return name in LOG_OBJECTS or (isinstance(owner, ast.Call) and _call_name(owner) == "getLogger")


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def _skipped_nodes(tree: ast.AST) -> set[int]:
    """Nodes inside a marker call, a log call or a ``raise`` of an internal error."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (_call_name(node) in MARKERS or _is_log_call(node)):
            skipped.update(id(child) for child in ast.walk(node))
    return skipped


def _strings(node: ast.AST) -> Iterator[ast.Constant]:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child


def check_file(path: Path) -> list[Finding]:
    relative = path.relative_to(SOURCE).as_posix()
    if relative in SKIPPED_FILES:
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs, skipped = _docstrings(tree), _skipped_nodes(tree)
    found: dict[int, Finding] = {}

    def add(constant: ast.Constant) -> None:
        if (relative, constant.value) not in EXCEPTIONS:
            found[id(constant)] = Finding(relative, constant.lineno, constant.value)

    for constant in _strings(tree):
        if id(constant) in docs or id(constant) in skipped:
            continue
        if ACCENTED.search(constant.value):
            add(constant)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in skipped:
            continue
        name = _call_name(node)
        if name in FIELD_CLASSES:  # (name, label, …): the label and the texts of the keywords
            shown = [*node.args[1:2], *(k.value for k in node.keywords if k.arg in FIELD_TEXTS)]
        elif name in SINKS:
            shown = [*node.args, *(k.value for k in node.keywords)]
        else:
            continue
        for argument in shown:
            for constant in _strings(argument):
                if id(constant) in skipped or id(constant) in docs:
                    continue
                if LETTERS.search(constant.value) and SENTENCE.search(constant.value):
                    add(constant)
    return sorted(found.values(), key=lambda finding: (finding.path, finding.line))


def check_tree(root: Path = SOURCE) -> list[Finding]:
    found = []
    for path in sorted(root.rglob("*.py")):
        found.extend(check_file(path))
    return found


if __name__ == "__main__":
    for finding in check_tree():
        print(finding)
