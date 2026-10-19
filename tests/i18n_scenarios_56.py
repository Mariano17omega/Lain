"""Probe scenarios of spec 56: the "Criar cálculo" window, the k-path editor, "Gerar SCF convergido" and
the messages of the generation (``tests/i18n_probe.py`` adds ``SCENARIOS`` to its own).

- ``calc_create_setup``, ``calc_create_files``, ``calc_create_errors``: step 1 (both modes of the
  switch, the rebuild notes), step 2 of a Slab (tabs, "Arquivos", the report) and the messages the
  window shows when something is wrong. The widgets are the probe's usual texts; what no widget
  shows comes back as facts (the rows of "Arquivos", the notes of a plan, the errors of the writer).
- ``kpath_editor``, ``derive``: the band path table and the toast and warning of the converged SCF.
- ``calc_create_notices``, ``report_text``, ``combo_data``: facts for the tests of the counts and
  notes of ``core/calc_create/preview``, of the language of ``geracao.md`` and of the value a combo
  keeps behind its label.

The types are spec 57's: their names and fields may still be Portuguese in English, so nothing here
asserts on them. Modules with texts are imported inside the functions: the language is installed
before them (``tests/i18n_probe.py``). Files are written into the probe's temporary project and
folders; nothing is written into ``tests/fixtures``.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from i18n_scenarios_55 import wait_for

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
AL_SCF = FIXTURES / "al_bands" / "al.scf.in"
KAO = FIXTURES / "kao_surface_inputs"
BULK = KAO / "scf-kaolinite.in"
SURFACE = KAO / "scf-kaolinite-slab-001.in"
SCF_WAIT_MS = 10_000

# The SCF each type is built over for ``combo_data``: a surface type needs a bulk or a surface.
SCF_OF = {"slab": BULK, "supercell": SURFACE, "adsorption": SURFACE}


# -- the window ------------------------------------------------------------------------------------
def open_dialog(window):
    """The "Criar cálculo" window, shown and not run. A close with something typed would ask first:
    that question is answered "yes" (a real one would wait for a click)."""
    from qe_studio.ui.dialogs.calc_create import dialog as dialog_module

    dialog_module.ask_discard = lambda parent: True  # type: ignore[assignment]
    window.calc_create.open()
    dialog = window.calc_create.dialog
    if dialog is None:
        raise RuntimeError("the Criar cálculo window did not open")
    dialog.debounce_ms = 0
    return dialog


def pick_scf(dialog, path: Path):
    """Choose ``path`` as the SCF and wait for the worker: its ``ScfInfo``, None when it is refused."""
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    outcome: list[object] = []

    def ready(info: object) -> None:
        outcome.append(info)
        loop.quit()

    dialog.setup.scf_ready.connect(ready)
    QTimer.singleShot(SCF_WAIT_MS, loop.quit)
    try:
        dialog.setup.set_scf(path)  # a file that is no input answers at once
        if not outcome:
            loop.exec()
    finally:
        dialog.setup.scf_ready.disconnect(ready)
    if not outcome:
        raise RuntimeError(f"the SCF {path.name} was not read in time")
    return outcome[0]


def to_files(dialog, type_id: str, scf: Path, suffix: str, location: Path):
    """Step 1 filled, then "Continuar": the page of step 2."""
    setup = dialog.setup
    setup.set_type(type_id)
    if pick_scf(dialog, scf) is None:
        raise RuntimeError(f"{scf.name} was refused: {setup.scf_message.text()}")
    setup.suffix_edit.setText(suffix)
    setup.set_location(location)
    dialog.continue_button.click()
    tabs = dialog.tabs
    if tabs is None or not dialog.on_files_step():
        raise RuntimeError(f"no step 2: {setup.reason.text()}")
    tabs.flush()
    return tabs


def calc_create_setup_scenario(window, project: Path) -> list[str]:
    """Step 1 with "Numerar" on, both modes of the switch (it lives on step 2: the page is built and
    left), then a change that redoes step 2: the note, with and without edits to lose."""
    dialog = open_dialog(window)
    setup = dialog.setup
    setup.set_type("bandas")
    pick_scf(dialog, AL_SCF)
    setup.number_check.setChecked(True)
    setup.suffix_edit.setText("Al")
    setup.set_location(project)
    facts = [setup.name_preview.text()]
    dialog.set_mode("avancado")
    dialog.continue_button.click()
    dialog.set_mode("padrao")
    facts += [dialog.step.text(), dialog.mode_switch.buttons["padrao"].text()]
    dialog.back()
    setup.set_type("scf")  # the SCF and the type of step 2 no longer match what it was built for
    facts.append(setup.rebuild_note.text())
    setup.show_rebuild_note(True, lose_edits=True)
    facts.append(setup.rebuild_note.text())
    return facts


def calc_create_files_scenario(window, project: Path) -> list[str]:
    """Step 2 of a Slab over the bulk of kaolinite, in the ``avancado`` mode (every field): the tabs,
    the form, "Arquivos" and the report. The folder is also written (into a folder of its own) to
    compare what is written with what the tab shows."""
    from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME
    from qe_studio.core.calc_create.writer import create_folder

    dialog = open_dialog(window)
    dialog.set_mode("avancado")
    tabs = to_files(dialog, "slab", BULK, "Kao", project)
    calc_type = dialog.setup.calc_type
    plan = tabs.plan
    report = plan.by_key(REPORT_KEY)
    if calc_type is None or report is None or plan.errors:
        raise RuntimeError(f"the Slab plan is not usable: {plan.errors}")
    with tempfile.TemporaryDirectory(prefix="lain-i18n-create-") as where:
        created = create_folder(Path(where), calc_type, "Kao", plan)
        written = (created.folder / REPORT_NAME).read_text(encoding="utf-8")
        names = sorted(path.name for path in created.files)
    tree = tabs.files_view.tree
    rows = [
        " | ".join(tree.topLevelItem(row).text(column) for column in (0, 1))  # type: ignore[union-attr]
        for row in range(tree.topLevelItemCount())
    ]
    return [
        f"preview:\n{tabs.previews[REPORT_KEY].toPlainText()}",
        f"planned:\n{report.text}",
        f"written:\n{written}",
        f"name: {report.name}",
        f"files: {' '.join(names)}",
        *(f"row: {row}" for row in rows),
        *(f"note: {note}" for note in plan.notes),
        f"target: {tabs.files_view.target.text()}",
        f"hint: {tabs.files_view.note.text()}",
    ]


def calc_create_errors_scenario(window, project: Path) -> list[str]:
    """What the window and the core say when something is wrong: no SCF, a name the folder cannot
    have, files that are no SCF, a name taken, and what ``create_folder``, ``scf_info`` and the k-mesh
    report. The window ones are widget texts; every message also comes back as a fact."""
    from qe_studio.core.calc_create.kpath import KMesh
    from qe_studio.core.calc_create.scf_info import ScfInputError, scf_info
    from qe_studio.core.calc_create.surface.fixing import FROM_SCF, fixed_atoms
    from qe_studio.core.calc_create.surface.model import model_of
    from qe_studio.core.calc_create.types import PlannedFile, by_id
    from qe_studio.core.calc_create.writer import CreateError, create_folder

    dialog = open_dialog(window)
    setup = dialog.setup
    setup.set_type("bandas")
    dialog.continue_()  # no SCF: the line of step 1 says why
    facts = [f"no scf: {setup.reason.text()}"]
    setup.suffix_edit.setText("a/b")
    facts.append(f"name: {setup.suffix_message.text()}")
    setup.suffix_edit.setText("Al")
    for label, path, kind in (
        ("not an input", project / "03_bands" / "bands.dat.gnu", "bandas"),
        ("not an scf", project / "01_relax" / "si.rel.in", "bandas"),
        ("bulk", BULK, "adsorption"),
    ):
        setup.set_type(kind)
        pick_scf(dialog, path)
        facts.append(f"{label}: {setup.scf_message.text()}")
    setup.set_type("bandas")
    pick_scf(dialog, AL_SCF)
    (project / "Bands_Al").mkdir(exist_ok=True)
    setup.number_check.setChecked(False)  # remembered from the scenario before
    setup.set_location(project)
    facts.append(f"taken: {setup.name_preview.text()}")
    setup.set_location(project / "nao_existe")
    facts.append(f"place: {setup.location_message.text()}")

    bandas = by_id("bandas")
    made = bandas.plan(scf_info(AL_SCF.read_text(), AL_SCF), {}, window.config.jobs, "padrao", "")
    plan = dataclasses.replace(made, errors=())  # the fields of the type are spec 57's: no errors
    bad_name = dataclasses.replace(
        plan, files=(*plan.files, PlannedFile("a/b", "qe_input", "", "x", "x"))
    )
    too_long = dataclasses.replace(
        plan, files=(PlannedFile("x" * 300, "qe_input", "", "x", "x"), *plan.files)
    )
    with tempfile.TemporaryDirectory(prefix="lain-i18n-errors-") as where:
        for label, parent, made in (
            ("writer name", Path(where), bad_name),
            ("writer write", Path(where), too_long),
            ("writer place", Path(where) / "nao_existe", plan),
        ):
            try:
                create_folder(parent, bandas, "Err", made)
            except CreateError as exc:
                shown = str(exc).replace(where, "<dir>").replace("x" * 300, "<name>")
                facts.append(f"{label}: {shown}")
            else:
                raise RuntimeError(f"{label}: the folder was created")
    for label, text in (
        ("scf head", "&control\n/\n"),
        ("scf calculation", (project / "01_relax" / "si.rel.in").read_text()),
    ):
        try:
            scf_info(text)
        except ScfInputError as exc:
            facts.append(f"{label}: {exc}")
        else:
            raise RuntimeError(f"{label}: the SCF was accepted")
    facts += [f"kmesh: {problem}" for problem in KMesh((0, 1, 1), (0, 0, 2)).problems()]
    bulk = scf_info(BULK.read_text(), BULK)
    facts += [f"fixing: {note}" for note in fixed_atoms(model_of(bulk), FROM_SCF).notes]
    return facts


# -- the k-path editor, the derived SCF ---------------------------------------------------------
def kpath_editor_scenario(window, project: Path) -> list[str]:
    """The table with a segment bands.x would collapse and a jump (their tooltips are item data, so
    they come back as facts), an invalid cell typed, and an editor with no cell to measure with."""
    import numpy as np
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QVBoxLayout

    from qe_studio.core.calc_create.kpath import KPath, KPoint
    from qe_studio.ui.widgets.kpath_editor import K1, KPathEditor

    a = 3.16
    cell = np.array([[a, 0, 0], [-a / 2, a * 3**0.5 / 2, 0], [0, 0, a * 6.33]])
    points = (
        ("Gamma", (0, 0, 0)),
        ("A", (0, 0, 0.5)),
        ("L", (0.5, 0, 0.5)),
        ("H", (1 / 3, 1 / 3, 0.5)),
        ("A", (0, 0, 0.5)),
    )
    path = KPath(tuple(KPoint(label, frac, 20) for label, frac in points), frozenset({3}))
    holder = QDialog(window)
    holder.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    layout = QVBoxLayout(holder)
    editor = KPathEditor(window.theme, cell)
    bare = KPathEditor(window.theme, None)
    layout.addWidget(editor)
    layout.addWidget(bare)
    editor.set_path(path)
    holder.show()
    facts = []
    for row in range(editor.table.rowCount()):
        for column in range(editor.table.columnCount()):
            item = editor.table.item(row, column)
            if item is not None and (item.toolTip() or column == 4):
                facts.append(f"cell {row},{column}: {item.text()!r} {item.toolTip()}")
    for typed in ("abc", ""):
        editor.table.item(0, K1).setText(typed)  # type: ignore[union-attr]
        facts.append(f"typed {typed!r}: {editor.message.text()}")
    facts.append(f"no cell: {bare.distribute_button.toolTip()}")
    return facts


def derive_scenario(window, project: Path) -> list[str]:
    """ "Gerar SCF convergido": its item in the menu of a converged relax, the toast of the file
    written (the SCF reuses the prefix: the warning is in its details), and the message of a relax
    whose input is gone, which the controller shows in a box (recorded, never run)."""
    from PyQt6.QtWidgets import QMessageBox

    folder = project / "01_relax"
    output = folder / "si.rel.out"
    window.service.detect_now(folder)
    window.item_actions.menu(output, summary=True, scf="")
    while window.toast.current is not None:  # a notice queued by an earlier scenario shows first
        window.toast.dismiss()
    window.derive.generate_scf(output)
    wait_for(window.derive.generated)
    toast = window.toast.current
    if toast is None:
        raise RuntimeError("no toast after the converged SCF")
    facts = [f"toast: {toast.text}", f"details:\n{toast.details}"]

    broken = project / "08_relax_no_input"
    shutil.copytree(folder, broken)
    (broken / "si.rel.in").unlink()
    window.service.detect_now(broken)
    shown: list[tuple[str, str]] = []

    def warning(parent, title, text, *rest):
        shown.append((title, text))
        return QMessageBox.StandardButton.Ok

    real = QMessageBox.warning
    QMessageBox.warning = staticmethod(warning)  # type: ignore[assignment]
    try:
        window.derive.generate_scf(broken / "si.rel.out")
        wait_for(window.derive.failed)
    finally:
        QMessageBox.warning = real  # type: ignore[assignment]
    facts += [f"warning: {title} | {text}" for title, text in shown]
    return facts


# -- facts for the tests of the language ----------------------------------------------------------
def calc_create_notices_scenario(window, project: Path) -> list[str]:
    """What ``core/calc_create/preview`` says outside any widget: the size of a k-mesh (one point and
    many), the toast of a folder made (one file and two, with the reminder of the upload and the
    name that was taken) and the notes of a place outside the project."""
    from qe_studio.core.calc_create.kpath import KMesh
    from qe_studio.core.calc_create.preview import (
        created_notice,
        location_warnings,
        mesh_summary,
    )
    from qe_studio.core.calc_create.writer import Created

    folder = project / "Bands_Al"
    one = Created(folder, (folder / "bands.in",))
    two = Created(folder, (folder / "bands.in", folder / "bands.qsub"), "Bands")
    facts = [mesh_summary(None), *(mesh_summary(KMesh(n)) for n in ((1, 1, 1), (4, 4, 2)))]
    for created, sync in ((one, False), (two, True)):
        text, details = created_notice(created, sync)
        facts += [f"notice: {text}", f"details: {details.splitlines()[-1]}"]
    facts += [f"place: {note}" for note in location_warnings(project.parent, project)]
    facts += [f"place: {note}" for note in location_warnings(project, project)]
    return facts


def report_text_scenario(window, project: Path) -> list[str]:
    """``report_text`` of rows it is given: its title follows the language, the rows are kept."""
    from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME, report_text

    text = report_text([("rótulo", "valor"), ("Número", "3.14")])
    return [*text.splitlines(), f"name: {REPORT_NAME}", f"key: {REPORT_KEY}"]


def combo_data_scenario(window, project: Path) -> list[str]:
    """For every field of every type that is a choice: the value behind each item and the current
    one (``data``, equal in every language) and what the combo shows (``text``)."""
    from PyQt6.QtWidgets import QComboBox

    from qe_studio.core.calc_create.scf_info import scf_info
    from qe_studio.core.calc_create.types import REGISTRY
    from qe_studio.ui.dialogs.calc_create.form import FieldForm

    facts: list[str] = []
    for calc_type in REGISTRY:
        path = SCF_OF.get(calc_type.id, AL_SCF)
        scf = scf_info(path.read_text(), path)
        form = FieldForm(window.theme, calc_type.fields(scf, window.config.jobs, "x"), scf.crystal)
        for field_id, widget in form.widgets.items():
            if not isinstance(widget, QComboBox):
                continue
            items = [(widget.itemText(row), widget.itemData(row)) for row in range(widget.count())]
            where = f"{calc_type.id}.{field_id}"
            facts.append(
                f"data {where}: {[data for _text, data in items]} now {widget.currentData()}"
            )
            facts.append(f"text {where}: {[text for text, _data in items]}")
        form.deleteLater()
    return facts


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "calc_create_setup": calc_create_setup_scenario,
    "calc_create_files": calc_create_files_scenario,
    "calc_create_errors": calc_create_errors_scenario,
    "kpath_editor": kpath_editor_scenario,
    "derive": derive_scenario,
    "calc_create_notices": calc_create_notices_scenario,
    "report_text": report_text_scenario,
    "combo_data": combo_data_scenario,
}
