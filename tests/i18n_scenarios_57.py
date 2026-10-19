"""Probe scenarios of spec 57: the ten calculation types of "Criar cálculo" (``tests/i18n_probe.py``
adds ``SCENARIOS`` to its own).

- ``calc_create_<type>``: step 1 in the ``avancado`` mode and step 2 of the type, every tab built.
  The facts are the list of types, the name step 1 gives the SCF, the tabs and, for every field, its
  label and the tooltip its label holds (``toolTip()``).
- ``calc_create_validation_<type>``: what the type says of a field left empty and of values it
  refuses, typed into the widgets of step 2 (the marked fields show the problem as their tooltip).
  The facts are the errors, the problems by field, the notes and those tooltips, before (``empty``)
  and after (``typed``) the values are typed.
- ``slab_files``: a Slab over the bulk of kaolinite with the molecule's SCF, its report in the tab and
  in the plan, and the text of every file ``create_folder`` writes (R2.2: the same ``.in`` and
  ``.qsub`` in both languages, ``geracao.md`` in each one).

Modules with texts are imported inside the functions: the language is installed before them. The
folders are written into temporary ones; nothing is written into ``tests/fixtures``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from i18n_scenarios_56 import AL_SCF, KAO, SCF_OF, SCF_WAIT_MS, open_dialog, to_files

MOLECULE = KAO / "scf-H3CHg.in"
MOLECULE_FIELD = "molecule"  # surface_fields.MOLECULE: the field of the second SCF
# The ids of ``calc_create.types.REGISTRY``, in its order (a test keeps them equal).
TYPE_IDS = (
    *("scf", "relax", "vc-relax", "bandas", "pdos", "charge", "charge_diff"),
    *("slab", "supercell", "adsorption"),
)

# What ``calc_create_validation_<type>`` types into step 2: values the type refuses or warns about,
# by field id. A choice is its value (the Portuguese token, the same in both languages). The required
# field of a type is left empty first: the bands' path, the atoms of the charge difference, the SCF of
# the molecule (read, for the second state, only where ``with_molecule`` says).
TYPED: dict[str, dict[str, object]] = {
    "scf": {"job_name": "job de teste", "name:scf": "scf al.in", "np": "0"},
    "relax": {"nstep": "abc", "np": "64", "nk": "7"},
    "vc-relax": {"press": "x", "np": "4", "nk": "8"},
    "bandas": {"name:bands": "bands", "nk": "0"},
    "pdos": {"e_min": "30", "degauss": "abc"},
    "charge": {
        "plot_num": "-1",
        "fileout": "/tmp/al.xsf",
        "iflag": "2 — gráfico 2D",
        "name:scf": "dup.in",
        "name:pp_charge": "dup.in",
    },
    "charge_diff": {"xsf_dir": "../xsf"},
    "slab": {  # a valid vacuum: the fixed atoms are checked once the slab is made
        "ads_distance": "-1",
        "bond_scale": "0",
        "complete": True,
        "metals": "Xx",
        "fix_rule": "espécies e vizinhos",
        "fix_species": ",",
        "fix_neighbors": "Yy",
    },
    "supercell": {
        "n2": "2",
        "bond_scale": "-1",
        "vacuum_min": "-1",
        "fix_rule": "camada inferior",
        "fix_fraction": "2",
    },
    "adsorption": {  # the window also empties the table of the site, which says why
        "ads_distance": "-1",
        "h_clearance": "-1",
        "site_tol": "0",
        "height_window": "0",
        "symprec": "0",
    },
}
WITH_MOLECULE = {"adsorption"}


# -- step 2 --------------------------------------------------------------------------------------
def files_step(window, type_id: str, project: Path):
    """The window in the ``avancado`` mode, on step 2 of ``type_id`` over its SCF."""
    dialog = open_dialog(window)
    dialog.set_mode("avancado")
    return dialog, to_files(dialog, type_id, SCF_OF.get(type_id, AL_SCF), "I18n", project)


def pick_molecule(tabs, path: Path) -> None:
    """The molecule's SCF read by its field (a worker), then the plan made again."""
    from PyQt6.QtCore import QEventLoop, QTimer

    field = tabs.widget_of(MOLECULE_FIELD)
    loop = QEventLoop()
    field.changed.connect(loop.quit)
    QTimer.singleShot(SCF_WAIT_MS, loop.quit)
    try:
        field.set_path(path)
        loop.exec()
    finally:
        field.changed.disconnect(loop.quit)
    if field.value() is None:
        raise RuntimeError(f"the molecule {path.name} was not read: {field.message.text()}")
    tabs.flush()


def type_values(tabs, values: dict[str, object]) -> None:
    """``values`` typed into their widgets, then the plan made again (what an edit does)."""
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit

    for field_id, value in values.items():
        widget = tabs.widget_of(field_id)
        if isinstance(widget, QComboBox):
            index = widget.findData(value)
            if index < 0:
                raise RuntimeError(f"{field_id} has no choice {value!r}")
            widget.setCurrentIndex(index)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        else:
            raise RuntimeError(f"{field_id}: no way to type into a {type(widget).__name__}")
    tabs.flush()


def marked_tip(widget) -> str:
    """The tooltip ``FieldForm.mark`` sets: the problem of the field, or its tooltip."""
    from qe_studio.ui.dialogs.calc_create.scf_field import ScfFileField
    from qe_studio.ui.widgets.atom_table import AtomTable
    from qe_studio.ui.widgets.kpath_editor import KPathEditor

    if isinstance(widget, KPathEditor | AtomTable):
        return widget.table.toolTip()
    if isinstance(widget, ScfFileField):
        return widget.edit.toolTip()
    return widget.toolTip()


# -- the scenarios ---------------------------------------------------------------------------------
def type_scenario(type_id: str) -> Callable[..., list[str]]:
    def scenario(window, project: Path) -> list[str]:
        from PyQt6.QtWidgets import QLabel

        dialog, tabs = files_step(window, type_id, project)
        combo = dialog.setup.type_combo
        facts = [
            f"types: {' | '.join(combo.itemText(row) for row in range(combo.count()))}",
            f"scf: {dialog.setup.scf_label.text()}",
            *(f"tab: {label}" for label in tabs.tab_labels()),
        ]
        for form in tabs.forms:
            for form_field in form.fields:
                label = form.rows[form_field.id][0]
                if isinstance(label, QLabel):
                    facts.append(f"field {form_field.id}: {label.text()} | {label.toolTip()}")
        return facts

    scenario.__doc__ = f"Step 2 of {type_id} in the avancado mode: its tabs and fields."
    return scenario


def plan_facts(tabs, state: str) -> list[str]:
    """The errors, problems, marked tooltips and notes of step 2 now, and the legend of each table of
    atoms (its hint, or why it has no rows: the rows of a field are its label, legend and table)."""
    plan = tabs.plan
    legends = [
        f"{state} legend {form_field.id}: {form.rows[form_field.id][1].text()}"
        for form in tabs.forms
        for form_field in form.fields
        if form_field.kind == "atoms"
    ]
    return [
        *legends,
        *(f"{state} error: {error}" for error in plan.errors),
        *(
            f"{state} problem {field_id}: {text}"
            for field_id, text in sorted(plan.problems.items())
        ),
        *(
            f"{state} tip {field_id}: {marked_tip(tabs.widget_of(field_id))}"
            for field_id in sorted(plan.problems)
            if any(field_id in form.widgets for form in tabs.forms)
        ),
        *(f"{state} note: {note}" for note in plan.notes),
    ]


def validation_scenario(type_id: str) -> Callable[..., list[str]]:
    def scenario(window, project: Path) -> list[str]:
        _dialog, tabs = files_step(window, type_id, project)
        facts = plan_facts(tabs, "empty")
        if type_id in WITH_MOLECULE:
            pick_molecule(tabs, MOLECULE)
        type_values(tabs, TYPED[type_id])
        return facts + plan_facts(tabs, "typed")

    scenario.__doc__ = f"What {type_id} says of an empty required field and of values it refuses."
    return scenario


def slab_files_scenario(window, project: Path) -> list[str]:
    """A Slab with the molecule's SCF, made by the window and written by ``create_folder``: the
    report as the tab shows it and as planned, and the text of every file written."""
    from qe_studio.core.calc_create.surface.report import REPORT_KEY
    from qe_studio.core.calc_create.writer import create_folder

    dialog, tabs = files_step(window, "slab", project)
    pick_molecule(tabs, MOLECULE)
    plan, calc_type = tabs.plan, dialog.setup.calc_type
    report = plan.by_key(REPORT_KEY)
    if calc_type is None or report is None or plan.errors:
        raise RuntimeError(f"the Slab plan is not usable: {plan.errors}")
    facts = [f"preview:\n{tabs.previews[REPORT_KEY].toPlainText()}", f"planned:\n{report.text}"]
    with tempfile.TemporaryDirectory(prefix="lain-i18n-slab-") as where:
        created = create_folder(Path(where), calc_type, "Kao", plan)
        for path in sorted(created.files):
            facts.append(f"file {path.name}:\n{path.read_text(encoding='utf-8')}")
    return facts


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    **{f"calc_create_{type_id}": type_scenario(type_id) for type_id in TYPE_IDS},
    **{f"calc_create_validation_{type_id}": validation_scenario(type_id) for type_id in TYPE_IDS},
    "slab_files": slab_files_scenario,
}
