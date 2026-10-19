"""Probe scenarios of spec 54: the viewers (text, input, diff, Markdown, ``.qsub``), the Resumo and the
write checks they show (``tests/i18n_probe.py`` adds ``SCENARIOS`` to its own).

A viewer reads in a worker of the global thread pool, which the probe's ``settle`` does not wait
for: each scenario waits for the pool itself (``read``) right after it opens a tab. What no widget
shows comes back as *facts*, to compare with the other language:

- the cells of the diff tree and the rows of the Resumo (item data, not widget text);
- texts with a number or a name in them (the problems label, the banners): a leak is no
  ``msgid``, so ``leaks`` cannot see it;
- the messages of the linters, which the editor only shows in a hover tip (``QToolTip``).

Files go into ``<project>/viewers``; nothing is written into ``tests/fixtures``.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

# One snippet per rule of the input linter (spec 11 R2) and per message of the script linter.
INPUT_HEAD = "&control\n/\n&system\n/\n&electrons\n/\n"
INPUTS = (
    "&control\n prefix = 'si\n calculation = 'scf'\n/\n&system\n/\n&electrons\n/\n",
    "&system\n nat = 1\n&electrons\n/\n",
    INPUT_HEAD.replace("&control\n/", "&control\n prefix\n/"),
    INPUT_HEAD.replace("&control\n/", "&control\n ecutwfc =\n/"),
    INPUT_HEAD.replace(
        "&control\n/", "&control\n starting_magnetization(1 = 0.5\n celldm1) = 5\n/"
    ),
    INPUT_HEAD.replace("&control\n/", "&control\n lflag = .ture.\n conv_thr = 1.0e\n/"),
    "&contrl\n/\n&system\n/\n&electrons\n/\n&plasma\n/\n",
    INPUT_HEAD + "&control\n/\n",
    INPUT_HEAD + "ATOMIC_POSITION crystal\nK_POINTS {automatc}\n",
    "&\n/\n&end\n/\n/\n",
)
SCRIPTS = (
    b"echo hi\n#$ -N\n#$ -pe physica\n#$ -zz\necho a \\ \nfi\nif true; then\necho b\r\n",
    b'#!/bin/bash\necho "abc\n',
    b"#!/bin/bash\necho ${x\ndone\nesac\ndo\ncase x in\nwhile true; do\n",
)
# The script of the ``qsub`` scenario: the five problems of ``qsub_lint`` and three more.
SCRIPT = SCRIPTS[0]

A_INPUT = """&control
 calculation = 'scf'
 prefix = 'x'
/
&system
 ibrav = 2, celldm(1) = 7.5, nat = 2, ntyp = 2, ecutwfc = 30
/
&electrons
/
ATOMIC_SPECIES
Al 26.98 Al.UPF
Si 28.08 Si.UPF
ATOMIC_POSITIONS crystal
Al 0 0 0
Si 0.25 0.25 0.25
K_POINTS automatic
4 4 4 0 0 0
CELL_PARAMETERS alat
1 0 0
0 1 0
0 0 1
"""
B_INPUT = """&control
 calculation = 'scf'
/
&system
 ibrav = 2, celldm(1) = 7.5, nat = 2, ntyp = 2, ecutwfc = 40, ecutrho = 160
/
&electrons
/
ATOMIC_SPECIES
Al 26.98 Al-b.UPF
Si 28.08 Si-b.UPF
ATOMIC_POSITIONS angstrom
Al 0 0 0
Si 0.25 0.25 0.25
K_POINTS gamma
OCCUPATIONS
1.0 1.0
"""
NOTES = """# Resultados do Al

Texto com **negrito**, `codigo` e [o site](https://example.org/doc) e [outro](outro.md).

| a | b |
|---|---|
| 1 | 2 |

## Notas
"""


def read() -> None:
    """Wait for the reads the scenario started and deliver their results to the GUI thread."""
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtWidgets import QApplication

    QThreadPool.globalInstance().waitForDone(5000)
    for _round in range(5):
        QApplication.processEvents()


def folder(project: Path) -> Path:
    path = project / "viewers"
    path.mkdir(exist_ok=True)
    return path


def open_text(window, path: Path):
    """The text viewer of ``path``, read."""
    window.open_file(path)
    read()
    viewer = window.workspace.widget_for(str(path))
    if viewer is None or viewer.loading:
        raise RuntimeError(f"{path.name} was not read")
    return viewer


def tree_cells(tree) -> list[str]:
    """Every row of a ``QTreeWidget``, children included, its cells joined by ``|``."""
    cells: list[str] = []

    def walk(item) -> None:
        cells.append(" | ".join(item.text(column) for column in range(tree.columnCount())))
        for index in range(item.childCount()):
            walk(item.child(index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return cells


def summary_rows(summary) -> list[str]:
    """The Resumo as the view shows it: each title as drawn (uppercase) and each ``label: value``."""
    facts: list[str] = []

    def walk(rows, depth: int) -> None:
        for row in rows:
            facts.append(f"{'  ' * depth}{row.label}: {row.value}")
            walk(row.children, depth + 1)

    for section in summary.sections:
        facts.append(section.title.upper())
        walk(section.rows, 0)
    return facts


# -- the viewers -------------------------------------------------------------------------------------
def banners() -> list[str]:
    """What ``read_preview`` says about a job log, a cut file, and an input, a script and a
    Markdown file above their limits (the limits patched down to a few bytes)."""
    from qe_studio.core import text_preview, textfile
    from qe_studio.core.text_preview import read_preview

    with tempfile.TemporaryDirectory(prefix="lain-i18n-preview-") as where:
        root = Path(where)
        (root / "empty.o1").write_text("")
        (root / "failed.o2").write_text("error\n")
        big = root / "big.out"
        big.write_text("line of the output\n" * 40)
        (root / "big.in").write_text(INPUT_HEAD + " ecutwfc = 30\n" * 10)
        (root / "big.qsub").write_bytes(b"#!/bin/bash\n" + b"echo hi\n" * 20)
        (root / "big.md").write_text("# Title\n\ntext\n" * 10)
        found = [read_preview(root / name).banner for name in ("empty.o1", "failed.o2")]
        with (
            mock.patch.object(textfile, "LARGE_FILE", 400),
            mock.patch.object(textfile, "HEAD_BYTES", 100),
            mock.patch.object(textfile, "TAIL_BYTES", 200),
        ):
            cut = read_preview(big)
            found += [cut.banner, read_preview(big, full=True).banner]
            found.append(textfile.MARKER.strip() if textfile.MARKER.strip() in cut.text else "")
        with (
            mock.patch.object(text_preview, "INPUT_READ_LIMIT", 50),
            mock.patch.object(text_preview, "MARKDOWN_RENDER_LIMIT", 50),
        ):
            found += [read_preview(root / name).banner for name in ("big.in", "big.qsub", "big.md")]
    return found


def text_viewer_scenario(window, project: Path) -> list[str]:
    """A pw.x output with the search open and the go-to-line prompt (``QInputDialog.getInt`` is a
    modal call: it is replaced by the same dialog, shown and not run)."""
    from PyQt6.QtWidgets import QInputDialog

    viewer = open_text(window, project / "02_scf" / "scf.out")
    viewer.search.field.setText("total energy")
    viewer.open_search()
    viewer.search.next_match()

    def prompt(parent, title, label, *rest):
        dialog = QInputDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.show()
        return 1, False

    QInputDialog.getInt = staticmethod(prompt)  # type: ignore[assignment]
    viewer.ask_line()
    return banners()


def input_viewer_scenario(window, project: Path) -> list[str]:
    """An input with write errors: the problems bar, the extract and the tooltips of its chips."""
    path = folder(project) / "broken.in"
    text = (project / "02_scf" / "scf.in").read_text()
    path.write_text(
        text.replace("prefix='al',", "prefix='al,").replace("ecutwfc = 100,", "ecutwfc = 100e,")
        .replace("&electrons", "&electron").replace("K_POINTS automatic", "K_POINTS automatc")
    )  # fmt: skip
    viewer = open_text(window, path)
    viewer.editor.go_to_line(1)
    view = viewer.input_view
    return [view.issues_label.text()] + [
        f"{button.text()} | {button.toolTip()}" for button in view.chip_buttons
    ]


def diff_scenario(window, project: Path) -> list[str]:
    """Two inputs compared (both modes), one that is not there and one over the size limit."""
    from qe_studio.core.qe import input_diff

    where = folder(project)
    a, b = where / "a.in", where / "b.in"
    a.write_text(A_INPUT)
    b.write_text(B_INPUT)
    diff = window.workspace.open_diff(a, b)
    read()
    diff.show_text()
    diff.show_params()
    facts = tree_cells(diff.tree)
    missing = window.workspace.open_diff(a, where / "missing.in")
    read()
    facts.append(missing.message.text())
    with mock.patch.object(input_diff, "INPUT_READ_LIMIT", 10):
        big = window.workspace.open_diff(b, a)
        read()
    facts.append(big.message.text())
    return facts


def summary_scenario(window, project: Path) -> list[str]:
    """The Resumo of a vc-relax (its input beside it gives the k mesh), every row opened."""
    from qe_studio.ui.widgets.summary_view import summary_key

    where = folder(project)
    for name in ("vc-relax.in", "vc-relax.out"):
        shutil.copy(FIXTURES / "kao_vc_relax" / name, where / name)
    path = where / "vc-relax.out"
    window.open_summary(path)
    read()
    view = window.workspace.widget_for(summary_key(path))
    if view is None or view.summary is None:
        raise RuntimeError("the summary of vc-relax.out was not read")
    for section in view.sections:
        for row in section.rows:
            row.expand()
    return summary_rows(view.summary)


def markdown_scenario(window, project: Path) -> list[str]:
    """A Markdown file rendered, a refused link (the footer says so), then as text."""
    from PyQt6.QtCore import QUrl

    path = folder(project) / "notes.md"
    path.write_text(NOTES)
    viewer = open_text(window, path)
    viewer.set_rendered(True, remember=False)
    viewer.markdown.anchorClicked.emit(QUrl("outro.md"))
    facts = [window.status.message.text()]
    viewer.set_rendered(False, remember=False)
    return facts


def qsub_scenario(window, project: Path) -> list[str]:
    """A ``.qsub`` with the five problems of ``qsub_lint`` and two more: the bar that counts them."""
    path = folder(project) / "job.qsub"
    path.write_bytes(SCRIPT)
    return [open_text(window, path).input_view.issues_label.text()]


def lint_scenario(window, project: Path) -> list[str]:
    """The messages of both linters on a text for each of their rules: the editor shows them in a
    hover tip, which is no widget text."""
    from qe_studio.core.qe.input_lint import lint
    from qe_studio.core.qsub_lint import lint_script

    messages = [issue.message for text in INPUTS for issue in lint(text).issues]
    for script in SCRIPTS:
        messages += [issue.message for issue in lint_script(script.decode())]
    return messages


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "text_viewer": text_viewer_scenario,
    "input_viewer": input_viewer_scenario,
    "diff": diff_scenario,
    "summary": summary_scenario,
    "markdown": markdown_scenario,
    "qsub": qsub_scenario,
    "lint": lint_scenario,
}
