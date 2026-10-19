"""Static checks of the marked texts (spec end R4.1, spec 52 R4): AST walks over ``src/qe_studio``.

``check_tree`` reports two kinds of literal that are not marked with ``_()`` / ``N_()`` /
``ngettext()``:

- any string with a Portuguese accented letter or a common Portuguese word (``PORTUGUESE_WORDS``),
  outside docstrings, logs and the explicit list of exceptions below;
- a string passed straight to a call that shows text (``setText``, ``QLabel``, ``QMessageBox.*``,
  ``ParamField``, ``LoadError``…).

``shadowed_underscore`` finds a ``_`` bound again in a module that translates with ``_()``, and
``dynamic_messages`` the marker calls whose message is not a literal.
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
# Portuguese words without an accent that are no identifier or acronym, so a literal holding one is
# a text (spec 52 R4.4). Not ``dos`` (density of states) nor ``do`` (a shell keyword).
PORTUGUESE_WORDS = (
    "erro",
    "erros",
    "aviso",
    "avisos",
    "arquivo",
    "arquivos",
    "pasta",
    "pastas",
    "nenhum",
    "nenhuma",
    "sem",
    "não",
    "abrir",
    "fechar",
    "salvar",
    "cancelar",
    "entrada",
    "raiz",
    "grade",
    "novo",
    "nova",
    "atualizar",
    "enviar",
    "baixar",
    "gerar",
    "escuro",
    "claro",
    "ajuda",
)
WORDS = re.compile(r"\b(?:" + "|".join(PORTUGUESE_WORDS) + r")\b", re.IGNORECASE)

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
    ("ui/shutdown.py", "cancelar"),
    ("ui/shutdown.py", "grade"),
    # status_label values: data the filter compares (core/filtering.py STATES shows them through
    # _()); the tree and the cards show them translated with spec 53.
    ("core/file_kinds.py", "ERRO"),
    ("core/file_kinds.py", "SEM ERROS"),
    ("core/file_kinds.py", "AVISO"),
    ("core/calculations/bands/data.py", "entrada"),  # BandsDataset.tick_source: data, never shown
    ("core/calculations/bands/data.py", "nenhum"),
    ("core/structure3d/options.py", "nenhum"),  # ids: LABEL_MODES / BACKGROUNDS show their texts
    ("core/structure3d/options.py", "escuro"),
    ("core/structure3d/options.py", "claro"),
    ("ui/widgets/structure3d/renderer.py", "nenhum"),  # the LABEL_MODES id
    ("core/sync/planner.py", "novo"),  # Action values: the preview shows ACTION_TITLES
    ("core/sync/planner.py", "atualizar"),
    ("core/sync/push_plan.py", "enviar"),  # PushAction value: the preview shows PUSH_TITLES
    ("ui/widgets/structure3d/panel.py", " px"),  # a unit
    # The parameters of QE a field of "Criar cálculo" names, the same in both languages (spec 57
    # R1.3): the namelist each &PROJWFC tooltip starts with, two tooltips that are only the name of
    # the parameter, and QE's own term for -nk.
    ("core/calc_create/types/pdos.py", "&PROJWFC "),
    ("core/calc_create/types/relax.py", "&IONS ion_dynamics"),
    ("core/calc_create/types/vc_relax.py", "&CELL cell_dynamics"),
    ("core/calc_create/types/script.py", "Pools (nk)"),
    # File data that does not follow the language (spec 55 R2, R3): a CSV column, the first line
    # of a synced ``.plot``. The legend shows the sum of the atoms through its own ``_()``.
    ("core/calculations/pdos/render.py", "Soma dos átomos selecionados"),
    (
        "core/plotting/plot_file.py",
        "# Lain: ajustes do gráfico. Gerado automaticamente; apague para voltar aos padrões.\n",
    ),
    (
        "core/structure3d/view_file.py",
        "# Lain: ajustes da visualização 3D, uma seção por arquivo. "
        "Gerado automaticamente; apague para voltar aos padrões.\n",
    ),
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


def python_files(root: Path = SOURCE) -> Iterator[tuple[str, str]]:
    """``(source, path relative to root)`` of every module under ``root``."""
    for path in sorted(root.rglob("*.py")):
        yield path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()


def check_source(text: str, relative: str) -> list[Finding]:
    """The unmarked texts of the module ``relative`` (relative to ``src/qe_studio``)."""
    if relative in SKIPPED_FILES:
        return []
    tree = ast.parse(text)
    docs, skipped = _docstrings(tree), _skipped_nodes(tree)
    found: dict[int, Finding] = {}

    def add(constant: ast.Constant) -> None:
        if (relative, constant.value) not in EXCEPTIONS:
            found[id(constant)] = Finding(relative, constant.lineno, constant.value)

    for constant in _strings(tree):
        if id(constant) in docs or id(constant) in skipped:
            continue
        if ACCENTED.search(constant.value) or WORDS.search(constant.value):
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
    for text, relative in python_files(root):
        found.extend(check_source(text, relative))
    return found


# Scopes of their own: a ``_`` bound in them never reaches the code around them.
OWN_SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
# The marker calls and how many of their first arguments are messages.
MESSAGE_ARGUMENTS = {"_": 1, "N_": 1, "ngettext": 2, "pgettext": 2}


def _is_gettext_import(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[-1] == "i18n"
        and any(alias.name == "_" and alias.asname is None for alias in node.names)
    )


def _underscore_bindings(node: ast.AST) -> Iterator[int]:
    """Lines where ``node`` binds ``_`` (the gettext import, lambdas and comprehensions left out)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, OWN_SCOPES) or _is_gettext_import(child):
            continue
        if (
            (isinstance(child, ast.Name) and child.id == "_" and isinstance(child.ctx, ast.Store))
            or (isinstance(child, ast.arg) and child.arg == "_")
            or (isinstance(child, ast.ExceptHandler) and child.name == "_")
            or (isinstance(child, ast.alias) and (child.asname or child.name) == "_")
            or (
                isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and child.name == "_"
            )
        ):
            yield child.lineno
        yield from _underscore_bindings(child)


def shadowed_underscore(text: str, relative: str) -> list[Finding]:
    """Where a module that translates with ``_()`` binds ``_`` again (spec 52 R4.2): a ``_("…")``
    added later in that scope would call the value (or raise ``UnboundLocalError``). Name the
    throwaway something else (``_sep``)."""
    tree = ast.parse(text)
    if not any(_is_gettext_import(node) for node in ast.walk(tree)):
        return []
    return [Finding(relative, line, "_") for line in sorted(set(_underscore_bindings(tree)))]


def dynamic_messages(text: str, relative: str) -> list[tuple[str, str]]:
    """``(module, argument)`` of each marker call whose message is not a literal (spec 52 R4.3):
    the extraction cannot see it, so it is translated only if its data was marked with ``N_``."""
    found = []
    for node in ast.walk(ast.parse(text)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        for argument in node.args[: MESSAGE_ARGUMENTS.get(node.func.id, 0)]:
            if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                found.append((relative, ast.unparse(argument)))
    return found


if __name__ == "__main__":
    for finding in check_tree():
        print(finding)
